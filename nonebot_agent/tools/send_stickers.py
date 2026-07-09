"""
Sticker Search and Send Tool
Search stickers from Chroma and return special markers for sending.
"""
import os
from typing import List, Optional

import dotenv
from langchain.tools import tool
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from nonebot_agent.config import config

dotenv.load_dotenv()

# 向量数据库配置
PERSIST_DIR = config.CHROMA_PERSIST_DIR
COLLECTION_NAME = "images_description"

# 表情包标记前缀 (用于在 agent_chat.py 中解析)
STICKER_MARKER_PREFIX = "[STICKER:"
STICKER_MARKER_SUFFIX = "]"


def get_sticker_db() -> Chroma:
    """获取表情包 Chroma 数据库实例"""
    embedding = OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=os.getenv("QIANWEN_API_KEY"),
        base_url=os.getenv("QIANWEN_API_URL"),
        check_embedding_ctx_length=False
    )
    
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding,
        persist_directory=PERSIST_DIR
    )


def search_stickers(query: str, k: int = 1) -> List[dict]:
    """
    通过相似度检索 Chroma 数据库中的表情包
    
    Args:
        query: 查询语句，描述想要的表情包类型或情绪
        k: 返回结果数量，默认为 1
        
    Returns:
        包含匹配项的列表，每个元素是一个字典，包含 description、url 和 score
    """
    db = get_sticker_db()
    
    # 执行相似度搜索
    results = db.similarity_search_with_score(query, k=k)
    
    # 提取结果信息
    search_results = []
    for doc, score in results:
        result_item = {
            "description": doc.page_content,
            "url": doc.metadata.get("url", ""),  # 这是文件名
            "score": score  # 相似度分数，值越小表示越相似
        }
        search_results.append(result_item)
    
    return search_results


@tool(description="""搜索表情包数据库，返回多张相关的表情包供你选择。

使用场景：
- 想用表情包来回应用户时，先调用此工具查看有哪些可选的表情包
- 对话氛围轻松，想用表情包增加趣味时

参数：
- query: 描述你想要的表情包类型或情绪

返回：5张相关表情包的描述和URL列表

注意：获取到表情包列表后，请根据当前对话语境选择最合适的一张，然后调用 send_sticker_by_url 工具发送。
""")
def search_stickers_tool(query: str) -> str:
    """
    搜索表情包数据库，返回多张相关表情包供LLM选择
    
    Args:
        query: 描述想要的表情包类型或情绪
        
    Returns:
        包含多张表情包描述和URL的格式化字符串
    """
    try:
        search_results = search_stickers(query, k=5)
        
        if not search_results:
            print(f"[Sticker] No sticker found for query: {query}")
            return "没有找到相关的表情包，请用文字回复。"
        
        # 格式化结果供LLM阅读和选择
        result_text = f"找到 {len(search_results)} 张相关表情包，请选择最合适的一张：\n\n"
        
        for i, item in enumerate(search_results, 1):
            result_text += f"【表情包 {i}】\n"
            result_text += f"描述：{item['description']}\n"
            result_text += f"URL：{item['url']}\n"
            result_text += f"相似度分数：{item['score']:.3f}\n\n"
        
        result_text += "请根据当前对话语境，选择最合适的表情包，然后调用 send_sticker_by_url 工具，传入对应的 URL 来发送。"
        
        print(f"[Sticker] Found {len(search_results)} stickers for query: {query}")
        return result_text
            
    except Exception as e:
        print(f"[Sticker] Error searching sticker: {e}")
        return f"搜索表情包时出错: {str(e)}"


@tool(description="""发送指定的表情包。

使用场景：
- 在调用 search_stickers_tool 获取表情包列表后，选定一张表情包进行发送

参数：
- url: 要发送的表情包的URL（从 search_stickers_tool 返回结果中获取）,示例：sticker (30).jpg

返回：表情包标记，会被自动转换为图片发送给用户

注意：调用此工具后，你可以在回复中添加简短的文字配合表情包。
""")
def send_sticker_by_url(url: str) -> str:
    """
    根据URL发送表情包
    
    Args:
        url: 表情包的URL/文件名
        
    Returns:
        表情包标记字符串，格式为 [STICKER:filename]
    """
    try:
        if not url:
            return "URL不能为空，请提供有效的表情包URL。"
        
        print(f"[Sticker] Sending sticker: {url}")
        
        # 返回特殊标记格式
        return f"{STICKER_MARKER_PREFIX}{url}{STICKER_MARKER_SUFFIX}"
            
    except Exception as e:
        print(f"[Sticker] Error sending sticker: {e}")
        return f"发送表情包时出错: {str(e)}"


def is_sticker_marker(text: str) -> bool:
    """检查文本是否是表情包标记"""
    return STICKER_MARKER_PREFIX in text and STICKER_MARKER_SUFFIX in text


def extract_sticker_filename(marker: str) -> Optional[str]:
    """从表情包标记中提取文件名"""
    if STICKER_MARKER_PREFIX in marker:
        start = marker.find(STICKER_MARKER_PREFIX) + len(STICKER_MARKER_PREFIX)
        end = marker.find(STICKER_MARKER_SUFFIX, start)
        if end > start:
            return marker[start:end]
    return None


def get_sticker_full_path(filename: str) -> str:
    """获取表情包的完整路径"""
    return os.path.join(config.STICKER_STORAGE_DIR, filename)
