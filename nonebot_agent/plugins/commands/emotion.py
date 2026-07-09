"""
Emotion-related commands: /情绪, /设置情绪
"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.log import logger

from nonebot_agent.config import config
from nonebot_agent.emotion import emotion_manager, EmotionLabel


# /情绪 command
emotion_cmd = on_command("情绪", aliases={"emotion", "心情"}, priority=5, block=True)

@emotion_cmd.handle()
async def handle_emotion(bot: Bot, event: MessageEvent):
    """
    View current emotion state.
    
    Shows the bot's current emotion for the context (user or group).
    """
    user_id = event.get_user_id()
    
    # Determine context
    if isinstance(event, GroupMessageEvent):
        context_type = "group"
        context_id = str(event.group_id)
        context_name = f"群 {context_id}"
    else:
        context_type = "c2c"
        context_id = user_id
        context_name = "我们的对话"
    
    # Get emotion state
    emotion_state = emotion_manager.get_emotion(context_type, context_id)
    label = emotion_state.get_label()
    style = emotion_state.get_style_description()
    
    response = f"""🎭 当前情绪状态

情绪：{label.value}
愉悦度：{emotion_state.pleasure:+d}
激动度：{emotion_state.arousal:+d}
支配度：{emotion_state.dominance:+d}

对话风格：{style}

💡 在{context_name}中的互动会影响我的情绪哦~"""
    
    await emotion_cmd.finish(response)


# /设置情绪 command (master only)
set_emotion_cmd = on_command("设置情绪", aliases={"set_emotion"}, priority=5, block=True)

# Map Chinese names to EmotionLabel
EMOTION_NAME_MAP = {
    "开心": EmotionLabel.HAPPY,
    "高兴": EmotionLabel.HAPPY,
    "happy": EmotionLabel.HAPPY,
    "低落": EmotionLabel.SAD,
    "难过": EmotionLabel.SAD,
    "sad": EmotionLabel.SAD,
    "烦躁": EmotionLabel.IRRITATED,
    "生气": EmotionLabel.IRRITATED,
    "angry": EmotionLabel.IRRITATED,
    "困倦": EmotionLabel.SLEEPY,
    "困": EmotionLabel.SLEEPY,
    "sleepy": EmotionLabel.SLEEPY,
    "撒娇": EmotionLabel.CUTE,
    "卖萌": EmotionLabel.CUTE,
    "cute": EmotionLabel.CUTE,
    "自信": EmotionLabel.CONFIDENT,
    "confident": EmotionLabel.CONFIDENT,
    "平静": EmotionLabel.CALM,
    "正常": EmotionLabel.CALM,
    "calm": EmotionLabel.CALM,
}

@set_emotion_cmd.handle()
async def handle_set_emotion(bot: Bot, event: MessageEvent):
    """
    Set bot emotion (master only).
    
    Usage: /设置情绪 <情绪名>
    Available emotions: 开心, 低落, 烦躁, 困倦, 撒娇, 自信, 平静
    """
    user_id = event.get_user_id()
    
    # Check if master QQ is configured
    if not config.MASTER_QQ:
        await set_emotion_cmd.finish("❌ 未配置主人QQ号")
        return
    
    # Check if user is the master
    if user_id != config.MASTER_QQ:
        await set_emotion_cmd.finish("❌ 只有主人才能使用此命令")
        return
    
    # Parse arguments
    args = str(event.message).strip().split()
    if args and args[0] in ["设置情绪", "/设置情绪", "set_emotion", "/set_emotion"]:
        args = args[1:]
    
    if not args:
        available = ", ".join(set(EMOTION_NAME_MAP.keys()) - {"happy", "sad", "angry", "sleepy", "cute", "confident", "calm"})
        await set_emotion_cmd.finish(
            f"❌ 请指定情绪名\n\n"
            f"使用方法: /设置情绪 <情绪名>\n"
            f"可选情绪: {available}"
        )
        return
    
    emotion_name = args[0].lower()
    
    if emotion_name not in EMOTION_NAME_MAP:
        available = ", ".join(set(EMOTION_NAME_MAP.keys()) - {"happy", "sad", "angry", "sleepy", "cute", "confident", "calm"})
        await set_emotion_cmd.finish(f"❌ 未知情绪: {emotion_name}\n可选: {available}")
        return
    
    # Determine context
    if isinstance(event, GroupMessageEvent):
        context_type = "group"
        context_id = str(event.group_id)
    else:
        context_type = "c2c"
        context_id = user_id
    
    # Set emotion
    target_label = EMOTION_NAME_MAP[emotion_name]
    new_state = emotion_manager.set_emotion(context_type, context_id, target_label)
    
    await set_emotion_cmd.finish(
        f"✅ 情绪已设置为：{target_label.value}\n\n"
        f"愉悦度：{new_state.pleasure:+d}\n"
        f"激动度：{new_state.arousal:+d}\n"
        f"支配度：{new_state.dominance:+d}"
    )
    
    logger.info(f"[Emotion] Master set emotion to {target_label.value} for {context_type}:{context_id}")
