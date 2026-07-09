# NoneBot Agent

NoneBot Agent 是一个基于 NoneBot2、OneBot V11、LangGraph 和 OpenAI-compatible LLM API 的智能 QQ 机器人项目。它的核心目标不是只做问答，而是提供一个可长期运行、能记忆上下文、能理解图片、能调用工具、能扩展本地技能、并能在私聊和群聊中自然互动的 Agent Bot。

当前代码面向 Windows + NapCatQQ 场景编写，数据层使用 MySQL 和 Chroma，模型接口使用 OpenAI 兼容协议，因此可以接入通义千问、DeepSeek、OpenAI 兼容中转、火山方舟等服务。

改进路线和后续重构建议见 [docs/improvement-roadmap.md](docs/improvement-roadmap.md)。

## 目录

- [核心能力](#核心能力)
- [整体架构](#整体架构)
- [运行链路](#运行链路)
- [目录结构](#目录结构)
- [环境要求](#环境要求)
- [安装与初始化](#安装与初始化)
- [配置说明](#配置说明)
- [启动方式](#启动方式)
- [QQ 使用方法](#qq-使用方法)
- [命令列表](#命令列表)
- [Skill 扩展机制](#skill-扩展机制)
- [开发指南](#开发指南)
- [测试与辅助脚本](#测试与辅助脚本)
- [运行数据与安全注意事项](#运行数据与安全注意事项)
- [常见问题](#常见问题)

## 核心能力

### 双模式聊天

机器人根据消息前缀切换对话模式：

| 模式 | 触发方式 | 代码位置 | 适合场景 |
| --- | --- | --- | --- |
| 聊天模式 | 普通消息，例如 `你好` | `nonebot_agent/agent/prompts.py` 的 `CHAT_MODE_PROMPT` | 日常闲聊、群聊插话、轻松语气 |
| 专业模式 | 消息以 `/` 开头，例如 `/帮我查一下 Python 3.13 新特性` | `get_mode_from_message()` | 搜索、解释、技术问答、长回复 |

聊天模式要求 LLM 输出结构化 JSON 气泡，随后由 `ChatResponsePlan` 和 `ResponseSender` 解析并分批发送。专业模式输出普通文本。

### 多模态图片理解

图片处理支持两种路径：

| 配置 | 行为 |
| --- | --- |
| `IS_MULTIMODAL_MODEL=true` | 把图片 URL 或本地 base64 直接传给主 LLM |
| `IS_MULTIMODAL_MODEL=false` | 先用 `VISION_MODEL` 分析图片，再把图片描述写入用户消息给主 LLM |

相关代码：

- `nonebot_agent/plugins/agent_chat.py`：从 OneBot 消息段提取图片 URL，并下载到本地。
- `nonebot_agent/agent/graph.py`：构造 OpenAI 多模态消息，或调用视觉模型生成图片描述。
- `nonebot_agent/utils/media_handler.py`：图片下载、base64 转换、过期清理。

### 记忆系统

项目同时使用 MySQL 和 Chroma：

| 层级 | 存储 | 内容 | 作用 |
| --- | --- | --- | --- |
| 短期记忆 | MySQL | 最近对话消息、群聊上下文、媒体记录 | 保持当前会话连贯 |
| 结构化长期记忆 | MySQL + Chroma | 用户事实、偏好、近况、事件 | 避免复读旧回答，只检索事实 |
| 会话摘要 | MySQL | 每个会话和模式的滚动摘要 | 主动聊天和长会话压缩 |
| 表情包向量库 | Chroma | 表情包描述和文件名 | 检索并发送本地表情包 |

关键模块：

- `nonebot_agent/memory/memory_manager.py`：统一入口，负责读取短期记忆、检索长期记忆、保存回复。
- `nonebot_agent/memory/memory_writer.py`：从用户消息中抽取用户事实和事件。
- `nonebot_agent/memory/memory_store.py`：写入 `memory_facts`、`memory_events`，并同步 Chroma 文档。
- `nonebot_agent/memory/memory_summary.py`：维护滚动会话摘要。
- `nonebot_agent/memory/response_guard.py`：检测回复是否和近期回复过于相似，必要时调用 LLM 改写。

### 情绪系统

聊天模式下，机器人维护一个简化 PAD 情绪状态：

- Pleasure：愉悦度
- Arousal：激动度
- Dominance：支配度

情绪按上下文隔离：

| 场景 | 情绪上下文 |
| --- | --- |
| 私聊 | 每个用户一份情绪状态 |
| 群聊 | 每个群一份情绪状态 |

情绪状态存储在 `bot_emotion_state` 表中。`EmotionAnalyzer` 会调用 LLM 判断用户消息对情绪的影响，`EmotionManager` 负责衰减、深夜困倦修正、手动设置和标签映射。

相关文件：

- `nonebot_agent/emotion/emotion_state.py`
- `nonebot_agent/emotion/emotion_analyzer.py`

### 工具调用

Agent 可以通过 Skill Registry 暴露的 callable skill 调用工具：

| 工具 | 文件 | 能力 |
| --- | --- | --- |
| `search_from_internet` | `nonebot_agent/tools/search.py` | 调用 WebSearch API 搜索实时信息 |
| `read_webpage` | `nonebot_agent/tools/webpage.py` | 请求公网 HTTP/HTTPS 网页并提取正文 |
| `search_stickers_tool` | `nonebot_agent/tools/send_stickers.py` | 从 Chroma 表情包库检索表情 |
| `send_sticker_by_url` | `nonebot_agent/tools/send_stickers.py` | 返回 `[STICKER:filename]` 标记，由消息层转成本地图片 |

### AI 画图

`/画图` 命令调用豆包图片生成接口，支持文生图和图生图：

- 文生图：`/画图 一只可爱的猫，4K`
- 图生图：发送图片并附带 `/画图 把背景换成海边`

相关文件：

- `nonebot_agent/plugins/agent_chat.py`：命令处理和参数抽取。
- `nonebot_agent/tools/generate_image.py`：LangChain tool 封装。
- `nonebot_agent/utils/doubao_image_generate.py`：火山方舟 Ark 图片生成调用。

### 视频下载

发送抖音或 B 站分享内容时，`video_download` 插件会优先拦截消息：

- 抖音：识别 `https://v.douyin.com/...`
- B 站：识别 QQ 小程序分享卡片中的 Bilibili appid 和 `qqdocurl`

下载成功后机器人会发送本地视频文件。B 站下载需要 FFmpeg 合并音视频。

网页读取和视频下载都会先做 URL 安全校验：只允许公网 HTTP/HTTPS 地址，拒绝 `file://`、`ftp://`、本机地址、内网地址、链路本地地址和保留 IP。

相关文件：

- `nonebot_agent/plugins/video_download.py`
- `nonebot_agent/utils/douyin_spider.py`
- `nonebot_agent/utils/bilibili_spider.py`
- `nonebot_agent/utils/address_qqdocurl.py`

### 主动聊天

`proactive_chat` 插件会在 NoneBot 启动时注册后台任务。如果 `.env` 中配置了 `INDIVIDUAL_QQ` 或 `GROUP_QQ`，机器人会在活跃时间窗口内，按间隔和冷却规则挑选目标主动发消息。

主动消息会使用：

- 最近聊天摘要
- 历史上下文
- 可选的联网话题
- 回复重复检测
- 自然气泡发送

相关文件：

- `nonebot_agent/plugins/proactive_chat.py`
- `nonebot_agent/services/proactive_runtime.py`
- `nonebot_agent/services/proactive_policy.py`

### Skill 兼容层

项目实现了一套轻量 Skill Registry：

- 自动注册内置 LangChain tools 为 callable skill。
- 从 `data/skills/<skill_name>/SKILL.md` 加载 prompt-only skill。
- 支持 `triggers` 自动激活。
- 支持 `/E ...` 这类前缀强制路由到指定 skill。
- 支持多文件 skill 的 `.md`、`.txt`、`.json` 引用检索。
- 支持严格白名单下的本地 Python 脚本调用。

详细见 [Skill 扩展机制](#skill-扩展机制)。

## 整体架构

```text
QQ / 群聊 / 私聊
        |
        v
NapCatQQ / OneBot V11
        |
        v
NoneBot2 FastAPI Driver
        |
        +--> video_download.py
        |       - 优先检测抖音/B站链接
        |       - 下载并发送视频
        |       - 命中后阻止继续进入聊天 Agent
        |
        +--> agent_chat.py
        |       - 私聊和 @ 消息
        |       - 群消息记录
        |       - 自由聊天概率触发
        |       - 命令处理
        |
        +--> proactive_chat.py
                - 启动后台主动聊天循环

agent_chat.py
        |
        v
services/chat_service.py
        |
        +--> memory_manager.process_message()
        |       - 写入用户消息
        |       - 读取短期记忆
        |       - 检索长期记忆和摘要
        |
        +--> agent/graph.py
        |       - LangGraph 状态机
        |       - LLM 调用
        |       - 工具调用循环
        |
        +--> response_guard
        |       - 检测并改写重复回复
        |
        +--> memory_manager.save_response()
        |       - 保存机器人回复
        |       - 抽取结构化长期记忆
        |       - 刷新摘要
        |
        +--> emotion_manager / emotion_analyzer
                - 更新聊天模式情绪

数据层
        |
        +--> MySQL
        |       - conversations
        |       - messages
        |       - message_media
        |       - group_settings
        |       - bot_emotion_state
        |       - memory_facts
        |       - memory_events
        |       - conversation_summaries
        |
        +--> Chroma
                - nonebot_agent_memory
                - images_description
```

## 运行链路

### 私聊或 @ 机器人

1. OneBot 把 QQ 消息推给 NoneBot。
2. `agent_chat.py` 的 `agent_reply` 处理器被 `to_me()` 规则触发。
3. `extract_message_content()` 提取文本、图片 URL、本地图片路径和媒体元数据。
4. `parse_skill_prefix()` 判断是否使用 `/E` 等 skill 前缀。
5. `get_mode_from_message()` 判断聊天模式或专业模式。
6. `generate_response()` 写入用户消息并准备记忆上下文。
7. `LangGraph` 调用主 LLM，必要时调用工具。
8. 聊天模式输出 JSON 气泡，专业模式输出文本。
9. `ResponseGuard` 检查是否复读。
10. 非错误回复写回 MySQL 和长期记忆。
11. 聊天模式更新情绪。
12. `ResponseSender` 按气泡和延迟发送 QQ 消息。

### 群聊未 @ 消息

1. `group_recorder` 记录所有群消息。
2. 消息会写入对应群的会话上下文。
3. 如果开启了自由聊天模式，则按群配置概率决定是否回复。
4. 被选中时以聊天模式生成并发送回复。

### 视频下载

1. `video_download_handler` 优先检查消息。
2. 命中抖音或 B 站链接后发送“正在下载”提示。
3. 下载前校验 URL，拒绝本机、内网、`file://`、`ftp://` 等不安全地址。
4. 使用 DrissionPage 启动 Chromium 抓取真实媒体地址。
5. 抖音直接下载视频；B 站下载视频流和音频流后用 FFmpeg 合并。
6. 发送本地视频文件。
7. 抛出 `StopPropagation`，阻止该消息继续触发 Agent 回复。

### 主动聊天

1. `proactive_chat.py` 在启动时检查是否配置主动聊天目标。
2. 后台循环只在 `PROACTIVE_DAY_START_HOUR` 到 `PROACTIVE_DAY_END_HOUR` 内工作。
3. 服务从配置中的私聊和群聊目标里选择符合冷却条件的目标。
4. 读取近期对话、摘要和长期记忆。
5. 可选调用网络搜索获取话题候选。
6. 生成一条自然聊天气泡并发送。
7. 主动发送内容也会写入记忆，避免后续重复。

## 目录结构

```text
NoneBot_Agent/
├── bot.py                         # NoneBot 启动入口，注册 OneBot V11 adapter
├── start_bot.bat                  # Windows 循环重启脚本
├── init_db.py                     # 创建 ORM 定义的数据库表
├── migrate_db.py                  # 为已有数据库补齐新表和新字段
├── test.py                        # LLM API 连通性测试脚本
├── pyproject.toml                 # 项目依赖、NoneBot 插件配置、ruff/pyright 配置
├── .env.example                   # 环境变量示例
├── docs/
│   ├── skills.md                  # Skill 兼容层说明
│   └── improvement-roadmap.md     # 单独的改进路线文档
├── data/
│   ├── chroma/                    # Chroma 持久化目录，运行时数据
│   ├── images/                    # 聊天图片、表情包、生成图片
│   ├── videos/                    # 下载视频和临时音视频文件
│   └── skills/                    # 本地 prompt-only skills
└── nonebot_agent/
    ├── config.py                  # 统一配置读取
    ├── database.py                # SQLAlchemy engine、Session、Base
    ├── models.py                  # MySQL ORM 模型
    ├── agent/
    │   ├── graph.py               # LangGraph Agent 状态机
    │   ├── prompts.py             # 聊天/专业模式 prompt 和情绪 prompt
    │   └── chat_output.py         # 聊天气泡 JSON 解析和归一化
    ├── plugins/
    │   ├── agent_chat.py          # 主聊天插件、命令、自由聊天、画图
    │   ├── video_download.py      # 抖音/B站视频下载插件
    │   └── proactive_chat.py      # 主动聊天后台循环插件
    ├── services/
    │   ├── chat_service.py        # 对话编排服务
    │   ├── response_sender.py     # 气泡发送、延迟、追发取消
    │   ├── proactive_runtime.py   # 主动聊天运行时
    │   └── proactive_policy.py    # 主动聊天纯策略函数
    ├── memory/
    │   ├── memory_manager.py      # 记忆系统统一入口
    │   ├── chroma_memory.py       # Chroma 向量记忆封装
    │   ├── memory_writer.py       # 用户事实/事件抽取
    │   ├── memory_store.py        # 结构化记忆写入和检索
    │   ├── memory_summary.py      # 滚动摘要
    │   └── response_guard.py      # 回复重复保护
    ├── emotion/
    │   ├── emotion_state.py       # PAD 情绪状态、衰减和标签
    │   └── emotion_analyzer.py    # LLM 情绪影响分析
    ├── skills/
    │   ├── registry.py            # Skill 注册、加载和工具 schema 暴露
    │   ├── executor.py            # callable skill 执行器
    │   ├── router.py              # prompt skill 选择和格式化
    │   ├── prefixes.py            # /E 等 skill 前缀解析
    │   ├── knowledge.py           # skill 引用文件轻量检索
    │   └── adapters/              # markdown/langchain/script 适配器
    ├── tools/
    │   ├── search.py              # 网络搜索工具
    │   ├── webpage.py             # 网页正文读取工具
    │   ├── send_stickers.py       # 表情包检索与发送标记
    │   └── generate_image.py      # 豆包图片生成工具
    ├── utils/
    │   ├── media_handler.py       # 图片下载、保存、base64、清理
    │   ├── url_safety.py          # 外部 HTTP URL 安全校验
    │   ├── douyin_spider.py       # 抖音下载器
    │   ├── bilibili_spider.py     # B站下载器
    │   ├── doubao_image_generate.py
    │   ├── multimodal_embeddings.py
    │   └── address_qqdocurl.py
    └── test/                      # unittest 和外部服务实验脚本
```

运行时数据、浏览器缓存、`.env`、Chroma 数据库、图片和视频目录都应该视为本地数据，不要提交到版本库。

## 环境要求

### 必需组件

| 组件 | 建议版本 | 用途 |
| --- | --- | --- |
| Python | 3.11 推荐，项目声明支持 `>=3.10,<4.0` | 运行 NoneBot 和 Agent |
| MySQL | 5.7+ 或 8.0 | 保存会话、消息、情绪、结构化记忆 |
| NapCatQQ | 近期版本 | QQ 协议端，提供 OneBot V11 反向 WebSocket |
| Chromium/Chrome | 可被 DrissionPage 调用 | 抖音/B站视频解析 |
| FFmpeg | 可在命令行执行 `ffmpeg` | B站音视频合并 |

### API Key

至少需要配置主 LLM：

| 配置项 | 用途 |
| --- | --- |
| `LLM_API_KEY` | 主 LLM API key |
| `LLM_API_URL` | OpenAI-compatible base URL |
| `LLM_MODEL` | 主模型名称 |

建议同时配置：

| 配置项 | 用途 |
| --- | --- |
| `QIANWEN_API_KEY` | Chroma 文本向量、可选视觉模型 |
| `VISION_API_KEY` | 主模型不支持图片时的视觉模型 |
| `WEB_SEARCH_API_KEY` | 网络搜索工具 |
| `DOUBAO_API_KEY` | `/画图` 命令 |

## 安装与初始化

### 1. 创建 Python 环境

Windows 推荐使用 Conda：

```powershell
conda create -n QQBot python=3.11 -y
conda activate QQBot
```

进入项目目录：

```powershell
cd D:\projects\PythonProjects\New_QQBot_demo\NoneBot_Agent
```

### 2. 安装依赖

```powershell
pip install -e .
```

项目依赖已在 `pyproject.toml` 中声明。`langchain-openai` 用于表情包向量检索等功能；如果你使用的是旧环境且启动时报 `ModuleNotFoundError: No module named 'langchain_openai'`，可以补装：

```powershell
pip install langchain-openai
```

### 3. 准备配置文件

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填写主 LLM、数据库和 OneBot 相关配置。

### 4. 创建 MySQL 数据库

在 MySQL 中执行：

```sql
CREATE DATABASE nonebot_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 初始化数据库表

新数据库执行：

```powershell
python init_db.py
```

如果是已有数据库，或者从旧版本升级，执行：

```powershell
python migrate_db.py
```

`migrate_db.py` 会补齐媒体表、结构化记忆表和摘要表。对新库执行也通常是安全的。

### 6. 配置 NapCatQQ

1. 启动 NapCatQQ 并登录机器人 QQ。
2. 打开 NapCat WebUI。
3. 添加反向 WebSocket：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

4. 如果启用了 token，把 NapCat 中的 token 和 `.env` 的 `ONEBOT_ACCESS_TOKEN` 保持一致。

## 配置说明

项目从根目录 `.env` 读取配置，集中封装在 `nonebot_agent/config.py`。

### NoneBot 基础配置

```env
ENVIRONMENT=dev
DRIVER=~fastapi
HOST=127.0.0.1
PORT=8080
LOG_LEVEL=DEBUG
COMMAND_START=["/", ""]
COMMAND_SEP=["."]
ONEBOT_ACCESS_TOKEN=
```

`PORT` 必须和 NapCat 反向 WebSocket URL 中的端口一致。

启动入口 `bot.py` 会在加载 NoneBot 插件前执行配置校验。主 LLM、MySQL、Qianwen/DashScope 向量配置缺失会直接阻止启动；搜索和画图这类可选能力缺失只会输出警告。

### 主 LLM 配置

```env
LLM_MODEL=deepseek-v4-pro
LLM_API_KEY=
LLM_API_URL=https://api.deepseek.com/v1
IS_MULTIMODAL_MODEL=false
```

说明：

- `LLM_API_URL` 必须是 OpenAI-compatible base URL。
- `IS_MULTIMODAL_MODEL=true` 时，主模型需要支持图片输入。
- `IS_MULTIMODAL_MODEL=false` 时，图片会先交给视觉模型描述。

### 视觉模型配置

```env
VISION_MODEL=qwen3-vl-plus
VISION_API_KEY=
VISION_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果未配置 `VISION_API_KEY`，代码会回退使用 `QIANWEN_API_KEY`。

### 向量与 Chroma 配置

```env
QIANWEN_API_KEY=
QIANWEN_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

代码默认：

- 文本嵌入模型：`text-embedding-v4`
- 多模态嵌入模型：`qwen2.5-vl-embedding`
- Chroma 目录：`data/chroma`
- 记忆集合：`nonebot_agent_memory`
- 表情包集合：`images_description`

### MySQL 配置

```env
DB_URL=mysql+pymysql://root:你的密码@localhost:3306/nonebot_agent?charset=utf8mb4
```

务必使用 `utf8mb4`，否则 emoji 和部分 QQ 消息可能无法正确保存。

### 网络搜索配置

```env
WEB_SEARCH_API_KEY=
WEB_SEARCH_API_URL=https://open.bigmodel.cn/api/paas/v4/web_search
```

`search_from_internet` 工具会读取这两个变量。

### 豆包画图配置

```env
DOUBAO_API_KEY=
DOUBAO_API_URL=https://ark.cn-beijing.volces.com/api/v3
```

默认图片模型在 `nonebot_agent/tools/generate_image.py` 中：

```text
doubao-seedream-4-5-251128
```

### 主人权限

```env
MASTER_QQ=
```

只有 `MASTER_QQ` 可以执行：

- `/重启bot`
- `/设置情绪`
- `/skills reload`
- `/skills enable <name>`
- `/skills disable <name>`

### 聊天气泡与发送延迟

```env
CHAT_MAX_FOLLOWUPS=1
CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS=1200
CHAT_DELAY_BASE_MS=180
CHAT_DELAY_PER_CHAR_MS=28
CHAT_DELAY_JITTER_MS=320
```

这些配置控制聊天模式下多气泡追发数量和延迟。

### Skill 配置

```env
SKILLS_ENABLED=true
SKILLS_DIR=data/skills
SKILLS_AUTO_LOAD=true
SKILLS_MAX_ACTIVE=8
SKILLS_PROMPT_MAX_CHARS=6000
SKILLS_REFERENCE_TOP_K=4
SKILLS_REFERENCE_MAX_CHARS=5000
SKILLS_REFERENCE_MAX_FILE_CHARS=20000
SKILLS_REFERENCE_CHUNK_CHARS=1200
SKILLS_TOOL_TIMEOUT_SECONDS=30
SKILLS_STATE_FILE=data/skills/.skill_state.json
SKILLS_PREFIX_ALIASES=E:ai-li-xi-ya,e:ai-li-xi-ya
SKILL_EXCLUSIVE_CHAT_MAX_FOLLOWUPS=3
SKILLS_ALLOW_MCP=false
SKILLS_ALLOW_OPENAPI=true
SKILLS_ALLOW_LOCAL_CODE=false
SKILLS_SCRIPT_PYTHON=
SKILLS_SCRIPT_ALLOWLIST=
SKILLS_SCRIPT_TIMEOUT_SECONDS=10
SKILLS_SCRIPT_MAX_OUTPUT_CHARS=8000
SKILLS_REQUIRE_MASTER_CONFIRM_HIGH_RISK=true
```

### 主动聊天配置

```env
INDIVIDUAL_QQ=32983424,781542,12345
GROUP_QQ=936554,134,154,25
PROACTIVE_DAY_START_HOUR=9
PROACTIVE_DAY_END_HOUR=23
PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES=240
PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES=720
PROACTIVE_GROUP_MIN_INTERVAL_MINUTES=360
PROACTIVE_GROUP_MAX_INTERVAL_MINUTES=960
PROACTIVE_ONLINE_TOPIC_PROBABILITY=0.55
```

如果 `INDIVIDUAL_QQ` 和 `GROUP_QQ` 都为空，主动聊天后台循环不会启动。

## 启动方式

### 命令行启动

```powershell
conda activate QQBot
cd D:\projects\PythonProjects\New_QQBot_demo\NoneBot_Agent
python bot.py
```

看到 NoneBot 启动日志，并且 NapCat 显示 WebSocket 已连接，即表示基础连接正常。

### Windows 自动重启脚本

```powershell
.\start_bot.bat
```

`start_bot.bat` 会循环执行 `python bot.py`。当 `/重启bot` 调用 `os._exit(0)` 退出进程后，脚本会等待 3 秒再启动。

## QQ 使用方法

### 私聊

直接给机器人发送消息：

```text
你好
```

使用专业模式：

```text
/帮我解释一下 LangGraph 是什么
```

发送图片并提问：

```text
[图片] 这是什么
```

### 群聊

默认需要 @ 机器人：

```text
@机器人 今天吃什么
```

群管理员可以开启自由聊天：

```text
/自由聊天 开
/自由聊天 概率 30
```

开启后，机器人会记录群聊并按概率自然插话。

### 视频下载

发送抖音短链：

```text
https://v.douyin.com/xxxx/
```

或发送 B 站 QQ 分享卡片。命中后机器人会下载并发送视频，且不会再额外触发 Agent 聊天回复。

### 画图

```text
/画图 一只坐在图书馆窗边的白猫，暖色阳光，4K
```

图生图：

```text
[图片] /画图 保留人物，把背景换成赛博朋克街道
```

## 命令列表

| 命令 | 权限 | 说明 |
| --- | --- | --- |
| `/ping` | 所有人 | 测试机器人是否在线 |
| `/help`、`/帮助`、`/?` | 所有人 | 查看帮助 |
| `/status`、`/状态` | 所有人 | 查看模型、视觉、记忆等运行状态 |
| `/cleanup`、`/清理` | 所有人 | 清理过期聊天图片 |
| `/情绪`、`/心情`、`/emotion` | 所有人 | 查看当前私聊或群聊情绪状态 |
| `/画图`、`/draw`、`/generate`、`/生成图片` | 所有人 | 文生图或图生图 |
| `/自由聊天` | 群聊所有人 | 查看当前群自由聊天状态 |
| `/自由聊天 开` | 群主/管理员 | 开启自由聊天 |
| `/自由聊天 关` | 群主/管理员 | 关闭自由聊天 |
| `/自由聊天 概率 50` | 群主/管理员 | 设置自由聊天回复概率 |
| `/skills list` | 所有人 | 列出已加载 skill |
| `/skills info <name>` | 所有人 | 查看 skill 信息 |
| `/skills test <name> <消息>` | 所有人 | 测试某个 prompt skill 是否会注入 |
| `/skills reload` | 主人 | 重新加载本地 skills |
| `/skills enable <name>` | 主人 | 启用 skill |
| `/skills disable <name>` | 主人 | 禁用 skill |
| `/设置情绪 <情绪>` | 主人 | 手动设置当前上下文情绪 |
| `/重启bot`、`/重启`、`/restart` | 主人 | 退出当前进程，依赖外部脚本重启 |

可设置情绪：

```text
开心 / 低落 / 烦躁 / 困倦 / 撒娇 / 自信 / 平静
```

## Skill 扩展机制

### Skill 的类型

| 类型 | 来源 | 能力 |
| --- | --- | --- |
| 内置 callable skill | `nonebot_agent/tools/` | 可作为 OpenAI function tool 被 LLM 调用 |
| 本地 prompt-only skill | `data/skills/<name>/SKILL.md` | 根据触发词向系统 prompt 注入说明 |
| 本地脚本 skill | 白名单 Python 脚本 | 只在显式开启和白名单配置下可执行 |

### 添加 prompt-only skill

创建目录：

```text
data/skills/campus_chat/
```

创建文件：

```text
data/skills/campus_chat/SKILL.md
```

示例：

```markdown
---
name: campus_chat
display_name: 校园聊天话题
description: 让回复自然接入校园生活。
triggers:
  - 校园
  - 考试
  - 宿舍
modes:
  - chat
session_types:
  - c2c
  - group
risk_level: low
---

# 校园聊天话题

当用户聊到课程、考试、宿舍、食堂时，用真实同学的语气回应。
不要说自己启用了 skill。
```

重启机器人或执行：

```text
/skills reload
```

### Skill 前缀强制路由

`.env` 中：

```env
SKILLS_PREFIX_ALIASES=E:ai-li-xi-ya,e:ai-li-xi-ya
```

用户发送：

```text
/E 今天心情不太好
```

`parse_skill_prefix()` 会把这条消息路由到 `ai-li-xi-ya`，并进入 exclusive skill 模式。exclusive 模式会跳过默认人设，让指定 skill 成为本轮回复的角色和风格权威。

### 多文件 Skill 引用

本地 skill 目录下除了 `SKILL.md`，还可以放：

- `.md`
- `.txt`
- `.json`

`SkillReferenceIndex` 会按当前用户消息做轻量关键词检索，把相关片段注入 prompt。默认不会扫描：

- `scripts/`
- `.git/`
- `__pycache__/`

### 启用本地脚本 Skill

默认不允许执行本地代码：

```env
SKILLS_ALLOW_LOCAL_CODE=false
```

如确实需要，只允许白名单脚本：

```env
SKILLS_ALLOW_LOCAL_CODE=true
SKILLS_SCRIPT_PYTHON=D:\Miniconda3\envs\QQBot\python.exe
SKILLS_SCRIPT_ALLOWLIST=ai-li-xi-ya:scripts/nav.py
```

当前脚本适配器只允许这些动作：

```text
list / search / show / category
```

`show` 只能读取 skill 目录内的 `.md`、`.txt`、`.json`，并拒绝绝对路径和 `..` 路径穿越。

### 添加 callable tool

1. 在 `nonebot_agent/tools/` 下创建工具文件。
2. 使用 LangChain `@tool` 装饰器定义函数。
3. 在 `nonebot_agent/tools/__init__.py` 中导出。
4. 在 `nonebot_agent/skills/registry.py` 的 `register_builtin_tools()` 中加入该工具。

示意：

```python
from langchain.tools import tool


@tool(description="查询某个内部系统状态。")
def check_internal_status(name: str) -> str:
    return f"{name}: ok"
```

## 开发指南

### 修改机器人角色

编辑：

```text
nonebot_agent/agent/prompts.py
```

重点对象：

- `CHAT_MODE_PROMPT`
- `PROFESSIONAL_MODE_PROMPT`
- `EMOTION_STYLE_PROMPTS`

### 修改模式判断

当前逻辑在：

```text
nonebot_agent/agent/prompts.py
```

函数：

```python
get_mode_from_message(content: str)
```

规则是：以 `/` 开头进入专业模式，否则进入聊天模式。

### 修改消息处理

主入口：

```text
nonebot_agent/plugins/agent_chat.py
```

其中包含：

- 消息内容提取
- 群消息记录
- 私聊和 @ 处理
- 自由聊天
- 命令注册
- 画图命令
- 表情包标记解析

这个文件较大，新增功能时建议优先复用 `services/`、`memory/`、`tools/` 下已有模块，不要继续把所有逻辑堆到插件文件里。

### 修改 Agent 编排

编辑：

```text
nonebot_agent/agent/graph.py
```

主要节点：

- `llm_call`：组装 system prompt、消息、图片、tools，并调用 LLM。
- `tool_node`：执行 LLM 请求的工具。
- `should_continue`：判断是否继续工具调用循环。

工具调用最多 6 轮，避免无限循环。

### 修改记忆策略

相关文件：

| 文件 | 作用 |
| --- | --- |
| `memory_manager.py` | 记忆读写主流程 |
| `memory_writer.py` | 从用户消息抽取结构化记忆 |
| `memory_store.py` | 写入/更新 fact 和 event |
| `memory_summary.py` | 摘要刷新策略 |
| `response_guard.py` | 回复重复检测和改写 |

记忆条数配置在 `config.py`：

```python
SHORT_TERM_MEMORY_SIZE = 40
GROUP_SHORT_TERM_MEMORY_SIZE = 80
LONG_TERM_MEMORY_TOP_K = 20
MEMORY_FACT_TOP_K = 6
MEMORY_EVENT_TOP_K = 6
MEMORY_SUMMARY_TRIGGER_MESSAGES = 6
MEMORY_SUMMARY_SOURCE_LIMIT = 12
```

### 修改情绪策略

编辑：

```text
nonebot_agent/emotion/emotion_state.py
nonebot_agent/emotion/emotion_analyzer.py
```

时间衰减参数：

```python
DECAY_INTERVAL_MINUTES = 30
DECAY_RATE = 0.1
RESET_AFTER_HOURS = 2
NIGHT_START_HOUR = 23
NIGHT_END_HOUR = 6
```

## 测试与辅助脚本

### 自动单元测试

这些测试不应该依赖真实 QQ 或浏览器：

```powershell
python -m unittest discover -s nonebot_agent/test -p "test_*.py"
```

当前覆盖范围包括：

- 聊天气泡解析
- 结构化记忆抽取和检索参数
- 主动聊天策略
- 发送层追发取消
- Skill loader、router、executor、script allowlist
- 外部 URL 安全校验和调用入口拦截

### API 连通性测试

```powershell
python test.py
```

该脚本会读取 `LLM_API_KEY` / `LLM_API_URL` 并列出模型。需要真实网络和 API key。

### 手工/实验脚本

以下文件更偏数据准备或外部服务验证，运行前需要检查路径、API key、浏览器和数据目录：

| 文件 | 用途 |
| --- | --- |
| `nonebot_agent/test/auto_description.py` | 给表情包图片生成描述 CSV |
| `nonebot_agent/test/chroma_operation.py` | 把 CSV 写入 Chroma 并检索 |
| `nonebot_agent/test/chroma_collections_test.py` | 检查 Chroma 集合 |
| `nonebot_agent/test/bilibili_spider_test.py` | B 站下载器实验 |
| `nonebot_agent/test/douyin_spider_test.py` | 视频下载实验 |
| `nonebot_agent/test/address_qqdocurl_test.py` | B 站 QQ 卡片解析实验 |

## 运行数据与安全注意事项

- `.env` 包含 API key 和数据库密码，不要提交。
- `data/chroma/`、`data/images/`、`data/videos/` 是运行时数据，不要提交。
- `nonebot_agent/utils/browser_data/` 和 `nonebot_agent/utils/bili_browser_data/` 是 DrissionPage 浏览器缓存，不要提交。
- 抖音/B站下载依赖页面结构和平台策略，可能随平台更新失效。
- 网页读取和视频下载只允许公网 HTTP/HTTPS URL，不会访问本机、内网、链路本地或保留 IP。
- `/重启bot` 会直接 `os._exit(0)`，需要 `start_bot.bat`、systemd、supervisor 或其他外部进程管理器拉起。
- 开启主动聊天前，应谨慎设置目标 QQ 和群号，避免打扰用户。
- 开启 `SKILLS_ALLOW_LOCAL_CODE=true` 前必须确认脚本来源可信，并使用白名单。

## 常见问题

### 机器人不回复

检查顺序：

1. NapCatQQ 是否在线。
2. 反向 WebSocket 是否连接到 `ws://127.0.0.1:8080/onebot/v11/ws`。
3. `.env` 的 `HOST`、`PORT`、`ONEBOT_ACCESS_TOKEN` 是否和 NapCat 一致。
4. NoneBot 控制台是否有红色异常。
5. LLM API key、base URL 和模型名是否正确。

### 调用模型时出错

常见原因：

- `LLM_API_KEY` 为空或无效。
- `LLM_API_URL` 不是 OpenAI-compatible 地址。
- 模型名不被该服务商支持。
- `extra_body` 中的模型特定参数不被后端接受。
- 网络无法访问模型服务。

### 图片无法理解

检查：

- 主模型是否真的支持图片。
- `IS_MULTIMODAL_MODEL` 是否设置正确。
- 文本模型模式下是否配置了 `VISION_MODEL` 和 `VISION_API_KEY`。
- QQ 图片 URL 是否能被模型服务访问；不能访问时需要依赖本地 base64。

### 数据库连接失败

检查：

- MySQL 服务是否启动。
- 数据库是否已创建。
- `DB_URL` 用户名、密码、端口是否正确。
- 数据库字符集是否是 `utf8mb4`。
- 是否执行过 `python init_db.py` 或 `python migrate_db.py`。

### 记忆不生效

检查：

- `QIANWEN_API_KEY` 是否可用。
- `data/chroma/` 是否可写。
- `memory_facts`、`memory_events`、`conversation_summaries` 表是否存在。
- 当前消息是否像事实或近况。问题、短句和 URL 默认不会写入结构化长期记忆。

### 表情包工具报错

检查：

- 是否安装 `langchain-openai`。
- `data/images/stickers/` 是否有表情包文件。
- Chroma 中是否存在 `images_description` 集合。
- `QIANWEN_API_KEY` 和 `QIANWEN_API_URL` 是否可用。

### 视频下载失败

检查：

- Chromium/Chrome 是否可被 DrissionPage 启动。
- B 站下载是否安装 FFmpeg 并加入 PATH。
- 平台是否需要登录、验证码或反爬验证。
- `data/videos/` 是否可写。
- 链接是否为公网 HTTP/HTTPS 地址；本机、内网、`file://`、`ftp://` 会被直接拒绝。

### `/重启bot` 后没有重新启动

`/重启bot` 只会退出当前 Python 进程。需要使用：

```powershell
.\start_bot.bat
```

或其他进程管理器启动，才能自动拉起。

## License

MIT License
