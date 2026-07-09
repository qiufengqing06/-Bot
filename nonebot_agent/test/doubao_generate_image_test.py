import os
import random

import dotenv
import requests

dotenv.load_dotenv()

base_url = os.getenv("DOUBAO_API_URL")
api_key = os.getenv("DOUBAO_API_KEY")

''' 
- 生成图片分辨率 2560*1440 - 4096*4096
- 文生图或图生图 
'''
from volcenginesdkarkruntime import Ark

client = Ark(
    base_url=base_url,
    api_key=api_key,
)

imagesResponse = client.images.generate( # 文生图
    # Replace with Model ID
    model="doubao-seedream-4-5-251128",
    prompt="充满活力的特写编辑肖像，模特眼神犀利，头戴雕塑感帽子，色彩拼接丰富，眼部焦点锐利，景深较浅，具有Vogue杂志封面的美学风格，采用中画幅拍摄，工作室灯光效果强烈。",
    size="4K",
    response_format="url",
    watermark=False
)

print(imagesResponse.data[0].url)
res = requests.get(imagesResponse.data[0].url)
with open("doubao_generate_image_by_text.png", "wb") as f:
    f.write(res.content)

'''
图片URL：请确保图片URL可被访问。
Base64编码：请遵循此格式data:image/<图片格式>;base64,<Base64编码>。注意 <图片格式> 需小写，如 data:image/png;base64,<base64_image>。
格式支持：jpeg、png、webp、bmp、tiff、gif 
宽高比（宽/高）范围：[1/16, 16]
大小：不超过10MB
总像素：不超过 6000x6000=36000000 px （对单张图宽度和高度的像素乘积限制，而不是对宽度或高度的单独值进行限制）
最多支持传入 14 张参考图。
'''
image_url = "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_5_imageToimage.png"
imagesResponse = client.images.generate( # 图生图
    # Replace with Model ID
    model="doubao-seedream-4-5-251128",
    prompt="保持模特姿势和液态服装的流动形状不变。将服装材质从银色金属改为完全透明的清水（或玻璃）。透过液态水流，可以看到模特的皮肤细节。光影从反射变为折射。",
    image=image_url,
    size="4K",
    response_format="url",
    watermark=False,
    seed=random.randint(0, 1000000000)
)

print(imagesResponse.data[0].url)
res = requests.get(imagesResponse.data[0].url)
with open("doubao_generate_image_by_image.png", "wb") as f:
    f.write(res.content)