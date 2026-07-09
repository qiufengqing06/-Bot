"""
Webpage Reading Tool
Read and parse webpage content.
"""
from langchain.tools import tool
import requests
from bs4 import BeautifulSoup

from nonebot_agent.utils.url_safety import UnsafeURLError, ensure_public_http_url


@tool(description="This tool can analysis web link and return the detailed content of it.")
def read_webpage(url: str) -> str:
    """Read the content of a webpage."""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        safe_url = ensure_public_http_url(url)
        response = requests.get(safe_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 检测并设置正确的编码
        response.encoding = response.apparent_encoding

        # 使用BeautifulSoup解析内容
        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除script和style标签
        for script in soup(["script", "style"]):
            script.decompose()

        # 提取文本内容
        text_content = soup.get_text()

        # 清理多余的空白字符
        clean_text = ' '.join(text_content.split())

        # 限制长度避免太长
        if len(clean_text) > 5000:
            clean_text = clean_text[:5000] + "... [内容已截断]"

        return clean_text
    except UnsafeURLError as e:
        return f"URL rejected: {str(e)}"
    except Exception as e:
        return f"Error fetching webpage: {str(e)}"
