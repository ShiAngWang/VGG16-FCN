from torch.utils.tensorboard import SummaryWriter
from torchvision.transforms import functional as TF
from torch.nn import functional as F
import torch.optim as optim
import os
import configparser
from benchmarks import *
from visualization import *
import numpy as np

config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "config.ini"))
outlier_training_root = config["isic_train"]["outlier_root"]
outlier_test_root = config["isic_test"]["outlier_root"]
epochs = int(config["isic_train"]["epochs"])
is_debug = config.getboolean("isic", "debug")
gpu = config["isic_train"]["gpu"]
predict_root = config["isic_test"]["prediction_root"]


def get_cuda_device():
    device = torch.device("cpu:0")
    if torch.cuda.is_available():
        os.environ['CUDA_VISIBLE_DEVICES'] = gpu
        device = torch.device("cuda", int(gpu))
    return device


def testing(test_loader, model, loss_fn, device, epoch=0):
    target = config["isic_test"]["logdir"]
    writer = SummaryWriter(target)

    print("### Testing period of epoch {}....... ###".format(epoch))

    # 此处没有训练过程
    with torch.no_grad():
        model.eval()
        model.to(device)
        iou = 0
        index = 0
        for idx, data in enumerate(test_loader):
            images, ground_truths = data[0].to(device), data[1].to(device)
            pos_gts = data[2].to(device)
            filename = data[3]
            assert images.shape[1:] == (3, 224, 224)  # format: (batch_size, frame_len, c, h, w)
            assert ground_truths.shape[1:] == (1, 224, 224)
            outputs = model(images)
            loss = loss_fn(outputs, pos_gts)
            print("The loss at epoch {} is {}...".format(epoch, loss))
            writer.add_scalar("test/bce_loss/{}".format(epoch), loss, idx)
            # calculate iou
            for key, output in enumerate(outputs):
                # get iou at each epoch
                output_for_iou = F.sigmoid(output)
                threshold = threshold_by_ostu(TF.to_pil_image(output_for_iou.detach().cpu())) / 255
                # 输出预测结果和fake_Gt
                if is_debug:
                    output_for_vis = 255 * binarify(output_for_iou, threshold)
                    visualize_image(output_for_vis, os.path.join(predict_root, "predict_gt_{}".format(filename)))
                temp_iou = max(getIOU(output_for_iou, ground_truths[key], threshold), getIOU(1-output_for_iou, ground_truths[key], threshold))
                iou += temp_iou
                index += 1
        avg_iou = iou / index
        print("The iou at epoch {} is {}...".format(epoch, avg_iou))
        writer.add_scalar("test/iou", avg_iou, epoch)
    writer.close()

# TODO: save model and checkpoint
def training(train_loader, test_loader, model, loss_fn, device):
    """
    训练函数，以epoch为基本单位，每一个epoch里使用fake_gt训练网络，并记录和real_gt的iou和训练loss，并进行测试
    每一个iteration结束后，额外打印训练数据对应的模型输出作为下一轮的fake_gt。
    :param device: gpu device
    :param train_loader:
    :param test_loader:
    :param model:
    :param loss_fn:
    :return:
    """
    target = config["isic_train"]["logdir"]
    writer = SummaryWriter(target)
    optimizer = optim.Adam(model.parameters(), lr=1e-4)

    if not os.path.exists(target):
        os.mkdir(target)

    for i in range(epochs):
        model.train()
        model.to(device)
        print("### the epoch {} start.... ###".format(i))
        for idx, data in enumerate(train_loader):
            images, ground_truths = data[0].to(device), data[1].to(device)
            pos_gts = data[2].to(device)
            assert images.shape[1:] == (3, 224, 224)    # format: (batch_size, frame_len, c, h, w)
            assert pos_gts.shape[1:] == (1, 224, 224)
            optimizer.zero_grad()
            outputs = model(images)
            loss = loss_fn(outputs, pos_gts)
            loss.backward()
            optimizer.step()
            writer.add_scalars("train/bce_loss", {"epoch_{}".format(i): loss.item()}, idx)
        # output result image every epoch
        with torch.no_grad():
            model.eval()
            for idx, data in enumerate(train_loader):
                index = 0
                iou = 0
                images, ground_truths = data[0].to(device), data[1].to(device)
                pos_gts = data[2].to(device)
                filename = data[3]         # might be multiple frames here, so it's two dimension array here.
                assert images.shape[1:] == (3, 224, 224)  # format: (batch_size, frame_len, c, h, w)
                assert ground_truths.shape[1:] == (1, 224, 224)
                outputs = model(images)
                for key, output in enumerate(outputs):
                    # get iou at each epoch, using sigmoid to activate.
                    output_for_iou = F.sigmoid(output)
                    threshold = threshold_by_ostu(TF.to_pil_image(output_for_iou.detach().cpu()))/255
                    print("the threshold is {}...".format(threshold))
                    temp_iou = max(getIOU(output_for_iou, ground_truths[key], threshold), getIOU(1-output_for_iou, ground_truths[key], threshold))
                    # record the outliers when iou is less than 0.5
                    if is_debug and temp_iou < 0.5:
                        output_for_vis = 255*binarify(output_for_iou, threshold)
                        visualize_outlier(config["isic_train"]["outlier_root"], images[key].detach().cpu(), output_for_vis.detach().cpu(), ground_truths[key].detach().cpu(), pos_gts[key].detach().cpu(), i, "training", filename)
                    iou += temp_iou
                    index += 1
                avg_iou = iou / index
                print("The iou at batch {} in epoch {} is {}...".format(i, idx, avg_iou))
                writer.add_scalars("train/iou", {"epoch_{}".format(i): avg_iou}, idx)
        # 测试嵌套在每一个epoch训练完之后
        testing(test_loader, model, loss_fn, device, i)
    writer.close()



