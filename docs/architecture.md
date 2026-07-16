# 系统架构文档

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        QQ 客户端                                 │
│                    (私聊 / 群聊 / @)                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ OneBot V11 协议
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      NapCatQQ                                   │
│                   (QQ 协议端)                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NoneBot2 Framework                            │
│                  (FastAPI + Plugin System)                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  plugins/   │   │  services/  │   │   agent/    │
│  消息入口    │──▶│  编排层      │──▶│  LLM Agent  │
└─────────────┘   └─────────────┘   └──────┬──────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
             ┌─────────────┐        ┌─────────────┐       ┌─────────────┐
             │  memory/    │        │  emotion/   │       │   skills/   │
             │  记忆系统    │        │  情绪系统    │       │  技能系统    │
             └──────┬──────┘        └──────┬──────┘       └──────┬──────┘
                    │                      │                      │
                    └──────────────────────┼──────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────┐
                    │              tools/                   │
                    │         (网络搜索/网页/画图/表情包)     │
                    └──────────────────────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────┐
                    │           LLM API (OpenAI)           │
                    │     (DeepSeek / Qwen / Claude)       │
                    └──────────────────────────────────────┘
```

## 模块说明

### plugins/ - 消息入口层

**职责**: 接收 NoneBot 事件，解析消息内容，路由到对应处理器

**核心模块**:
- `agent_chat.py` - 主聊天处理器，支持私聊/群聊/@触发，命令分发
- `video_download.py` - 视频下载插件（抖音/B站链接识别与下载）
- `proactive_chat.py` - 主动聊天后台任务
- `commands/` - 命令子目录
  - `memory.py` - 记忆管理命令（/记忆 查看/清理）
  - `draw.py` - 画图命令（/画图）
  - `restart.py` - 重启命令（/重启）
  - `skills.py` - 技能管理命令（/技能 列表/启用/禁用）
  - `emotion.py` - 情绪设置命令（/情绪）
  - `basic.py` - 基础命令（/帮助 /状态）
  - `free_chat.py` - 自由聊天开关（/自由聊天）

**设计原则**: 
- 插件只负责消息解析和路由，不处理业务逻辑
- 复杂逻辑下沉到 services/ 层
- 每个插件文件不超过 400 行（AGENTS.md 约束）

### services/ - 编排层

**职责**: 协调多个模块完成复杂业务流程

**核心模块**:
- `chat_service.py` - 聊天服务编排
  - 调用 memory_manager 获取上下文
  - 调用 agent/graph 生成回复
  - 调用 response_sender 发送消息
  - 更新情绪状态
- `response_sender.py` - 响应发送器
  - 解析聊天气泡 JSON
  - 控制发送延迟和节奏
  - 处理表情包标记 `[STICKER:xxx]`
- `proactive_service.py` - 主动聊天服务
  - 选择聊天目标
  - 生成主动话题
  - 控制发送频率

**设计原则**:
- 服务层是业务流程的"导演"
- 不直接操作数据库，通过 memory/ 模块间接访问
- 不直接调用 LLM，通过 agent/ 模块间接调用

### agent/ - LLM Agent 核心

**职责**: 管理对话状态，调用 LLM，执行工具

**核心模块**:
- `graph.py` - LangGraph 状态机
  - 定义对话流程（用户输入 → 记忆检索 → LLM 调用 → 工具执行 → 响应生成）
  - 管理对话状态（State）
  - 处理工具调用循环（最多 6 轮）
- `prompts.py` - Prompt 模板
  - `CHAT_MODE_PROMPT` - 聊天模式系统提示
  - `PROFESSIONAL_MODE_PROMPT` - 专业模式系统提示
  - `EMOTION_STYLE_PROMPTS` - 情绪风格提示
  - `get_mode_from_message()` - 模式判断逻辑
- `chat_output.py` - 聊天输出解析
  - 解析 LLM 返回的 JSON 气泡
  - 归一化响应格式
  - 处理表情包标记
- `llm_provider.py` - LLM 提供商适配
  - 根据配置选择 LLM（DeepSeek/Qwen/OpenAI）
  - 适配不同模型的参数（temperature、extra_body 等）

**设计原则**:
- 使用 LangGraph 而非 LangChain AgentExecutor，因为需要精细控制对话流程
- Prompt 模板与代码分离，便于迭代
- LLM 调用参数按 provider 分派，避免硬编码模型特定参数

### memory/ - 记忆系统

**职责**: 管理短期记忆、长期记忆、会话摘要

**核心模块**:
- `memory_manager.py` - 记忆管理器（统一入口）
  - `process_message()` - 处理用户消息，写入短期记忆
  - `get_context()` - 获取对话上下文（短期 + 长期 + 摘要）
  - `save_response()` - 保存机器人回复
- `memory_store.py` - 记忆存储
  - 操作 MySQL 表（conversations, messages, memory_facts, memory_events）
  - 提供 CRUD 接口
- `memory_writer.py` - 记忆抽取器
  - 从用户消息中提取事实（偏好、个人信息）
  - 从对话中提取事件（重要事件、状态变化）
  - 调用 LLM 进行结构化抽取
- `memory_summary.py` - 摘要生成器
  - 滚动摘要（每 6 条消息触发）
  - 调用 LLM 生成对话摘要
  - 压缩长对话
- `chroma_memory.py` - Chroma 向量记忆
  - 存储长期记忆的向量表示
  - 支持语义检索（top-k 相似记忆）
  - 集合：`nonebot_agent_memory`
- `response_guard.py` - 响应保护
  - 检测回复重复（与近期回复相似度）
  - 调用 LLM 改写重复回复
  - 避免"复读机"现象

**设计原则**:
- MySQL 存储结构化数据（关系、索引、事务）
- Chroma 存储向量数据（语义检索）
- 双存储互补：MySQL 保证数据一致性，Chroma 支持模糊匹配
- 记忆抽取异步执行，不阻塞主流程

### emotion/ - 情绪系统

**职责**: 维护机器人情绪状态，影响回复风格

**核心模块**:
- `emotion_state.py` - 情绪状态管理
  - PAD 模型（Pleasure-Arousal-Dominance）
  - 情绪衰减（每 30 分钟衰减 10%）
  - 深夜困倦修正（23:00-06:00 自动降低 arousal）
  - 情绪标签映射（7 种：开心/低落/烦躁/困倦/撒娇/自信/平静）
- `emotion_analyzer.py` - 情绪分析器
  - 调用 LLM 分析用户消息对情绪的影响
  - 返回 PAD 分数变化
  - 仅在聊天模式下触发

**设计原则**:
- 使用 PAD 三维模型而非离散情绪，因为：
  - 连续空间更细腻（-100~100）
  - 支持混合情绪
  - 便于数学运算（衰减、叠加）
- 情绪按上下文隔离（每个用户/群独立）
- 情绪影响回复风格，但不影响回复内容

### skills/ - 技能系统

**职责**: 管理可调用技能，支持动态加载和路由

**核心模块**:
- `registry.py` - 技能注册表
  - 注册内置工具（search/webpage/sticker/image）
  - 加载本地技能（data/skills/）
  - 提供技能列表和 schema
- `router.py` - 技能路由器
  - 根据消息内容选择技能
  - 支持前缀强制路由（/E skill_name）
  - 支持触发词自动激活
- `executor.py` - 技能执行器
  - 执行 callable skill（工具调用）
  - 执行 prompt skill（提示注入）
  - 超时控制和错误处理
- `prefixes.py` - 前缀解析
  - 解析 `/E skill_name` 格式
  - 支持别名映射（E → ai-li-xi-ya）
- `knowledge.py` - 知识库检索
  - 从技能目录检索参考文档
  - 支持 .md/.txt/.json 文件
  - 轻量关键词匹配

**设计原则**:
- 自研 Skill 系统而非使用 LangChain Tools，因为：
  - 需要支持 prompt-only skill（纯提示注入）
  - 需要支持本地脚本调用
  - 需要支持触发词自动激活
  - 需要支持前缀强制路由
- 技能分为两类：
  - callable skill - 可被 LLM 调用的工具
  - prompt skill - 注入到系统提示的上下文

### tools/ - 工具实现

**职责**: 实现具体工具功能

**核心模块**:
- `search.py` - 网络搜索
  - 调用 WebSearch API
  - 返回搜索结果摘要
- `webpage.py` - 网页读取
  - 请求 HTTP/HTTPS 网页
  - 提取正文内容（BeautifulSoup）
  - URL 安全校验（拒绝内网/本机地址）
- `send_stickers.py` - 表情包工具
  - `search_stickers_tool` - 从 Chroma 检索表情包
  - `send_sticker_by_url` - 返回表情包标记
- `generate_image.py` - 画图工具
  - 调用豆包图片生成 API
  - 支持文生图和图生图

**设计原则**:
- 工具使用 LangChain `@tool` 装饰器
- 工具返回字符串，不直接发送消息
- 所有外部请求做 URL 安全校验

### utils/ - 通用工具

**职责**: 提供通用辅助功能

**核心模块**:
- `media_handler.py` - 媒体处理
  - 图片下载和保存
  - base64 编码
  - 过期清理
- `url_safety.py` - URL 安全校验
  - 拒绝 file:// ftp:// 协议
  - 拒绝 localhost/127.0.0.1/内网 IP
  - 拒绝链路本地地址和保留 IP
- `douyin_spider.py` - 抖音下载器
  - 解析抖音短链
  - 提取视频 URL
  - 下载视频文件
- `bilibili_spider.py` - B站下载器
  - 解析 B站分享卡片
  - 提取音视频流
  - 调用 FFmpeg 合并
- `doubao_image_generate.py` - 豆包画图
  - 调用火山方舟 API
  - 支持文生图和图生图
- `multimodal_embeddings.py` - 多模态嵌入
  - 调用 DashScope 嵌入 API
  - 支持文本和图片嵌入
- `address_qqdocurl.py` - QQ 文档链接处理
  - 解析 qqdocurl 格式
  - 提取真实 URL

## 数据流

### 典型聊天流程

```
1. QQ 客户端发送消息
   ↓
2. NapCatQQ 接收并转换为 OneBot V11 事件
   ↓
3. NoneBot2 接收事件，路由到 plugins/agent_chat.py
   ↓
4. agent_chat.py 解析消息
   - 提取文本、图片、@信息
   - 判断模式（聊天/专业）
   - 检查命令前缀
   ↓
5. 调用 services/chat_service.py
   ↓
6. chat_service.py 编排流程
   a. 调用 memory_manager.process_message()
      - 写入 MySQL messages 表
      - 检索短期记忆（最近 40 条）
      - 检索长期记忆（Chroma top-20）
      - 检索会话摘要
   b. 调用 agent/graph.py
      - 构建 LangGraph State
      - 注入系统提示（prompts.py）
      - 调用 LLM API
      - 执行工具调用（如有）
      - 生成回复
   c. 调用 response_guard.py
      - 检测回复重复
      - 必要时调用 LLM 改写
   d. 调用 memory_manager.save_response()
      - 写入 MySQL messages 表
      - 抽取长期记忆（异步）
      - 更新会话摘要（异步）
   e. 调用 emotion_analyzer.py（聊天模式）
      - 分析情绪影响
      - 更新情绪状态
   f. 调用 response_sender.py
      - 解析聊天气泡 JSON
      - 控制发送延迟
      - 发送 QQ 消息
   ↓
7. NapCatQQ 发送消息到 QQ 客户端
```

### 工具调用流程

```
1. LLM 返回工具调用请求
   ↓
2. LangGraph 进入工具节点
   ↓
3. skills/executor.py 执行工具
   - 查找工具函数
   - 调用工具（search/webpage/sticker/image）
   - 捕获异常
   ↓
4. 工具返回结果
   ↓
5. LangGraph 将结果注入对话
   ↓
6. 继续 LLM 调用（最多 6 轮）
```

### 主动聊天流程

```
1. NoneBot 启动时注册后台任务
   ↓
2. proactive_chat.py 启动循环
   - 检查时间窗口（9:00-23:00）
   - 等待间隔（4-12 小时）
   ↓
3. proactive_service.py 选择目标
   - 从 INDIVIDUAL_QQ/GROUP_QQ 选择
   - 检查冷却时间
   ↓
4. 生成主动话题
   - 检索近期对话
   - 可选调用网络搜索
   ↓
5. 调用 chat_service.py 生成回复
   ↓
6. 调用 response_sender.py 发送消息
```

## 设计决策

### 为什么使用 LangGraph 而非 LangChain AgentExecutor

**问题**: LangChain AgentExecutor 是黑盒，难以控制对话流程

**LangGraph 优势**:
1. **显式状态机** - 对话流程可视化为节点和边
2. **精细控制** - 可以控制每个节点的输入输出
3. **条件分支** - 支持根据状态选择不同路径
4. **持久化** - 支持对话状态持久化（未来扩展）
5. **可测试** - 每个节点可以独立测试

**实际收益**:
- 工具调用循环限制为 6 轮，避免无限循环
- 可以在工具调用后注入额外上下文
- 可以根据对话模式切换不同流程

### 为什么使用 MySQL + Chroma 双存储

**问题**: 单一存储无法同时满足关系查询和语义检索需求

**MySQL 优势**:
- 关系型数据（用户-对话-消息）
- 事务支持（保证数据一致性）
- 索引和查询优化
- 成熟稳定

**Chroma 优势**:
- 向量存储和检索
- 语义相似度计算
- 轻量级，易于部署

**双存储策略**:
- MySQL 存储结构化数据（conversations, messages, memory_facts, memory_events）
- Chroma 存储向量数据（记忆嵌入、表情包描述）
- 通过 ID 关联（memory_facts.chroma_id → Chroma document id）

**实际收益**:
- 短期记忆用 MySQL 查询（最近 40 条）
- 长期记忆用 Chroma 检索（语义相似 top-20）
- 表情包用 Chroma 检索（描述相似）

### 为什么自研 Skill 系统

**问题**: LangChain Tools 无法满足所有需求

**LangChain Tools 限制**:
1. 只支持 callable tool（工具调用）
2. 不支持 prompt-only skill（提示注入）
3. 不支持触发词自动激活
4. 不支持前缀强制路由
5. 不支持本地脚本调用

**自研 Skill 系统优势**:
1. **双类型支持**
   - callable skill - 可被 LLM 调用
   - prompt skill - 注入到系统提示
2. **灵活路由**
   - 触发词自动激活
   - 前缀强制路由（/E skill_name）
   - 别名映射
3. **本地扩展**
   - 支持 data/skills/ 目录
   - 支持 .md/.txt/.json 参考文档
   - 支持白名单脚本调用
4. **知识库集成**
   - 从技能目录检索参考
   - 轻量关键词匹配

**实际收益**:
- 可以快速添加新技能（只需创建 SKILL.md）
- 可以强制使用特定技能（/E ai-li-xi-ya）
- 可以引用技能目录的文档（knowledge.py）

### 为什么使用 PAD 情绪模型

**问题**: 离散情绪模型（开心/悲伤/愤怒）无法表达细腻情绪

**PAD 模型优势**:
1. **三维连续空间**
   - Pleasure（愉悦度）: -100~100
   - Arousal（激动度）: -100~100
   - Dominance（支配度）: -100~100
2. **支持混合情绪**
   - 可以同时开心（P=80）和激动（A=60）
   - 可以表达复杂情绪（如"平静的自信"）
3. **数学运算友好**
   - 情绪衰减（每 30 分钟衰减 10%）
   - 情绪叠加（多条消息影响）
   - 深夜困倦修正（降低 Arousal）
4. **标签映射灵活**
   - 7 种标签（开心/低落/烦躁/困倦/撒娇/自信/平静）
   - 根据 PAD 分数动态映射

**实际收益**:
- 情绪状态更细腻（不是非黑即白）
- 情绪衰减自然（不会突然变化）
- 情绪影响回复风格（通过 EMOTION_STYLE_PROMPTS）

## 扩展指南

### 如何添加新命令

**步骤**:

1. **创建命令文件**（在 `plugins/commands/` 下）
   ```python
   # plugins/commands/my_command.py
   from nonebot import on_command
   from nonebot.adapters.onebot.v11 import MessageEvent
   from nonebot.params import CommandArg
   
   my_cmd = on_command("我的命令", priority=5)
   
   @my_cmd.handle()
   async def handle_my_command(event: MessageEvent, args: Message = CommandArg()):
       await my_cmd.finish("这是我的命令回复")
   ```

2. **注册命令**（在 `plugins/__init__.py` 中）
   ```python
   from .commands import my_command
   ```

3. **更新文档**（在 README.md 命令列表中）

**注意事项**:
- 命令文件不超过 400 行
- 复杂逻辑下沉到 services/
- 使用 `nonebot.log.logger` 而非 `print()`

### 如何添加新工具

**步骤**:

1. **创建工具文件**（在 `tools/` 下）
   ```python
   # tools/my_tool.py
   from langchain.tools import tool
   
   @tool(description="我的工具描述")
   def my_tool(param: str) -> str:
       """工具文档字符串"""
       return f"工具返回结果: {param}"
   ```

2. **导出工具**（在 `tools/__init__.py` 中）
   ```python
   from .my_tool import my_tool
   
   __all__ = ["my_tool", ...]
   ```

3. **注册工具**（在 `skills/registry.py` 中）
   ```python
   from nonebot_agent.tools import my_tool
   
   def register_builtin_tools():
       # ... 现有工具
       register_tool(my_tool)
   ```

4. **更新文档**（在 README.md 工具列表中）

**注意事项**:
- 工具返回字符串，不直接发送消息
- 所有外部请求做 URL 安全校验
- 工具描述要清晰（LLM 根据描述选择工具）

### 如何添加新人设

**步骤**:

1. **创建人设目录**（在 `data/skills/` 下）
   ```
   data/skills/my_persona/
   ├── SKILL.md          # 人设定义
   ├── profile.md        # 个人资料
   ├── personality.md    # 性格特点
   └── references/       # 参考文档
       └── dialogues.md
   ```

2. **编写 SKILL.md**
   ```markdown
   ---
   name: my_persona
   display_name: 我的人设
   description: 我的人设描述
   triggers:
     - 触发词1
     - 触发词2
   modes:
     - chat
   session_types:
     - c2c
     - group
   risk_level: low
   ---
   
   # 我的人设
   
   当用户聊到相关话题时，用特定风格回应。
   不要说自己启用了人设。
   ```

3. **加载人设**
   - 自动加载（重启后）
   - 或手动加载：`/skills reload`

4. **使用人设**
   - 自动激活（触发词匹配）
   - 或强制使用：`/E my_persona 消息内容`

**注意事项**:
- SKILL.md 必须包含 YAML frontmatter
- 参考文档支持 .md/.txt/.json
- 人设风格通过 prompt 注入，不影响工具调用

## 总结

NoneBot Agent 采用分层架构：
- **plugins/** - 消息入口，负责解析和路由
- **services/** - 编排层，负责协调业务流程
- **agent/** - LLM Agent，负责对话生成
- **memory/** - 记忆系统，负责上下文管理
- **emotion/** - 情绪系统，负责风格调节
- **skills/** - 技能系统，负责工具管理
- **tools/** - 工具实现，负责具体功能
- **utils/** - 通用工具，负责辅助功能

核心设计原则：
1. **分层清晰** - 每层职责单一，便于测试和维护
2. **双存储互补** - MySQL 保证一致性，Chroma 支持语义检索
3. **LangGraph 精细控制** - 显式状态机，避免黑盒
4. **自研 Skill 系统** - 灵活扩展，支持多种技能类型
5. **PAD 情绪模型** - 连续空间，支持细腻情绪

这种架构支持：
- 长期运行的智能对话
- 多模态理解（文本 + 图片）
- 工具调用（搜索/网页/画图/表情包）
- 主动聊天（后台任务）
- 技能扩展（本地 prompt + 工具）
- 情绪调节（影响回复风格）
