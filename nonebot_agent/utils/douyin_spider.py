import re
import os
import time
import logging
import requests
from DrissionPage import ChromiumPage, ChromiumOptions

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DouyinDownloader:
    def __init__(self, save_dir="../../data/videos", headless=False, proxy=None):
        """
        初始化下载器
        :param save_dir: 视频保存目录
        :param headless: 是否使用无头模式
        :param proxy: 代理地址
        """
        self.save_dir = save_dir
        self.proxy = proxy

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        # 初始化浏览器配置
        co = ChromiumOptions()
        co.auto_port()  # 自动分配端口
        co.set_user_data_path(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'browser_data'))
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.mute(True)

        if headless:
            co.headless()

        if self.proxy:
            co.set_proxy(self.proxy)

        # 浏览器启动的健壮性处理
        try:
            self.page = ChromiumPage(co)
        except ValueError as e:
            if "not enough values to unpack" in str(e):
                logging.warning("自动分配端口失败，尝试回退到默认端口 9222...")
                co = ChromiumOptions()
                co.set_local_port(9222)
                co.set_user_data_path(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'browser_data'))
                co.set_argument('--no-sandbox')
                co.set_argument('--disable-dev-shm-usage')
                co.mute(True)
                if headless:
                    co.headless()
                if self.proxy:
                    co.set_proxy(self.proxy)
                self.page = ChromiumPage(co)
            else:
                raise e

        self.session = requests.Session()
        logging.info("DouyinDownloader 初始化完成")

    def _extract_url(self, text):
        # 匹配更广泛的URL字符集：排除空白、引号、尖括号、CJK字符
        # 这样可以处理含 +, #, @, !, ~, *, ', (, ), ; 等特殊字符的URL
        pattern = re.compile(r'https?://[^\s<>"\'\u4e00-\u9fff\uff00-\uffef]+')
        match = pattern.search(text)
        if match:
            # 去除末尾可能是句子标点的字符
            url = match.group(0).rstrip('.,;:!?。，；：！？)）')
            return url
        return None

    def _sanitize_filename(self, filename):
        """清洗文件名"""
        filename = re.sub(r'[\\/:*?"<>|]', '', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        return filename[:100] if len(filename) > 100 else filename

    def _pick_optimal_url(self, video_info):
        """
        【核心修改】智能选择画质
        优先选择 1080p，其次 720p，避免下载 4K/HDR 导致文件过大
        """
        try:
            bit_rate_list = video_info.get("bit_rate", [])

            # 如果列表为空，直接尝试取 play_addr (旧版接口或特殊情况)
            if not bit_rate_list:
                return video_info["play_addr"]["url_list"][0]

            logging.info(f"检测到 {len(bit_rate_list)} 种画质选项，正在筛选 1080p...")

            # 1. 第一轮遍历：寻找 1080p
            for item in bit_rate_list:
                gear = str(item.get("gear_name", "")).lower()
                # 排除 HDR (如果你想要 HDR 也可以去掉这个排除)
                if "1080" in gear and "hdr" not in gear:
                    logging.info(f"已选中画质: {gear} (1080p)")
                    return item["play_addr"]["url_list"][0]

            # 2. 第二轮遍历：寻找 720p (如果没找到 1080p)
            for item in bit_rate_list:
                gear = str(item.get("gear_name", "")).lower()
                if "720" in gear:
                    logging.info(f"未找到1080p，降级选中: {gear} (720p)")
                    return item["play_addr"]["url_list"][0]

            # 3. 兜底：如果上面的都没找到（可能是只有4K，或者只有540p，或者 gear_name 变了）
            # 直接取列表第一个，通常是当前可用的最高画质
            fallback_gear = bit_rate_list[0].get("gear_name", "unknown")
            logging.info(f"未匹配到标准档位，使用默认首选: {fallback_gear}")
            return bit_rate_list[0]["play_addr"]["url_list"][0]

        except Exception as e:
            # 终极兜底：如果解析 bit_rate 结构出错，回退到最原始的地址
            logging.warning(f"画质筛选出错 ({e})，使用默认地址")
            return video_info["play_addr"]["url_list"][0]

    def _extract_from_page_html(self):
        """
        当 aweme/detail API 监听超时时，从页面 HTML 中的嵌入 JSON 提取视频信息。
        尝试顺序：window.__INITIAL_STATE__ → RENDER_DATA → window._ROUTER_DATA
        返回 (video_url, title) 或 (None, None)
        """
        import json
        import urllib.parse

        try:
            html = self.page.html
        except Exception as e:
            logging.warning(f"获取页面HTML失败: {e}")
            return None, None

        # 尝试各种嵌入 JSON 的模式
        patterns = [
            # window.__INITIAL_STATE__ = {...}
            (r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*(?:</script>|window\.)', 'INITIAL_STATE'),
            (r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*$', 'INITIAL_STATE'),
            # RENDER_DATA (URL encoded)
            (r'<script id="RENDER_DATA"[^>]*>([^<]+)</script>', 'RENDER_DATA'),
            # window._ROUTER_DATA = {...}
            (r'window\._ROUTER_DATA\s*=\s*(\{.+?\})\s*;?\s*(?:</script>|window\.)', 'ROUTER_DATA'),
            (r'window\._ROUTER_DATA\s*=\s*(\{.+?\})\s*$', 'ROUTER_DATA'),
        ]

        for pattern, source_name in patterns:
            try:
                match = re.search(pattern, html, re.DOTALL)
                if not match:
                    continue

                raw = match.group(1)
                logging.info(f"从 {source_name} 提取到嵌入数据，尝试解析...")

                # RENDER_DATA 是 URL encoded
                if source_name == 'RENDER_DATA':
                    try:
                        raw = urllib.parse.unquote(raw)
                    except Exception:
                        continue

                data = json.loads(raw)

                # 递归搜索视频信息
                video_url, title = self._find_video_in_data(data)
                if video_url:
                    logging.info(f"从 {source_name} 成功提取视频URL")
                    return video_url, title

            except (json.JSONDecodeError, Exception) as e:
                logging.debug(f"解析 {source_name} 失败: {e}")
                continue

        return None, None

    def _find_video_in_data(self, data, depth=0):
        """
        递归搜索嵌套 JSON 数据中的视频 URL 和标题。
        返回 (video_url, title) 或 (None, None)
        """
        if depth > 15:
            return None, None

        if isinstance(data, dict):
            # 检查是否是 aweme_detail 结构
            if 'aweme_detail' in data:
                return self._extract_from_aweme(data['aweme_detail'])
            if 'awemeDetail' in data:
                return self._extract_from_aweme(data['awemeDetail'])
            # 检查是否有 video + play_addr 结构
            if 'video' in data and isinstance(data['video'], dict):
                video_obj = data['video']
                play_addr = video_obj.get('play_addr') or video_obj.get('playAddr')
                if play_addr and isinstance(play_addr, dict):
                    url_list = play_addr.get('url_list') or play_addr.get('urlList') or []
                    if url_list:
                        title = data.get('desc', '') or data.get('title', '')
                        return url_list[0], title
            # 递归搜索子项
            for key, value in data.items():
                if key in ('video', 'play_addr', 'playAddr', 'url_list', 'urlList'):
                    continue
                result = self._find_video_in_data(value, depth + 1)
                if result[0]:
                    return result

        elif isinstance(data, list):
            for item in data:
                result = self._find_video_in_data(item, depth + 1)
                if result[0]:
                    return result

        return None, None

    def _extract_from_aweme(self, aweme):
        """从 aweme 对象提取视频URL和标题"""
        if not isinstance(aweme, dict):
            return None, None

        title = aweme.get('desc', '') or aweme.get('title', '')
        video_obj = aweme.get('video', {})
        if not video_obj:
            return None, None

        # 尝试 bit_rate 列表
        bit_rate_list = video_obj.get('bit_rate') or video_obj.get('bitRate') or []
        if bit_rate_list:
            for item in bit_rate_list:
                play_addr = item.get('play_addr') or item.get('playAddr')
                if play_addr:
                    url_list = play_addr.get('url_list') or play_addr.get('urlList') or []
                    if url_list:
                        return url_list[0], title

        # 直接 play_addr
        play_addr = video_obj.get('play_addr') or video_obj.get('playAddr')
        if play_addr:
            url_list = play_addr.get('url_list') or play_addr.get('urlList') or []
            if url_list:
                return url_list[0], title

        return None, None

    def close(self):
        try:
            self.page.quit()
            logging.info("浏览器已关闭")
        except:
            pass

    def download(self, share_text):
        result = {
            "status": "failed",
            "message": "",
            "file_path": None,
            "title": None
        }

        # 1. 提取 URL
        target_url = self._extract_url(share_text)
        print("目标链接:", target_url)
        if not target_url:
            result["message"] = "未找到有效链接"
            return result

        try:
            # 2. 监听并访问
            self.page.listen.start("aweme/detail")
            self.page.get(target_url)

            # 等待数据包 (增加到 20 秒，防止网络慢)
            res_packet = self.page.listen.wait(timeout=20)

            if not res_packet:
                # 监听超时，尝试从页面 HTML 提取
                logging.info("API 监听超时，尝试从页面 HTML 提取视频数据...")
                video_url, raw_title = self._extract_from_page_html()
                
                if not video_url:
                    result["message"] = "获取数据超时或被验证码拦截"
                    return result
                
                # 从 HTML 提取成功，继续处理
                safe_title = self._sanitize_filename(raw_title or f"video_{int(time.time())}")
                file_extension = ".mp4"
                full_filename = safe_title + file_extension
                save_path = os.path.join(self.save_dir, full_filename)
                
                # 跳过 API 解析，直接到下载步骤
                # (video_url 已设置，video_obj 不需要)
            else:
                # 3. 提取数据（从 API 响应）
                json_data = res_packet.response.body
                aweme = json_data.get("aweme_detail", {})

                # 获取标题
                raw_title = aweme.get("desc", f"video_{int(time.time())}")
                safe_title = self._sanitize_filename(raw_title)
                file_extension = ".mp4"
                full_filename = safe_title + file_extension
                save_path = os.path.join(self.save_dir, full_filename)

                # 4. 获取下载链接（调用新的画质选择方法）
                video_obj = aweme.get("video", {})
                if not video_obj:
                    result["message"] = "未解析到视频对象(可能是图文)"
                    return result

                #  - 此处调用解析函数
                video_url = self._pick_optimal_url(video_obj)

            # 5. 检查本地是否已存在
            if os.path.exists(save_path):
                logging.info(f"文件已存在: {save_path}")
                result.update({
                    "status": "success",
                    "message": "文件已存在",
                    "file_path": os.path.abspath(save_path),
                    "title": safe_title
                })
                return result

            # 6. 同步 Cookies 并下载
            cookies = {item['name']: item['value'] for item in self.page.cookies()}
            headers = {
                "User-Agent": self.page.user_agent,
                "Referer": "https://www.douyin.com/",
                "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()])
            }

            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

            logging.info(f"开始下载: {safe_title}")
            with self.session.get(video_url, headers=headers, stream=True, timeout=30, proxies=proxies) as r:
                r.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            # 7. 返回成功结果
            result.update({
                "status": "success",
                "message": "下载完成",
                "file_path": os.path.abspath(save_path),
                "title": safe_title
            })
            return result

        except Exception as e:
            logging.error(f"下载异常: {e}")
            result["message"] = f"系统异常: {str(e)}"
            return result
        finally:
            self.page.listen.stop()


if __name__ == "__main__":
    downloader = DouyinDownloader()
    text = "3.53 复制打开抖音，看看【Y的作品】  https://v.douyin.com/KJum96wcKqU/ :6pm 01/02 iPX:/ O@K.jc "
    res = downloader.download(text)
    print(res)
    downloader.close()
    # print(downloader._extract_url(text))