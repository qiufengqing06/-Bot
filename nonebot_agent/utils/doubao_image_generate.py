import os
import random
import logging
from typing import Optional

import dotenv
import requests

dotenv.load_dotenv()

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

base_url = os.getenv("DOUBAO_API_URL")
api_key = os.getenv("DOUBAO_API_KEY")


class ImageGenerator:
    def __init__(self, base_url: str, api_key: str):
        if not base_url or not api_key:
            raise ValueError("请设置 DOUBAO_API_URL 和 DOUBAO_API_KEY 环境变量")
        try:
            from volcenginesdkarkruntime import Ark
            self.client = Ark(
                base_url=base_url,
                api_key=api_key,
            )
        except ImportError:
            logger.error("未安装 volcenginesdkarkruntime，请运行 'pip install volcenginesdkarkruntime' 安装")
            raise
        except Exception as e:
            logger.error(f"初始化 Ark 客户端失败: {e}")
            raise

    def generate_image_from_text(
        self,
        prompt: str,
        model: str = "doubao-seedream-4-5-251128",
        size: str = "4K",
        filename: Optional[str] = None
    ) -> str:
        """
        根据文本生成图片

        Args:
            prompt: 图片描述提示词
            model: 使用的模型ID
            size: 图片尺寸
            filename: 保存文件名，如果不提供则自动生成

        Returns:
            生成的图片URL
        """
        try:
            images_response = self.client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                response_format="url",
                watermark=False
            )

            image_url = images_response.data[0].url
            logger.info(f"文本生成图片成功: {image_url}")

            # 保存图片
            if filename is None:
                filename = f"doubao_generate_image_by_text_{random.randint(1000, 9999)}.png"

            self._download_and_save_image(image_url, filename)
            return image_url

        except Exception as e:
            logger.error(f"文本生成图片失败: {e}")
            raise

    def generate_image_from_image(
        self,
        prompt: str,
        image_url: str,
        model: str = "doubao-seedream-4-5-251128",
        size: str = "4K",
        filename: Optional[str] = None
    ) -> str:
        """
        根据图片和文本生成新图片（图生图）

        Args:
            prompt: 图片描述提示词
            image_url: 参考图片URL
            model: 使用的模型ID
            size: 图片尺寸
            filename: 保存文件名，如果不提供则自动生成

        Returns:
            生成的图片URL
        """
        try:
            images_response = self.client.images.generate(
                model=model,
                prompt=prompt,
                image=image_url,
                size=size,
                response_format="url",
                watermark=False,
                seed=random.randint(0, 1000000000)
            )

            image_url_result = images_response.data[0].url
            logger.info(f"图生图生成成功: {image_url_result}")

            # 保存图片
            if filename is None:
                filename = f"doubao_generate_image_by_image_{random.randint(1000, 9999)}.png"

            self._download_and_save_image(image_url_result, filename)
            return image_url_result

        except Exception as e:
            logger.error(f"图生图生成失败: {e}")
            raise

    def _download_and_save_image(self, image_url: str, filename: str) -> None:
        """下载并保存图片到本地"""
        try:
            res = requests.get(image_url, timeout=30)
            res.raise_for_status()
            
            # 使用基于模块位置的绝对路径
            module_dir = os.path.dirname(os.path.abspath(__file__))
            # 路径: NoneBot_Agent/nonebot_agent/utils -> NoneBot_Agent/data/images/doubao_image_generate
            save_dir = os.path.join(module_dir, "..", "..", "data", "images", "doubao_image_generate")
            save_dir = os.path.normpath(save_dir)
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            save_path = os.path.join(save_dir, filename)
            with open(save_path, "wb") as f:
                f.write(res.content)
            logger.info(f"图片已保存至: {save_path}")

        except requests.RequestException as e:
            logger.error(f"下载图片失败: {e}")
            raise
        except IOError as e:
            logger.error(f"保存图片失败: {e}")
            raise

#
# def main():
#     # 创建图片生成器实例
#     generator = ImageGenerator(base_url, api_key)
#
#     # 示例1: 文生图
#     text_prompt = "充满活力的特写编辑肖像，模特眼神犀利，头戴雕塑感帽子，色彩拼接丰富，眼部焦点锐利，景深较浅，具有Vogue杂志封面的美学风格，采用中画幅拍摄，工作室灯光效果强烈。"
#     try:
#         text_generated_url = generator.generate_image_from_text(
#             prompt=text_prompt,
#             filename="doubao_generate_image_by_text.png"
#         )
#         print(f"文生图结果: {text_generated_url}")
#     except Exception as e:
#         logger.error(f"文生图过程出错: {e}")
#
#     # 示例2: 图生图
#     image_url = "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_5_imageToimage.png"
#     image_prompt = "保持模特姿势和液态服装的流动形状不变。将服装材质从银色金属改为完全透明的清水（或玻璃）。透过液态水流，可以看到模特的皮肤细节。光影从反射变为折射。"
#     try:
#         image_generated_url = generator.generate_image_from_image(
#             prompt=image_prompt,
#             image_url=image_url,
#             filename="doubao_generate_image_by_image.png"
#         )
#         print(f"图生图结果: {image_generated_url}")
#     except Exception as e:
#         logger.error(f"图生图过程出错: {e}")
#
#
# if __name__ == "__main__":
#     main()
