"""
Video Download Plugin
NoneBot2 plugin for automatically detecting and downloading videos from Douyin and Bilibili.
Supports both private chat and group chat (doesn't require @mention).
"""
import asyncio
import re
import json
import os
from typing import Optional, Dict, Tuple

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent,
    Message, MessageSegment
)
from nonebot.log import logger
from nonebot.exception import StopPropagation

from nonebot_agent.config import config
from nonebot_agent.utils.address_qqdocurl import extract_bilibili_url_from_card
from nonebot_agent.utils.url_safety import UnsafeURLError, ensure_public_http_url

# Log plugin load
logger.info("[VideoDownload] Plugin loaded!")


# ============ URL Safety Helpers ============

def _safe_video_url(url: str) -> Optional[str]:
    try:
        return ensure_public_http_url(url)
    except UnsafeURLError as e:
        logger.warning(f"[VideoDownload] Rejected unsafe video URL: {url!r}, reason: {e}")
        return None


# ============ Link Detection Functions ============

def detect_douyin_link(text: str) -> Optional[str]:
    """
    Detect Douyin share link in text.
    
    Patterns:
    - Direct URL: https://v.douyin.com/xxx/
    - Share text format: contains v.douyin.com URL
    
    Args:
        text: Message text content
        
    Returns:
        The share text containing the link if found, None otherwise
    """
    if not text:
        return None
    
    # Check for douyin URL pattern
    douyin_pattern = re.compile(r'https?://v\.douyin\.com/[a-zA-Z0-9]+/?')
    match = douyin_pattern.search(text)
    if match and _safe_video_url(match.group(0)):
        # Return the full text for DouyinDownloader which extracts URL internally
        logger.info(f"[VideoDownload] Detected Douyin link in: {text[:50]}...")
        return text
    
    return None


def detect_bilibili_card(raw_message: str) -> Optional[Dict]:
    """
    Detect Bilibili share card in message.
    
    Bilibili videos are typically shared as QQ mini-app cards with CQ:json format.
    
    Args:
        raw_message: Raw message string (may contain CQ codes)
        
    Returns:
        Dict with card info if found, None otherwise
    """
    if not raw_message:
        return None
    
    # Check for CQ:json with Bilibili appid
    if "[CQ:json" not in raw_message:
        return None
    
    # Try to parse the JSON card
    try:
        json_match = re.search(r'\[CQ:json,data=(.*?)\]', raw_message)
        if not json_match:
            return None
        
        json_str = json_match.group(1)
        # Handle HTML entity encoding (&#44; for comma)
        json_str = json_str.replace('&#44;', ',')
        json_str = json_str.replace('&#91;', '[')
        json_str = json_str.replace('&#93;', ']')
        json_str = json_str.replace('&amp;', '&')
        
        parsed_json = json.loads(json_str)
        
        # Check if it's a Bilibili card
        meta = parsed_json.get("meta", {})
        detail = meta.get("detail_1", {})
        
        if detail.get("appid") == "1109937557":  # Bilibili mini-app ID
            qqdocurl = detail.get("qqdocurl", "")
            if qqdocurl:
                # Clean URL
                clean_url = qqdocurl.replace("\\/", "/").replace("\\", "")
                safe_url = _safe_video_url(clean_url)
                if not safe_url:
                    return None

                logger.info(f"[VideoDownload] Detected Bilibili card: {clean_url[:50]}...")
                return {
                    "title": detail.get("title", "哔哩哔哩"),
                    "desc": detail.get("desc", ""),
                    "url": safe_url
                }
    except json.JSONDecodeError as e:
        logger.debug(f"[VideoDownload] JSON decode error: {e}")
    except Exception as e:
        logger.debug(f"[VideoDownload] Card detection error: {e}")
    
    return None


def detect_bilibili_url(text: str) -> Optional[str]:
    """
    Detect direct Bilibili URLs in plain text.
    
    Patterns:
    - Full BV URLs: https://www.bilibili.com/video/BVxxx
    - Short links: https://b23.tv/xxx
    
    Args:
        text: Message text content
        
    Returns:
        The matched URL if found, None otherwise
    """
    if not text:
        return None
    
    # Pattern for full BV URLs
    bv_pattern = re.compile(r'https?://(?:www\.)?bilibili\.com/video/BV[a-zA-Z0-9]+/?')
    match = bv_pattern.search(text)
    if match:
        url = match.group(0)
        if _safe_video_url(url):
            logger.info(f"[VideoDownload] Detected Bilibili BV URL: {url}")
            return url
    
    # Pattern for short links
    short_pattern = re.compile(r'https?://b23\.tv/[a-zA-Z0-9]+/?')
    match = short_pattern.search(text)
    if match:
        url = match.group(0)
        if _safe_video_url(url):
            logger.info(f"[VideoDownload] Detected Bilibili short link: {url}")
            return url
    
    return None


# ============ Async Download Wrappers ============

async def download_douyin_video(share_text: str) -> Dict:
    """
    Download Douyin video in a thread pool (browser automation is blocking).
    
    Args:
        share_text: Text containing Douyin share link
        
    Returns:
        Result dict with status, message, file_path, title
    """
    from nonebot_agent.utils.douyin_spider import DouyinDownloader

    url_match = re.search(r'https?://\S+', share_text or "")
    if not url_match or not _safe_video_url(url_match.group(0)):
        return {
            "status": "failed",
            "message": "拒绝下载不安全或无效的抖音链接",
            "file_path": None,
            "title": None
        }
    
    def _download():
        downloader = None
        try:
            downloader = DouyinDownloader(save_dir=config.VIDEO_DOWNLOAD_DIR, headless=True)
            result = downloader.download(share_text)
            return result
        except Exception as e:
            logger.error(f"[VideoDownload] Douyin download error: {e}")
            return {
                "status": "failed",
                "message": f"下载失败: {str(e)}",
                "file_path": None,
                "title": None
            }
        finally:
            if downloader:
                downloader.close()
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _download)
    return result


async def download_bilibili_video(url: str) -> Dict:
    """
    Download Bilibili video in a thread pool (browser automation is blocking).
    
    Args:
        url: Bilibili video URL (can be short link like b23.tv)
        
    Returns:
        Result dict with status, message, file_path, title
    """
    from nonebot_agent.utils.bilibili_spider import BilibiliDownloader
    import httpx

    safe_url = _safe_video_url(url)
    if not safe_url:
        return {
            "status": "failed",
            "message": "拒绝下载不安全或无效的 B站链接",
            "file_path": None,
            "title": None
        }
    
    def _download():
        downloader = None
        try:
            # First resolve short URL if needed
            real_url = safe_url
            if "b23.tv" in safe_url:
                try:
                    with httpx.Client(timeout=10.0) as client:
                        response = client.get(safe_url, follow_redirects=True)
                        resolved_url = str(response.url)
                        checked_url = _safe_video_url(resolved_url)
                        if not checked_url:
                            return {
                                "status": "failed",
                                "message": "短链跳转到了不安全地址，已拒绝下载",
                                "file_path": None,
                                "title": None
                            }
                        real_url = checked_url
                        logger.info(f"[VideoDownload] Resolved B站短链: {real_url}")
                except Exception as e:
                    logger.warning(f"[VideoDownload] Failed to resolve short URL: {e}")
            
            downloader = BilibiliDownloader(base_dir=config.VIDEO_DOWNLOAD_DIR)
            result = downloader.download(real_url)
            return result
        except Exception as e:
            logger.error(f"[VideoDownload] Bilibili download error: {e}")
            return {
                "status": "failed",
                "message": f"下载失败: {str(e)}",
                "file_path": None,
                "title": None
            }
        finally:
            if downloader:
                downloader.close()
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _download)
    return result


# ============ Message Handler ============

# Priority 5 (higher than agent_chat at 10), block=False to let non-video messages through
video_download_handler = on_message(priority=5, block=False)

@video_download_handler.handle()
async def handle_video_link(bot: Bot, event: MessageEvent):
    """
    Handle messages that may contain video links.
    Automatically detects and downloads videos from Douyin and Bilibili.
    """
    logger.debug(f"[VideoDownload] Handler triggered, checking message...")
    
    # Check if feature is enabled
    if not config.VIDEO_DOWNLOAD_ENABLED:
        logger.debug("[VideoDownload] Feature disabled, skipping")
        return
    
    # Get raw message for CQ code parsing
    raw_message = str(event.message)
    
    # Extract text content
    text_content = ""
    for seg in event.message:
        if seg.type == "text":
            text_content += seg.data.get("text", "")
    
    # Try to detect video links
    douyin_text = detect_douyin_link(text_content)
    bilibili_card = detect_bilibili_card(raw_message)
    bilibili_url = detect_bilibili_url(text_content)
    
    # No video link detected, let message pass through to agent
    if not douyin_text and not bilibili_card and not bilibili_url:
        logger.debug("[VideoDownload] No video link detected, passing to next handler")
        return  # Just return, don't block, agent_chat will handle it
    
    # Log detection
    if isinstance(event, GroupMessageEvent):
        logger.info(f"[VideoDownload] Video link detected in group {event.group_id} from {event.get_user_id()}")
    else:
        logger.info(f"[VideoDownload] Video link detected in private chat from {event.get_user_id()}")
    
    # Send processing message
    await bot.send(event, "🎬 检测到视频链接，正在下载中...")
    
    result = None
    platform = ""
    
    try:
        if douyin_text:
            platform = "抖音"
            result = await download_douyin_video(douyin_text)
        elif bilibili_card:
            platform = "B站"
            result = await download_bilibili_video(bilibili_card["url"])
        elif bilibili_url:
            platform = "B站"
            result = await download_bilibili_video(bilibili_url)
        
        if result and result.get("status") == "success":
            file_path = result.get("file_path")
            title = result.get("title", "视频")
            
            if file_path and os.path.exists(file_path):
                # Send success message
                await bot.send(event, f"✅ {platform}视频下载完成：{title}")
                
                # Send video file
                try:
                    video_segment = MessageSegment.video(f"file:///{file_path}")
                    await bot.send(event, video_segment)
                    logger.info(f"[VideoDownload] Successfully sent video: {file_path}")
                except Exception as e:
                    logger.error(f"[VideoDownload] Failed to send video: {e}")
                    await bot.send(event, f"❌ 视频发送失败: {str(e)}")
            else:
                await bot.send(event, f"❌ 视频文件不存在")
        else:
            error_msg = result.get("message", "未知错误") if result else "下载失败"
            await bot.send(event, f"❌ {platform}视频下载失败: {error_msg}")
            
    except Exception as e:
        logger.error(f"[VideoDownload] Error processing video: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await bot.send(event, f"❌ 视频处理失败: {str(e)}")
    
    # Block message from reaching agent_chat by raising StopPropagation
    logger.info("[VideoDownload] Stopping propagation to prevent agent_chat response")
    raise StopPropagation()
