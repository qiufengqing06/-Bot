"""
Memory management commands: /记忆
"""
from datetime import datetime

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.typing import T_State

from nonebot_agent.database import SessionLocal
from nonebot_agent.models import MemoryFact, MemoryEvent


# /记忆 command
memory_cmd = on_command("记忆", priority=5, block=True)

# Pending clear confirmations: user_id -> True
_pending_clear = {}


@memory_cmd.handle()
async def handle_memory(bot: Bot, event: MessageEvent, state: T_State, args=CommandArg()):
    """
    Memory management command.
    - /记忆 — list user's stored facts and events (max 20)
    - /记忆 删除 <id> — delete a specific fact/event by id
    - /记忆 清空 — clear all memories (requires confirmation)
    """
    user_id = event.get_user_id()
    arg_text = args.extract_plain_text().strip()

    # Sub-command: 删除 <id>
    if arg_text.startswith("删除"):
        rest = arg_text[len("删除"):].strip()
        if not rest:
            await memory_cmd.finish("❌ 请指定要删除的条目 ID\n用法: /记忆 删除 <id>")
            return
        try:
            target_id = int(rest)
        except ValueError:
            await memory_cmd.finish("❌ ID 必须是数字")
            return

        db = SessionLocal()
        try:
            # Try MemoryFact first
            fact = db.query(MemoryFact).filter(
                MemoryFact.id == target_id,
                MemoryFact.user_id == user_id
            ).first()
            if fact:
                db.delete(fact)
                db.commit()
                logger.info(f"[Memory] User {user_id} deleted fact id={target_id}")
                await memory_cmd.finish(f"✅ 已删除事实条目 (ID: {target_id})")
                return

            # Try MemoryEvent
            event_row = db.query(MemoryEvent).filter(
                MemoryEvent.id == target_id,
                MemoryEvent.user_id == user_id
            ).first()
            if event_row:
                db.delete(event_row)
                db.commit()
                logger.info(f"[Memory] User {user_id} deleted event id={target_id}")
                await memory_cmd.finish(f"✅ 已删除事件条目 (ID: {target_id})")
                return

            await memory_cmd.finish(f"❌ 未找到 ID 为 {target_id} 的记忆条目")
        except Exception as e:
            db.rollback()
            logger.error(f"[Memory] Error deleting memory id={target_id}: {e}")
            await memory_cmd.finish(f"❌ 删除失败: {e}")
        finally:
            db.close()
        return

    # Sub-command: 清空
    if arg_text == "清空":
        if user_id in _pending_clear:
            # Already pending, do the actual clear
            del _pending_clear[user_id]
            db = SessionLocal()
            try:
                facts_deleted = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).delete()
                events_deleted = db.query(MemoryEvent).filter(MemoryEvent.user_id == user_id).delete()
                db.commit()
                logger.info(f"[Memory] User {user_id} cleared all memories (facts={facts_deleted}, events={events_deleted})")
                await memory_cmd.finish(f"✅ 已清空所有记忆\n删除了 {facts_deleted} 条事实和 {events_deleted} 条事件")
            except Exception as e:
                db.rollback()
                logger.error(f"[Memory] Error clearing memories for {user_id}: {e}")
                await memory_cmd.finish(f"❌ 清空失败: {e}")
            finally:
                db.close()
        else:
            # First time, ask for confirmation
            _pending_clear[user_id] = True
            await memory_cmd.finish(
                "⚠️ 确认清空所有记忆？\n"
                "此操作不可恢复！\n"
                "请输入「确认清空」来继续"
            )
        return

    # Sub-command: 确认清空 (typed as a separate message)
    if arg_text == "确认清空":
        if user_id in _pending_clear:
            del _pending_clear[user_id]
            db = SessionLocal()
            try:
                facts_deleted = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).delete()
                events_deleted = db.query(MemoryEvent).filter(MemoryEvent.user_id == user_id).delete()
                db.commit()
                logger.info(f"[Memory] User {user_id} cleared all memories (facts={facts_deleted}, events={events_deleted})")
                await memory_cmd.finish(f"✅ 已清空所有记忆\n删除了 {facts_deleted} 条事实和 {events_deleted} 条事件")
            except Exception as e:
                db.rollback()
                logger.error(f"[Memory] Error clearing memories for {user_id}: {e}")
                await memory_cmd.finish(f"❌ 清空失败: {e}")
            finally:
                db.close()
        else:
            await memory_cmd.finish("❌ 没有待确认的清空操作，请先使用 /记忆 清空")
        return

    # Default: list memories
    db = SessionLocal()
    try:
        facts = db.query(MemoryFact).filter(
            MemoryFact.user_id == user_id
        ).order_by(MemoryFact.updated_at.desc()).limit(20).all()

        events = db.query(MemoryEvent).filter(
            MemoryEvent.user_id == user_id
        ).order_by(MemoryEvent.updated_at.desc()).limit(20).all()

        if not facts and not events:
            await memory_cmd.finish("📭 暂无记忆记录")
            return

        lines = ["📋 我的记忆记录\n"]

        if facts:
            lines.append("【事实】")
            for f in facts[:20]:
                date_str = f.updated_at.strftime("%Y-%m-%d") if f.updated_at else "未知"
                lines.append(f"  #{f.id} [{f.category}] {f.content} | {date_str}")
            lines.append("")

        if events:
            lines.append("【事件】")
            for e in events[:20]:
                date_str = e.updated_at.strftime("%Y-%m-%d") if e.updated_at else "未知"
                lines.append(f"  #{e.id} [{e.category}] {e.content} | {date_str}")

        total_facts = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).count()
        total_events = db.query(MemoryEvent).filter(MemoryEvent.user_id == user_id).count()
        lines.append(f"\n共 {total_facts} 条事实, {total_events} 条事件")

        await memory_cmd.finish("\n".join(lines))
    except Exception as e:
        logger.error(f"[Memory] Error listing memories for {user_id}: {e}")
        await memory_cmd.finish(f"❌ 查询失败: {e}")
    finally:
        db.close()


# Handle "确认清空" as a standalone message (when user types it after /记忆 清空)
confirm_clear_cmd = on_command("确认清空", priority=5, block=True)


@confirm_clear_cmd.handle()
async def handle_confirm_clear(bot: Bot, event: MessageEvent):
    """Handle the confirmation message for clearing memories."""
    user_id = event.get_user_id()
    if user_id in _pending_clear:
        del _pending_clear[user_id]
        db = SessionLocal()
        try:
            facts_deleted = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).delete()
            events_deleted = db.query(MemoryEvent).filter(MemoryEvent.user_id == user_id).delete()
            db.commit()
            logger.info(f"[Memory] User {user_id} cleared all memories (facts={facts_deleted}, events={events_deleted})")
            await confirm_clear_cmd.finish(f"✅ 已清空所有记忆\n删除了 {facts_deleted} 条事实和 {events_deleted} 条事件")
        except Exception as e:
            db.rollback()
            logger.error(f"[Memory] Error clearing memories for {user_id}: {e}")
            await confirm_clear_cmd.finish(f"❌ 清空失败: {e}")
        finally:
            db.close()
    else:
        await confirm_clear_cmd.finish("❌ 没有待确认的清空操作，请先使用 /记忆 清空")
