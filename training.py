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
config.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini"))
epochs = int(config["training"]["epochs"])
is_debug = bool(config["app"]["debug"])
gpu = config["tranining"]["gpu"]


def get_cuda_device():
    device = torch.device("cpu:0")
    if torch.cuda.is_available():
        os.environ['CUDA_VISIBLE_DEVICES'] = gpu
        device = torch.device("cuda", int(gpu))
    return device


def testing(test_loader, model, loss_fn, device, epoch=0):
    target = config["testing"]["logdir"]
    writer = SummaryWriter(target)

    print("### Testing period....... ###")

    # 此处没有训练过程
    with torch.no_grad():
        model.eval()
        model.to(device)
        index = 0
        iou = 0
        for idx, data in enumerate(test_loader):
            images, ground_truths = torch.squeeze(data[0], 1).to(device), torch.squeeze(data[1], 1).to(device)
            assert images.shape[1:] == (3, 224, 224)  # format: (batch_size, frame_len, c, h, w)
            assert ground_truths.shape[1:] == (1, 224, 224)
            outputs = model(images)
            loss = loss_fn(outputs, ground_truths)
            print("The loss at epoch {} is {}...".format(epoch, loss))
            writer.add_scalar("test/bce_loss", loss, epoch)
            # calculate iou
            for key, output in enumerate(outputs):
                # get iou at each epoch
                iou += getIOU(output, ground_truths[key])
                index += 1
            avg_iou = iou / index
            print("The iou at epoch {} is {}...".format(epoch, avg_iou))
            writer.add_scalar("test/iou", avg_iou, epoch)
    writer.close()


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
    target = config["training"]["logdir"]
    writer = SummaryWriter(target)
    optimizer = optim.Adam(model.parameters(), lr=1e-4)

    if not os.path.exists(target):
        os.mkdir(target)

    # TODO: calculating on the gpu device
    for i in range(epochs):
        total_loss = 0
        index = 0
        model.train()
        model.to(device)
        print("### the epoch {} start.... ###".format(i))
        for idx, data in enumerate(train_loader):
            images = torch.squeeze(data[0], 1).to(device)
            pos_gts, neg_gts = torch.squeeze(data[2], 1).to(device), torch.squeeze(data[3], 1).to(device)
            assert images.shape[1:] == (3, 224, 224)    # format: (batch_size, frame_len, c, h, w)
            assert pos_gts.shape[1:] == (1, 224, 224)
            assert neg_gts.shape[1:] == (1, 224, 224)
            optimizer.zero_grad()
            outputs = model(images)
            loss = loss_fn(outputs, pos_gts)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            index += 1

        print("The loss of epoch {} is {}".format(i, total_loss/index))
        writer.add_scalar("train/bce_loss", total_loss/index, i)
        # output result image every epoch
        with torch.no_grad():
            model.eval()
            index = 0
            iou = 0
            for idx, data in enumerate(train_loader):
                images, ground_truths = torch.squeeze(data[0], 1).to(device), torch.squeeze(data[1], 1).to(device)
                pos_gts = torch.squeeze(data[2], 1).to(device)
                filenames = data[4]         # might be multiple frames here, so it's two dimension array here.
                dataset = data[5][0][0]     # get the dataset name
                assert images.shape[1:] == (3, 224, 224)  # format: (batch_size, frame_len, c, h, w)
                assert ground_truths.shape[1:] == (1, 224, 224)
                outputs = model(images)
                for key, output in enumerate(outputs):
                    # get iou at each epoch, using sigmoid to activate.
                    output_for_iou = F.sigmoid(output)
                    temp_iou = getIOU(output_for_iou, ground_truths[key])
                    # save the output after training for the next epoch
                    write_training_images(output_for_iou, i, dataset, filenames[key])
                    # record the outliers when iou is less than 0.5
                    if is_debug and temp_iou < 0.5:
                        visualize_outlier(images[key], output_for_iou, ground_truths[key], pos_gts[key], i, dataset, filenames[key])
                    iou += temp_iou
                    index += 1
            avg_iou = iou / index
            print("The iou at epoch {} is {}...".format(i, avg_iou))
            writer.add_scalar("train/iou", avg_iou, i)
        # 测试嵌套在每一个epoch训练完之后
        if not is_debug:
            testing(test_loader, model, loss_fn, device, i)
    writer.close()



