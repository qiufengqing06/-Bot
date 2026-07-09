import base64
import csv
import os

import dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

dotenv.load_dotenv()

# 向量数据库持久化目录
PERSIST_DIR = "../../data/chroma"
COLLECTION_NAME = "images_description"

client = OpenAI(
    api_key=os.getenv("QIANWEN_API_KEY"),
    base_url=os.getenv("QIANWEN_API_URL")
)

# 读取文件夹下所有图片文件
image_folder = "../../data/images/stickers"
image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')  # 支持的图片格式

# 获取文件夹中所有图片文件的路径
image_files = []
for file in os.listdir(image_folder):
    if file.lower().endswith(image_extensions):
        image_files.append(file)

# 按文件名排序
image_files.sort()
# print(urls)
des_demo = ("一张粉色头发动漫角色的表情包。图片上的文字写着‘你是傻瓜！你也是傻瓜！指指点点’。"
            "这是一张充满嘲讽意味但又有点可爱的图片，用于指责对方说了蠢话，或者当对方说你是"
            "笨蛋时的有力回击。表示鄙视、嘲笑、互相指责、指指点点。")

# 将本地图片转换为base64格式
def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 读取CSV文件
def read_csv_file(csv_path):
    """读取CSV文件，返回包含已有数据的列表"""
    if not os.path.exists(csv_path):
        # 如果文件不存在，创建并写入表头
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['description', 'url']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        return []

    with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)

# 写入CSV文件
def write_to_csv(csv_path, image_url, description):
    """向CSV文件追加一行数据"""
    # 检查文件是否存在，不存在则创建并写入表头
    file_exists = os.path.exists(csv_path)

    with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['description', 'url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            'description': description,
            'url': image_url
        })

def get_image_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.jpg' or ext == '.jpeg':
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.gif':
        return 'image/gif'
    elif ext == '.webp':
        return 'image/webp'
    else:
        # 默认使用jpeg
        return 'image/jpeg'

# 读取现有的CSV文件
csv_file_path = "../../data/images/stickers/images_description.csv"
existing_data = read_csv_file(csv_file_path)

# 创建一个集合来存储已处理的图片名，避免重复处理
processed_images = {row['url'] for row in existing_data}

for url in image_files:
    full_path = "../../data/images/stickers/" + url

    # 检查图片是否已经处理过
    if url in processed_images:
        print(f"图片 {url} 已经处理过，跳过...")
        continue

    print(f"正在处理: {url}")

    try:
        base64_image = encode_image_to_base64(full_path)
        mime_type = get_image_mime_type(full_path)

        completion = client.chat.completions.create(
            model="qwen3-vl-plus",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            },
                        },
                        {"type": "text", "text": f"请你仿照如下示例对图片进行描述，示例：{des_demo}"},
                    ],
                },
            ],
        )
        description = completion.choices[0].message.content
        print(description)

        # 将结果写入CSV文件
        write_to_csv(csv_file_path, url, description)


    except FileNotFoundError:
        print(f"文件不存在: {full_path}")
        continue
    except Exception as e:
        print(f"处理图片 {url} 时出错: {e}")
        continue


print(f"所有描述已保存到 {csv_file_path}")
