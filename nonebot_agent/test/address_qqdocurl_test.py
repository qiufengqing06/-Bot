"""
Bilibili URL Resolver Module
Handle Bilibili share card messages and resolve the actual video URL from qqdocurl.
"""
import json
import re
from typing import Dict, Optional, Tuple
from nonebot.log import logger
import httpx


async def extract_bilibili_url_from_card(card_message: str) -> Optional[Dict[str, str]]:
    """
    从B站分享卡片消息中提取视频URL

    Args:
        card_message: 包含B站分享卡片的完整消息字符串

    Returns:
        包含标题、描述和真实URL的字典，如果无法解析则返回None
    """
    try:
        # 检查消息是否包含JSON结构
        json_match = re.search(r'\[CQ:json,data=(.*)\]', card_message)
        if not json_match:
            logger.warning("[BilibiliResolver] No JSON data found in message")
            return None

        json_str = json_match.group(1)
        # 处理可能的HTML实体编码
        json_str = json_str.replace('&#44;', ',')

        # 解析JSON数据
        parsed_json = json.loads(json_str) if isinstance(json_str, str) else json_str

        # 检查是否为B站分享卡片
        meta = parsed_json.get("meta", {})
        detail = meta.get("detail_1", {})

        if detail.get("appid") != "1109937557":  # B站小程序ID
            logger.info("[BilibiliResolver] Not a Bilibili share card")
            return None

        # 提取基本信息
        title = detail.get("title", "")
        desc = detail.get("desc", "")
        url = detail.get("url", "")
        qqdocurl = detail.get("qqdocurl", "")

        if not qqdocurl:
            logger.warning("[BilibiliResolver] No qqdocurl found in Bilibili share card")
            return None

        # 清理URL，移除转义字符
        clean_url = qqdocurl.replace("\\/", "/").replace("\\", "")

        # 尝试解析短链接获取真实URL
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(clean_url, follow_redirects=True)
                real_url = str(response.url)

                # 检查是否为B站相关链接
                if "bilibili.com" in real_url or "b23.tv" in real_url:
                    result = {
                        "title": title,
                        "desc": desc,
                        "original_url": clean_url,
                        "real_url": real_url,
                        "is_bilibili_video": True
                    }
                    logger.info(f"[BilibiliResolver] Successfully resolved Bilibili video: {real_url}")
                    return result
                else:
                    logger.warning(f"[BilibiliResolver] Resolved URL is not a Bilibili video: {real_url}")
                    return {
                        "title": title,
                        "desc": desc,
                        "original_url": clean_url,
                        "real_url": real_url,
                        "is_bilibili_video": False
                    }
        except Exception as e:
            logger.error(f"[BilibiliResolver] Error resolving Bilibili short URL: {e}")
            return {
                "title": title,
                "desc": desc,
                "original_url": clean_url,
                "real_url": None,
                "is_bilibili_video": False,
                "error": str(e)
            }

    except json.JSONDecodeError as e:
        logger.error(f"[BilibiliResolver] JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"[BilibiliResolver] Unexpected error: {e}")
        return None


def extract_bilibili_url_from_card_sync(card_message: str) -> Optional[Dict[str, str]]:
    """
    同步版本：从B站分享卡片消息中提取视频URL

    Args:
        card_message: 包含B站分享卡片的完整消息字符串

    Returns:
        包含标题、描述和真实URL的字典，如果无法解析则返回None
    """
    try:
        # 检查消息是否包含JSON结构
        json_match = re.search(r'\[CQ:json,data=(.*)\]', card_message)
        if not json_match:
            logger.warning("[BilibiliResolver] No JSON data found in message")
            return None

        json_str = json_match.group(1)
        # 处理可能的HTML实体编码
        json_str = json_str.replace('&#44;', ',')

        # 解析JSON数据
        parsed_json = json.loads(json_str) if isinstance(json_str, str) else json_str

        # 检查是否为B站分享卡片
        meta = parsed_json.get("meta", {})
        detail = meta.get("detail_1", {})

        if detail.get("appid") != "1109937557":  # B站小程序ID
            logger.info("[BilibiliResolver] Not a Bilibili share card")
            return None

        # 提取基本信息
        title = detail.get("title", "")
        desc = detail.get("desc", "")
        url = detail.get("url", "")
        qqdocurl = detail.get("qqdocurl", "")

        if not qqdocurl:
            logger.warning("[BilibiliResolver] No qqdocurl found in Bilibili share card")
            return None

        # 清理URL，移除转义字符
        clean_url = qqdocurl.replace("\\/", "/").replace("\\", "")

        # 尝试解析短链接获取真实URL
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(clean_url, follow_redirects=True)
                real_url = str(response.url)

                # 检查是否为 B站相关链接
                if "bilibili.com" in real_url or "b23.tv" in real_url:
                    result = {
                        "title": title,
                        "desc": desc,
                        "original_url": clean_url,
                        "real_url": real_url,
                        "is_bilibili_video": True
                    }
                    logger.info(f"[BilibiliResolver] Successfully resolved Bilibili video: {real_url}")
                    return result
                else:
                    logger.warning(f"[BilibiliResolver] Resolved URL is not a Bilibili video: {real_url}")
                    return {
                        "title": title,
                        "desc": desc,
                        "original_url": clean_url,
                        "real_url": real_url,
                        "is_bilibili_video": False
                    }
        except Exception as e:
            logger.error(f"[BilibiliResolver] Error resolving Bilibili short URL: {e}")
            return {
                "title": title,
                "desc": desc,
                "original_url": clean_url,
                "real_url": None,
                "is_bilibili_video": False,
                "error": str(e)
            }

    except json.JSONDecodeError as e:
        logger.error(f"[BilibiliResolver] JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"[BilibiliResolver] Unexpected error: {e}")
        return None


async def test_resolver():
    """
    测试函数，用于验证解析功能
    """
    # 测试数据
    test_message = ('[CQ:json,data={"ver":"1.0.0.19"&#44;"prompt":"&#91;QQ小程序&#93;泰拉瑞亚1.4.5正式定档1月27日'
                    '！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！'
                    '"&#44;"config":{"type":"normal"&#44;"width":0&#44;"height":0&#44;"forward":1&#44;"autoSize":0&#44;'
                    '"ctime":1768460574&#44;"token":"ce7573415caa258069b7f54db8136884"}&#44;"needShareCallBack":false&#44;'
                    '"app":"com.tencent.miniapp_01"&#44;"view":"view_8C8E89B49BE609866298ADDFF2DBABA4"&#44;"meta":{"detail_1"'
                    ':{"appid":"1109937557"&#44;"appType":0&#44;"title":"哔哩哔哩"&#44;"desc":"泰拉瑞亚1.4.5正式定档1月27日！！！！！！'
                    '！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！！"&#44;"icon":"http:'
                    '\/\/miniapp.gtimg.cn\/public\/appicon\/432b76be3a548fc128acaa6c1ec90131_200.jpg"&#44;"preview":"https:\/\/'
                    'qq.ugcimg.cn\/v1\/m462moqkddr44geokh4uqbfvd71finpthat6541jronkl1siro4ripj20a1msisa5lh5qr3ckv9hbmvh3butgfsufp'
                    '26q5vkb73aas757rsi4bonl02kl9uo61lptlfh7doav0pg4ralhr62n8sf3a9ho4\/e9vf2tsqr6j29hl2kodb3vahlc"&#44;"url":"m.q.'
                    'qq.com\/a\/s\/1343bdef88b524fcd2d636b1ba36b9af"&#44;"scene":1036&#44;"host":{"uin":3298364424&#44;"nick":"秋风清"'
                    '}&#44;"shareTemplateId":"8C8E89B49BE609866298ADDFF2DBABA4"&#44;"shareTemplateData":{}&#44;"qqdocurl":"https:\/\/'
                    'b23.tv\/g31M4jD?share_medium=android&amp;share_source=qq&amp;bbid=XX6881168E5FE4FC688377CE17987AFA43382&amp;ts='
                    '1768460572448"&#44;"showLittleTail":""&#44;"gamePoints":""&#44;"gamePointsUrl":""&#44;"shareOrigin":0}}}]')
    result = await extract_bilibili_url_from_card(test_message)
    if result:
        print("解析成功:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("解析失败")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_resolver())
