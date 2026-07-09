import re
import os
import json
import time
import logging
import subprocess
import requests
from DrissionPage import ChromiumPage, ChromiumOptions

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BilibiliDownloader:
    def __init__(self, base_dir="../../data/videos"):
        """
        初始化下载器
        :param base_dir: 基础保存目录
        """
        self.base_dir = base_dir
        # 定义三个子目录：纯视频、纯音频、合并后的成品
        self.video_temp_dir = os.path.join(base_dir, "temp_video")
        self.audio_temp_dir = os.path.join(base_dir, "temp_audio")
        self.output_dir = os.path.join(base_dir, "")

        # 【核心修复】初始化时直接创建所有必要的目录
        self._init_dirs()

        # 配置浏览器
        co = ChromiumOptions()
        co.set_local_port(9223)
        co.set_argument('--no-sandbox')
        co.mute(True)
        # 建议设置 UserData 以保存登录状态（B站不登录只能下载低画质）
        co.set_user_data_path(os.path.join(os.path.dirname(__file__), 'bili_browser_data'))
        self.page = ChromiumPage(co)
        self.session = requests.Session()

    def _init_dirs(self):
        """确保目录存在，防止 FFmpeg 报错 No such file or directory"""
        for path in [self.video_temp_dir, self.audio_temp_dir, self.output_dir]:
            if not os.path.exists(path):
                os.makedirs(path)
                logging.info(f"已自动创建目录: {path}")

    def sanitize_filename(self, filename):
        """
        深度清洗文件名
        1. 解决乱码问题
        2. 解决 Windows 非法字符问题
        """
        # 去除 HTML 标签
        filename = re.sub(r'<[^>]+>', '', filename)
        # 替换 Windows 非法字符
        filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
        # 去除换行符和首尾空格
        filename = filename.replace('\n', '').replace('\r', '').strip()
        # 限制长度
        return filename[:50]

    def merge_video_audio(self, video_path, audio_path, output_path):
        """
        使用 FFmpeg 合并音视频
        """
        if not os.path.exists(video_path) or not os.path.exists(audio_path):
            logging.error("合并失败：源文件缺失")
            return False

        # 如果输出文件已存在，先删除，防止 ffmpeg 询问覆盖卡住
        if os.path.exists(output_path):
            os.remove(output_path)

        logging.info("正在合并音视频 (FFmpeg)...")

        # 构建命令：视频流拷贝，音频流拷贝，不重新编码，速度最快
        cmd = [
            'ffmpeg', '-y',  # -y 自动覆盖
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-strict', 'experimental',
            output_path
        ]

        try:
            # 使用 subprocess 调用，隐藏控制台窗口
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"合并成功！文件已保存至: {output_path}")

            # 合并成功后清理临时文件
            os.remove(video_path)
            os.remove(audio_path)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg 合并出错: {e}")
            return False
        except FileNotFoundError:
            logging.error("未找到 ffmpeg 命令，请确保已安装 FFmpeg 并添加到环境变量 PATH 中")
            return False

    def download(self, url):
        try:
            logging.info(f"正在访问: {url}")
            self.page.get(url)

            # 等待 Bilibili 播放器加载配置 (window.__playinfo__)
            # B站比较特殊，不一定非要监听 response，直接从页面源码提取 JS 对象更稳
            time.sleep(3)

            html_content = self.page.html

            # 1. 提取视频标题
            title_match = re.search(r'<h1[^>]*title="([^"]+)"', html_content)
            # 如果 h1 没找到，尝试 title 标签
            if not title_match:
                title_match = re.search(r'<title>(.*?)</title>', html_content)

            raw_title = title_match.group(1) if title_match else f"bili_{int(time.time())}"
            # 清洗标题：去除 "_哔哩哔哩" 后缀
            raw_title = re.sub(r'_哔哩哔哩.*', '', raw_title)
            safe_title = self.sanitize_filename(raw_title)

            logging.info(f"解析到标题: {safe_title}")

            # 2. 提取 window.__playinfo__ JSON 数据
            # 这是 B站前端存放视频流地址的标准位置，比正则搜 baseUrl 更稳健
            playinfo_match = re.search(r'window.__playinfo__=(.*?)</script>', html_content)
            if not playinfo_match:
                logging.error("未找到视频流信息 (__playinfo__)")
                return

            play_info = json.loads(playinfo_match.group(1))

            # 获取 dash 格式流媒体 (通常包含 video 和 temp_audio 数组)
            dash_data = play_info.get('data', {}).get('dash', {})

            if not dash_data:
                logging.error("未找到 DASH 流媒体数据")
                return

            # 获取第一个视频流 (通常默认是最高画质，或者需要遍历 id 判断)
            video_url = dash_data['video'][0]['baseUrl']
            # 获取第一个音频流
            audio_url = dash_data['audio'][0]['baseUrl']

            # 3. 准备 Request Headers
            # 必须带 Referer，否则 403 Forbidden
            cookies = {item['name']: item['value'] for item in self.page.cookies()}
            headers = {
                "User-Agent": self.page.user_agent,
                "Referer": url,  # 关键！
                "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()])
            }

            # 4. 下载逻辑
            v_path = os.path.join(self.video_temp_dir, f"{safe_title}_video.m4s")
            a_path = os.path.join(self.audio_temp_dir, f"{safe_title}_audio.m4s")
            final_path = os.path.join(self.output_dir, f"{safe_title}.mp4")

            # 下载视频
            logging.info("正在下载视频流...")
            with self.session.get(video_url, headers=headers, stream=True) as r:
                r.raise_for_status()
                with open(v_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # 下载音频
            logging.info("正在下载音频流...")
            with self.session.get(audio_url, headers=headers, stream=True) as r:
                r.raise_for_status()
                with open(a_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # 5. 合并
            self.merge_video_audio(v_path, a_path, final_path)

        except Exception as e:
            logging.error(f"处理出错: {e}")
            import traceback
            logging.error(traceback.format_exc())
        finally:
            self.page.quit()


# if __name__ == "__main__":
#     # 替换成你要下载的 BV 号链接
#     url = 'https://www.bilibili.com/video/BV1fv6mBNEXj/?spm_id_from=333.1007.tianma.1-2-2.click&vd_source=65aa3291130d8eba0ecbc6253ebd7a71'
#
#     # 实例化并运行
#     # 文件默认会保存在当前目录下的 data/videos 文件夹内
#     downloader = BilibiliDownloader()
#     downloader.download(url)