"""
Skills management command: /skills
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent

from nonebot_agent.config import config
from nonebot_agent.skills import get_skill_registry
from nonebot_agent.skills.models import SkillContext


def _is_master_user(user_id: str) -> bool:
    return bool(config.MASTER_QQ and user_id == config.MASTER_QQ)


def _skill_line(skill) -> str:
    status_text = "on" if skill.enabled else "off"
    kind = "tool" if skill.is_tool else "prompt"
    trigger_text = ", ".join(skill.triggers[:4]) if skill.triggers else "-"
    return f"- {skill.name} [{status_text}/{kind}] triggers: {trigger_text}"


# /skills command
skills_cmd = on_command("skills", aliases={"技能"}, priority=5, block=True)


@skills_cmd.handle()
async def handle_skills(bot: Bot, event: MessageEvent):
    """Manage and inspect local skills."""
    args = str(event.message).strip().split()
    if args and args[0].lstrip("/") in {"skills", "技能"}:
        args = args[1:]

    registry = get_skill_registry()
    action = args[0].lower() if args else "list"
    user_id = event.get_user_id()

    if action in {"list", "ls"}:
        skills = registry.list_skills()
        if not skills:
            await skills_cmd.finish("当前没有加载到任何 skill")
            return
        lines = ["已加载 skills:"]
        lines.extend(_skill_line(skill) for skill in skills)
        lines.append("")
        lines.append("用法: /skills info <name> | reload | enable <name> | disable <name> | test <name> <消息>")
        await skills_cmd.finish("\n".join(lines))
        return

    if action == "info":
        if len(args) < 2:
            await skills_cmd.finish("用法: /skills info <name>")
            return
        skill = registry.get(args[1])
        if not skill:
            await skills_cmd.finish(f"未找到 skill: {args[1]}")
            return
        lines = [
            f"Skill: {skill.name}",
            f"Display: {skill.display_name}",
            f"Status: {'enabled' if skill.enabled else 'disabled'}",
            f"Adapter: {skill.adapter}",
            f"Risk: {skill.risk_level}",
            f"Source: {skill.source}",
            f"Triggers: {', '.join(skill.triggers) if skill.triggers else '-'}",
            f"Aliases: {', '.join(skill.aliases) if skill.aliases else '-'}",
            f"Requires: {', '.join(skill.requires) if skill.requires else '-'}",
            f"Description: {skill.description[:500]}",
        ]
        await skills_cmd.finish("\n".join(lines))
        return

    if action == "reload":
        if not _is_master_user(user_id):
            await skills_cmd.finish("只有主人可以重载 skills")
            return
        registry.reload()
        await skills_cmd.finish(f"skills 已重载，共 {len(registry.list_skills())} 个")
        return

    if action in {"enable", "disable"}:
        if not _is_master_user(user_id):
            await skills_cmd.finish("只有主人可以启用或禁用 skills")
            return
        if len(args) < 2:
            await skills_cmd.finish(f"用法: /skills {action} <name>")
            return
        enabled = action == "enable"
        if not registry.set_enabled(args[1], enabled):
            await skills_cmd.finish(f"未找到 skill: {args[1]}")
            return
        await skills_cmd.finish(f"{args[1]} 已{'启用' if enabled else '禁用'}")
        return

    if action == "test":
        if len(args) < 3:
            await skills_cmd.finish("用法: /skills test <name> <消息>")
            return
        skill_name = args[1]
        message = " ".join(args[2:])
        skill = registry.get(skill_name)
        if not skill:
            await skills_cmd.finish(f"未找到 skill: {skill_name}")
            return
        context = SkillContext(
            user_id=user_id,
            session_type="group" if isinstance(event, GroupMessageEvent) else "c2c",
            group_id=str(event.group_id) if isinstance(event, GroupMessageEvent) else None,
            mode="chat",
            user_message=message,
            skill_override=skill.name,
            skill_exclusive=True,
        )
        prompt = registry.get_prompt_instructions(context)
        await skills_cmd.finish(
            f"测试 skill: {skill.name}\n"
            f"会注入: {'是' if prompt else '否'}\n"
            f"prompt 长度: {len(prompt)} 字符"
        )
        return

    await skills_cmd.finish("未知操作。用法: /skills list | info | reload | enable | disable | test")
