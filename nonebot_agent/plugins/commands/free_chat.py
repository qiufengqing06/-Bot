"""
Free chat mode commands: /自由聊天
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.log import logger

from nonebot_agent.plugins.group_settings import (
    is_free_chat_enabled,
    set_group_free_chat,
)


async def check_admin_permission(bot: Bot, group_id: str, user_id: str) -> bool:
    """Check if user is group admin or owner."""
    try:
        member_info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
        role = member_info.get("role", "member")
        return role in ["owner", "admin"]
    except Exception as e:
        logger.error(f"[Agent] Failed to check admin permission: {e}")
        return False


# /自由聊天 command - toggle free chat mode for groups
free_chat_cmd = on_command("自由聊天", aliases={"freechat"}, priority=5, block=True)

@free_chat_cmd.handle()
async def handle_free_chat(bot: Bot, event: MessageEvent):
    """
    Toggle free chat mode for a group.
    
    Usage:
        /自由聊天         - Show current status
        /自由聊天 开      - Enable free chat mode
        /自由聊天 关      - Disable free chat mode
        /自由聊天 概率 50 - Set reply probability to 50%
    """
    # Only works in group chat
    if not isinstance(event, GroupMessageEvent):
        await free_chat_cmd.finish("❌ 此命令仅在群聊中可用")
        return
    
    user_id = event.get_user_id()
    group_id = str(event.group_id)
    
    # Parse command arguments
    args = str(event.message).strip().split()
    # Remove command prefix
    if args and args[0] in ["自由聊天", "/自由聊天", "freechat", "/freechat"]:
        args = args[1:]
    
    # No arguments: show status
    if not args:
        enabled, probability = is_free_chat_enabled(group_id)
        status_emoji = "✅ 开启" if enabled else "❌ 关闭"
        await free_chat_cmd.finish(
            f"💬 自由聊天模式状态\n\n"
            f"状态: {status_emoji}\n"
            f"回复概率: {probability}%\n\n"
            f"使用方法:\n"
            f"  /自由聊天 开 - 开启\n"
            f"  /自由聊天 关 - 关闭\n"
            f"  /自由聊天 概率 50 - 设置回复概率为50%"
        )
        return
    
    # Check admin permission for modifications
    is_admin = await check_admin_permission(bot, group_id, user_id)
    if not is_admin:
        await free_chat_cmd.finish("❌ 仅群主或管理员可以修改此设置")
        return
    
    action = args[0]
    
    # Enable free chat
    if action in ["开", "开启", "on", "enable", "1"]:
        settings = set_group_free_chat(group_id, True, user_id)
        await free_chat_cmd.finish(
            f"✅ 自由聊天模式已开启\n\n"
            f"回复概率: {settings.reply_probability}%\n"
            f"Bot 将会随机参与群聊对话"
        )
        logger.info(f"[Agent] Free chat enabled for group {group_id} by {user_id}")
        return
    
    # Disable free chat
    if action in ["关", "关闭", "off", "disable", "0"]:
        settings = set_group_free_chat(group_id, False, user_id)
        await free_chat_cmd.finish(
            f"❌ 自由聊天模式已关闭\n\n"
            f"Bot 只会响应 @消息"
        )
        logger.info(f"[Agent] Free chat disabled for group {group_id} by {user_id}")
        return
    
    # Set probability
    if action in ["概率", "prob", "probability"]:
        if len(args) < 2:
            await free_chat_cmd.finish("❌ 请指定概率值 (0-100)\n例如: /自由聊天 概率 30")
            return
        
        try:
            prob = int(args[1])
            if prob < 0 or prob > 100:
                raise ValueError("概率必须在 0-100 之间")
            
            # Get current state and update probability
            enabled, _ = is_free_chat_enabled(group_id)
            settings = set_group_free_chat(group_id, enabled, user_id, prob)
            
            await free_chat_cmd.finish(
                f"✅ 回复概率已设置为 {prob}%\n\n"
                f"当前状态: {'开启' if settings.free_chat_enabled else '关闭'}"
            )
            logger.info(f"[Agent] Free chat probability set to {prob}% for group {group_id} by {user_id}")
        except ValueError as e:
            await free_chat_cmd.finish(f"❌ 无效的概率值: {e}")
        return
    
    # Unknown action
    await free_chat_cmd.finish(
        f"❌ 未知操作: {action}\n\n"
        f"使用方法:\n"
        f"  /自由聊天 开 - 开启\n"
        f"  /自由聊天 关 - 关闭\n"
        f"  /自由聊天 概率 50 - 设置回复概率"
    )
