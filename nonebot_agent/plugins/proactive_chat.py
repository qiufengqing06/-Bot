"""Background proactive chat plugin."""
from __future__ import annotations

import asyncio
import logging

import nonebot
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot

from nonebot_agent.services.proactive_runtime import proactive_service

try:
    from nonebot.log import logger
except Exception:
    logger = logging.getLogger(__name__)


driver = get_driver()
_proactive_task: asyncio.Task | None = None


def _pick_bot() -> Bot | None:
    bots = nonebot.get_bots()
    for bot in bots.values():
        if isinstance(bot, Bot):
            return bot
    return None


async def _proactive_loop() -> None:
    logger.info("[Proactive] Background proactive loop started")
    while True:
        if not proactive_service.in_active_window():
            sleep_seconds = proactive_service.seconds_until_active_window()
            logger.info(f"[Proactive] Outside active hours, sleeping {sleep_seconds // 60} minutes")
            await asyncio.sleep(sleep_seconds)
            continue

        delay_seconds = proactive_service.choose_delay_seconds()
        logger.info(f"[Proactive] Next proactive attempt in {delay_seconds // 60} minutes")
        await asyncio.sleep(delay_seconds)

        if not proactive_service.in_active_window():
            logger.debug("[Proactive] Woke up outside active hours, defer to next window")
            continue

        bot = _pick_bot()
        if bot is None:
            logger.debug("[Proactive] No connected OneBot instance available")
            continue

        try:
            sent = await proactive_service.maybe_send(bot)
            if not sent:
                logger.debug("[Proactive] Skipped proactive send this round")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[Proactive] Background proactive send failed: {exc}")


@driver.on_startup
async def _start_proactive_loop() -> None:
    global _proactive_task
    if not proactive_service.enabled():
        logger.info("[Proactive] INDIVIDUAL_QQ/GROUP_QQ not configured, proactive chat disabled")
        return

    if _proactive_task is None or _proactive_task.done():
        _proactive_task = asyncio.create_task(_proactive_loop())
        logger.info("[Proactive] Scheduled proactive background loop")


@driver.on_shutdown
async def _stop_proactive_loop() -> None:
    global _proactive_task
    if _proactive_task and not _proactive_task.done():
        _proactive_task.cancel()
        try:
            await _proactive_task
        except asyncio.CancelledError:
            pass
    _proactive_task = None
