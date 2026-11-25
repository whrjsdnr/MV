"""고정 소스의 PIL Resize + ImageNet Normalize + AE ColorJitter를 재현한다."""
from torchvision import transforms as T

NORMALIZE = T.Normalize([.485,.456,.406], [.229,.224,.225])
BASE = T.Compose([T.Resize((256,256)), T.ToTensor(), NORMALIZE])
AE = T.RandomChoice([T.ColorJitter(brightness=.2), T.ColorJitter(contrast=.2), T.ColorJitter(saturation=.2)])


def prepare_image(sample, *, augment=False):
    if sample['metadata']['image_policy'] != 'approved_crop':
        raise ValueError('EfficientAD requires approved_crop')
    image = T.ToPILImage()(sample['image'])
    return BASE(AE(image) if augment else image)
