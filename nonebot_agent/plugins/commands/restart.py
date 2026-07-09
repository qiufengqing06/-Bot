"""
Bot restart command: /重启bot
"""
import asyncio
import os as _os

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger

from nonebot_agent.config import config


# /重启bot command - restart the bot (only master can use)
restart_cmd = on_command("重启bot", aliases={"restart", "重启"}, priority=5, block=True)

@restart_cmd.handle()
async def handle_restart(bot: Bot, event: MessageEvent):
    """
    Restart the bot process.
    
    Only the master QQ (configured in .env) can use this command.
    The bot will exit and rely on external process manager to restart.
    """
    user_id = event.get_user_id()
    
    # Check if master QQ is configured
    if not config.MASTER_QQ:
        await restart_cmd.finish("❌ 未配置主人QQ号，无法使用此命令\n请在 .env 文件中设置 MASTER_QQ")
        return
    
    # Check if user is the master
    if user_id != config.MASTER_QQ:
        await restart_cmd.finish("❌ 只有主人才能使用此命令")
        return
    
    logger.info(f"[Agent] Bot restart requested by master {user_id}")
    
    # Send confirmation message
    await restart_cmd.send("🔄 正在重启 Bot...")
    
    # Give time for the message to be sent
    await asyncio.sleep(1)
    
    # Use os._exit() to force exit without triggering asyncio cleanup issues
    # External manager (like systemd/supervisor) should restart the bot
    logger.info("[Agent] Bot is shutting down for restart...")
    _os._exit(0)
