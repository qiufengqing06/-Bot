"""
Basic commands: ping, help, status, cleanup
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger

from nonebot_agent.config import config
from nonebot_agent.utils.media_handler import cleanup_expired_images


# /ping command
ping = on_command("ping", priority=5, block=True)

@ping.handle()
async def handle_ping():
    """Test if the bot is online."""
    await ping.finish(f"pong! 🤖 Agent 运行正常 ✓ (Multimodal {config.IS_MULTIMODAL_MODEL}, {config.LLM_MODEL})")


# /help command
help_cmd = on_command("help", aliases={"帮助", "?"}, priority=5, block=True)

@help_cmd.handle()
async def handle_help():
    """Show help information."""
    help_text = """🤖 NoneBot Agent 帮助

📋 使用方式：
  @机器人 + 消息 - 聊天模式
  @机器人 /问题 - 专业模式

  私聊直接对话，群聊中开启自由聊天模式可不用@，否则必须@机器人
  通过命令/自由聊天 开 /自由聊天模式 关 进行开关

💡 示例：
  @机器人 吃了吗？吃的什么？好吃吗？多吃点长胖点
  @机器人 /帮我搜索一下最近的新闻
  @机器人 [图片] 这是什么

🔧 命令：
  /ping - 测试机器人是否在线
  /help - 显示此帮助信息
  /status - 显示机器人状态
  /画图 星际穿越，黑洞，黑洞里冲出一辆快支离破碎的复古列车，抢视觉冲击力，电影大片，末日既视感，动感，对比色，oc渲染，光线追踪，动态模糊，景深，超现实主义，深蓝，画面通过细腻的丰富的色彩层次塑造主体与场景，质感真实，暗黑风背景的光影效果营造出氛围，整体兼具艺术幻想感，夸张的广角透视效果，耀光，反射，极致的光影，强引力，吞噬（支持尺寸指定，默认4k）
    或是：
    请修改这张图，要求……[图片]
  /情绪 - 查看当前情绪状态
  /设置情绪 - 设置情绪（仅主人）
  /自由聊天 - 开关群聊自由聊天模式（仅管理员）
  /重启bot - 重启机器人（仅主人）

✨ 特性：
  - 双模式对话（聊天/专业）
  - 多模态理解（图片识别）
  - AI画图（文生图/图生图）
  - 长期记忆（记住你说过的话）
  - 群聊记录（记住群里的对话）
  - 网络搜索（获取实时信息）
  - 发送抖音或B站视频分享链接可爬取视频发送给你
  """
    await help_cmd.finish(help_text)


# /status command
status = on_command("status", aliases={"状态"}, priority=5, block=True)

@status.handle()
async def handle_status(bot: Bot):
    """Show bot status."""
    bot_info = await bot.get_login_info()
    nickname = bot_info.get("nickname", "未知")
    user_id = bot_info.get("user_id", "未知")
    
    status_text = f"""📊 机器人状态

🤖 昵称: {nickname}
🆔 QQ号: {user_id}
✅ 状态: 运行中
🧠 LLM: {config.LLM_MODEL} (ISMULTIMODEL {config.IS_MULTIMODAL_MODEL})
🔍 嵌入: qwen2.5-vl-embedding/text-embedding-v4
💾 记忆: MySQL + Chroma
👁 视觉：{config.VISION_MODEL}
"""

    await status.finish(status_text)


# /cleanup command
cleanup_cmd = on_command("cleanup", aliases={"清理"}, priority=5, block=True)

@cleanup_cmd.handle()
async def handle_cleanup():
    """Manually trigger image cleanup."""
    deleted = cleanup_expired_images()
    await cleanup_cmd.finish(f"🧹 已清理 {deleted} 个过期图片文件")
