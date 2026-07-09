"""
Media Handler Module
Handle image/video/file download, storage, and base64 conversion.
Also provides cleanup functionality for expired media files.
"""
import os
import base64
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from nonebot.log import logger

from nonebot_agent.config import config


def ensure_image_dir() -> Path:
    """Ensure the image storage directory exists."""
    image_dir = Path(config.IMAGE_STORAGE_DIR)
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir


def generate_filename(url: str, extension: str = ".jpg") -> str:
    """
    Generate a unique filename based on URL hash and timestamp.
    
    Args:
        url: Original image URL
        extension: File extension
        
    Returns:
        Unique filename
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{url_hash}{extension}"


async def download_image(url: str, timeout: int = 30) -> Optional[bytes]:
    """
    Download image from URL.
    
    Args:
        url: Image URL
        timeout: Download timeout in seconds
        
    Returns:
        Image bytes or None if failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.warning(f"[MediaHandler] Failed to download image: HTTP {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"[MediaHandler] Download timeout for: {url}")
        return None
    except Exception as e:
        logger.error(f"[MediaHandler] Download error: {e}")
        return None


async def download_and_save_image(url: str, custom_name: Optional[str] = None) -> Optional[str]:
    """
    Download image from URL and save to local storage.
    
    Args:
        url: Image URL
        custom_name: Optional custom filename
        
    Returns:
        Local file path or None if failed
    """
    # Ensure directory exists
    image_dir = ensure_image_dir()
    
    # Download image
    image_data = await download_image(url)
    if not image_data:
        return None
    
    # Determine extension from URL or default to .jpg
    extension = ".jpg"
    if "." in url.split("/")[-1]:
        ext = "." + url.split(".")[-1].split("?")[0].lower()
        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
            extension = ext
    
    # Generate filename
    filename = custom_name or generate_filename(url, extension)
    file_path = image_dir / filename
    
    # Save to file
    try:
        with open(file_path, "wb") as f:
            f.write(image_data)
        logger.info(f"[MediaHandler] Saved image to: {file_path}")
        return str(file_path)
    except Exception as e:
        logger.error(f"[MediaHandler] Failed to save image: {e}")
        return None


def image_to_base64(file_path: str) -> Optional[str]:
    """
    Convert local image file to base64 data URI.
    
    Args:
        file_path: Path to image file
        
    Returns:
        Base64 data URI string or None if failed
    """
    try:
        with open(file_path, "rb") as f:
            image_data = f.read()
        
        # Determine MIME type from extension
        extension = Path(file_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime_type = mime_types.get(extension, "image/jpeg")
        
        # Encode to base64
        base64_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"
    except Exception as e:
        logger.error(f"[MediaHandler] Failed to convert image to base64: {e}")
        return None


def image_file_to_base64_raw(file_path: str) -> Optional[str]:
    """
    Convert local image file to raw base64 string (without data URI prefix).
    
    Args:
        file_path: Path to image file
        
    Returns:
        Raw base64 string or None if failed
    """
    try:
        with open(file_path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        logger.error(f"[MediaHandler] Failed to convert image to base64: {e}")
        return None


def cleanup_expired_images(retention_days: Optional[int] = None) -> int:
    """
    Clean up images older than retention period.
    
    Args:
        retention_days: Number of days to keep images (default from config)
        
    Returns:
        Number of files deleted
    """
    retention_days = retention_days or config.IMAGE_RETENTION_DAYS
    image_dir = Path(config.IMAGE_STORAGE_DIR)
    
    if not image_dir.exists():
        return 0
    
    cutoff_time = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    
    for file_path in image_dir.iterdir():
        if file_path.is_file():
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"[MediaHandler] Deleted expired image: {file_path}")
            except Exception as e:
                logger.error(f"[MediaHandler] Failed to delete {file_path}: {e}")
    
    if deleted_count > 0:
        logger.info(f"[MediaHandler] Cleaned up {deleted_count} expired images")
    
    return deleted_count


def get_image_info(file_path: str) -> Optional[dict]:
    """
    Get image file information.
    
    Args:
        file_path: Path to image file
        
    Returns:
        Dict with file info or None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None
        
        stat = path.stat()
        return {
            "path": str(path.absolute()),
            "filename": path.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except Exception as e:
        logger.error(f"[MediaHandler] Failed to get image info: {e}")
        return None
