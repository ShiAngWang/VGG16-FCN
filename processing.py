import torch
import random
from torchvision import transforms
import torchvision.transforms.functional as TF


# 根据阈值，将Tensor二值化为0-1map
def binarify(output, threshold=0.5):
    ones_temp = torch.ones_like(output, dtype=torch.uint8)
    zeros_temp = torch.zeros_like(output, dtype=torch.uint8)

    final_output = torch.where(output > threshold, ones_temp, zeros_temp)
    return final_output

# 给定多个list，以相同的方式就地shuffle多个数组
def shuffle_lists(*lists):
    seed = random.random()
    for array in lists:
        random.seed(seed)
        random.shuffle(array)


# data augmentation
def augment_transform(*datasets, target_size):
    """
    对图片进行data augmentation，包括crop, flip和color jitter
    :param datasets:
    :return:
    """

    length = len(datasets)
    assert length > 0

    # crop, flip and color change
    composer = transforms.Compose([
        transforms.RandomResizedCrop(target_size, scale=(0.85, 1)),
        transforms.RandomHorizontalFlip(),
    ])

    # only do this for the input image
    jitter = transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.01, hue=0.01)

    result_imgs = []

    # 对一个batch中的每张图片进行相同的transform，注意要对应
    for i in range(length):
        temp_img = composer(datasets[i])
        if i == 0:
            temp_img = jitter(temp_img)
        result_imgs.append(temp_img)

    return result_imgs




