# NoneBot Agent 改进路线

本文档记录项目后续可以推进的改进方案。README 负责说明当前项目如何理解、部署和使用；本文件负责描述下一步如何把项目做得更稳定、更安全、更容易维护。

## 总体判断

项目已经具备完整 Bot 闭环：消息接入、Agent 编排、工具调用、记忆、情绪、视频下载、画图、Skill 扩展和主动聊天都已经落地。当前主要问题不在“功能缺失”，而在以下方面：

- 插件层文件过大，消息处理、命令、业务逻辑和外部调用混在一起。
- 配置项多，但缺少启动前校验和错误提示。
- 数据库迁移依赖手写 SQL，长期维护风险较高。
- 外部 API、浏览器自动化、视频下载和 Skill 脚本都有安全和稳定性边界。
- 测试覆盖了部分纯逻辑，但对插件流程、数据库、工具调用和模型调用的隔离测试不足。
- 部署主要依赖本地脚本，缺少服务化、日志、健康检查和故障恢复方案。

## 优先级路线

### P0：先做稳定性和安全基线

这些改动优先级最高，因为它们直接影响机器人能否长期运行。

1. 增加启动前配置校验。
2. 修正依赖声明，确保 `pip install -e .` 后能直接启动。
3. 引入正式数据库迁移工具。
4. 为外部工具增加超时、重试、错误分类和降级回复。
5. 为主动聊天、视频下载、画图和脚本 Skill 加权限与频率限制。
6. 清理运行时数据和浏览器缓存的生命周期策略。

### P1：再做架构拆分和测试体系

这些改动提升可维护性，避免后续新增功能继续堆积。

1. 拆分 `agent_chat.py`。
2. 抽象 LLM、Vision、Embedding、Image Generation provider。
3. 合并或删除重复的主动聊天实现。
4. 引入可 mock 的 Bot adapter 测试。
5. 将单元测试、集成测试、外部服务测试分层。
6. 统一日志结构和 trace id。

### P2：最后做体验和功能增强

这些改动提升用户体验，但不应该早于稳定性和架构基线。

1. 增加记忆管理命令。
2. 增加主动聊天策略配置命令。
3. 增加表情包和生成图片的管理工具。
4. 增加简单 Web 管理面板。
5. 增加 Docker Compose 或 Windows 服务部署方案。

## 详细改进方案

### 1. 配置与依赖治理

#### 问题

当前 `.env.example` 配置项较多，但代码没有统一校验必填项。部分模块在 import 时就读取 API key 或初始化客户端，导致缺配置时错误位置不直观。

另外，当前代码中 `send_stickers.py` 和部分测试引用了 `langchain_openai`，但 `pyproject.toml` 没有明确声明 `langchain-openai` 依赖。

#### 建议

1. 用 Pydantic Settings 或自定义校验器替换普通 `os.getenv` 聚合。
2. 启动时输出配置检查结果，但不输出密钥原文。
3. 按功能分组校验：
   - 基础运行：OneBot、LLM、DB。
   - 图片理解：Vision 配置。
   - 长期记忆：Embedding 配置。
   - 搜索：WebSearch 配置。
   - 画图：Doubao 配置。
   - 视频：Chromium/FFmpeg。
4. 修正 `pyproject.toml` 依赖：
   - 增加 `langchain-openai`。
   - 检查 `langchain-core==1.2.7` 和 `langchain==0.3.25` 的兼容性。
   - 将浏览器下载、画图、测试依赖拆到 optional dependencies。

#### 验收标准

- 缺少主 LLM key 时，启动日志直接说明缺少 `LLM_API_KEY`。
- 未配置搜索 API 时，聊天功能仍可启动，搜索工具返回明确降级信息。
- 新环境执行 `pip install -e .` 后不再因缺少 `langchain_openai` 启动失败。

### 2. 数据库迁移正规化

#### 问题

项目有 `init_db.py` 和 `migrate_db.py`，但迁移逻辑是手写 SQL。随着表结构继续变化，容易出现重复字段、不同数据库版本兼容问题和不可回滚问题。

#### 建议

1. 引入 Alembic。
2. 将当前 ORM 状态作为 baseline migration。
3. 以后新增字段和索引用 migration 文件管理。
4. 启动时只做轻量检查，不在运行期自动修改表结构。
5. 提供命令：

```powershell
alembic upgrade head
alembic current
alembic history
```

#### 验收标准

- 新库可以通过 migration 创建所有表。
- 旧库可以从当前版本升级到最新版本。
- 不再依赖 `migrate_db.py` 手工维护每次结构变更。

### 3. 插件层拆分

#### 问题

`nonebot_agent/plugins/agent_chat.py` 同时承担：

- 群设置读写
- 权限检查
- 用户昵称获取
- 表情包解析
- 消息段解析
- 群消息记录
- Agent 入口
- cleanup/ping/help/status/skills/freechat/restart/emotion/draw 命令

文件过大，后续维护容易引入回归。

#### 建议拆分

```text
nonebot_agent/plugins/agent_chat.py          # 只保留 handler 注册
nonebot_agent/plugins/commands/basic.py      # ping/help/status/cleanup
nonebot_agent/plugins/commands/emotion.py    # 情绪相关命令
nonebot_agent/plugins/commands/free_chat.py  # 自由聊天命令
nonebot_agent/plugins/commands/skills.py     # skills 命令
nonebot_agent/plugins/commands/draw.py       # 画图命令
nonebot_agent/plugins/commands/restart.py    # 重启命令
nonebot_agent/plugins/message_parser.py      # OneBot 消息段解析
nonebot_agent/plugins/group_settings.py      # 群配置读写和权限判断
nonebot_agent/plugins/sticker_sender.py      # sticker marker 转 MessageSegment
```

#### 验收标准

- `agent_chat.py` 只负责注册主消息 handler 和组装调用。
- 每类命令可以单独测试。
- 新增命令不需要修改一个千行级文件。

### 4. Agent Provider 抽象

#### 问题

当前主 LLM、视觉模型、情绪分析、重复改写、画图参数抽取都直接创建 OpenAI client。不同模型后端对 `extra_body`、工具调用、图片输入、seed、thinking 参数支持不一致。

#### 建议

1. 增加 provider 层：

```text
nonebot_agent/providers/llm.py
nonebot_agent/providers/vision.py
nonebot_agent/providers/embedding.py
nonebot_agent/providers/image_generation.py
```

2. 将模型能力显式建模：

```python
supports_tools: bool
supports_images: bool
supports_seed: bool
supports_extra_body: bool
```

3. 按 provider 生成请求参数，避免对所有模型硬塞同一组参数。
4. 提供统一错误类型：
   - authentication error
   - rate limit
   - bad request
   - timeout
   - provider unavailable

#### 验收标准

- 切换 DeepSeek、Qwen、OpenAI-compatible 中转时，只改 `.env` 或 provider 配置。
- 不支持 `extra_body` 的后端不会因参数不兼容失败。
- 工具调用失败可以降级为无工具回答。

### 5. 记忆系统增强

#### 当前优点

当前已经避免直接存储完整问答对，而是抽取用户事实和事件。这比传统“把整段对话塞进向量库”更不容易导致复读。

#### 可改进点

1. 记忆抽取从启发式规则升级为可选 LLM 抽取。
2. 给每条记忆增加重要性、置信度和过期时间。
3. 增加用户可控命令：

```text
/记忆
/记忆 搜索 <关键词>
/记忆 删除 <id>
/记忆 清空
/记忆 导出
```

4. 对群聊记忆区分：
   - 当前用户事实
   - 群共同上下文
   - 某用户在某群中的近况
5. 为 Chroma 和 MySQL 的结构化记忆建立一致性检查脚本。

#### 验收标准

- 用户可以查看和删除自己的长期记忆。
- 过期近况不会长期影响回复。
- Chroma 文档丢失或重复时有修复脚本。

### 6. 工具调用安全和权限

#### 当前进展

- 已增加统一 URL 安全校验模块，`read_webpage` 和视频下载入口会拒绝 `file://`、非 HTTP(S)、本机、内网、链路本地和保留 IP 地址。

#### 问题

网络搜索、网页读取、视频下载、画图和本地脚本执行都有资源消耗和安全边界。当前已有脚本白名单，但其他工具还缺少统一权限控制。

#### 建议

1. 在 SkillSpec 中落实权限字段：

```text
network.search
network.read_url
media.download
image.generate
filesystem.read
local.exec
qq.send_media
```

2. 建立工具调用策略：
   - 普通用户可用哪些工具。
   - 群聊是否允许下载大视频。
   - 每用户/每群频率限制。
   - 高风险工具是否需要主人确认。
3. 给 `read_webpage` 增加 URL 校验：
   - 拒绝内网地址。已完成。
   - 拒绝 file://。已完成。
   - 限制响应大小。
   - 限制跳转次数。
4. 给视频下载增加大小限制和并发限制。

#### 验收标准

- 普通用户不能触发本地脚本。
- 群聊里频繁发视频链接不会导致下载任务堆积。
- 网页读取不能访问本机管理端口或内网地址。

### 7. 主动聊天治理

#### 问题

主动聊天是体验敏感功能。发送太频繁会打扰用户，话题来源质量低会显得突兀。

#### 建议

1. 增加 QQ 命令管理主动聊天：

```text
/主动聊天 状态
/主动聊天 开
/主动聊天 关
/主动聊天 间隔 240 720
/主动聊天 目标 添加 <qq或群>
/主动聊天 目标 删除 <qq或群>
```

2. 群聊主动消息默认关闭，只允许管理员开启。
3. 每个目标持久化冷却状态，而不是只存在内存。
4. 主动话题来源增加质量评分。
5. 加入“最近用户是否反感”判断，例如用户明确说“别主动找我”后自动关闭。

#### 验收标准

- 主动聊天目标和开关不依赖手改 `.env`。
- 重启后仍保留每个目标的冷却时间和开启状态。
- 用户或群管理员可以关闭主动聊天。

### 8. 视频下载稳定性

#### 问题

抖音和 B 站解析依赖页面结构、浏览器状态和平台反爬。长期运行时容易遇到浏览器缓存膨胀、验证码、端口冲突、下载失败等问题。

#### 建议

1. 将下载任务放入队列，限制并发。
2. 下载前检查文件大小和剩余磁盘空间。
3. 为 `DrissionPage` 浏览器实例增加统一生命周期管理。
4. B 站下载前检测 FFmpeg 是否存在。
5. 对失败类型分类：
   - 链接无效
   - 登录/验证码
   - 解析失败
   - 下载超时
   - FFmpeg 合并失败
6. 增加定期清理：
   - 临时音视频
   - 超过保留期的视频
   - 浏览器缓存

#### 验收标准

- 多个视频链接不会同时启动多个互相冲突的浏览器实例。
- FFmpeg 缺失时给出明确提示。
- 临时文件不会长期堆积。

### 9. 测试体系分层

#### 问题

当前已有不错的纯逻辑 unittest，但外部依赖测试和手工脚本混在 `nonebot_agent/test/` 下，测试边界不够清晰。

#### 建议

1. 调整目录：

```text
tests/unit/
tests/integration/
tests/manual/
```

2. 单元测试只测纯逻辑和 mock 后的服务。
3. 集成测试使用临时数据库或 Docker MySQL。
4. 外部 API、真实浏览器、真实 QQ 的测试放到 manual。
5. 增加 CI 可运行命令：

```powershell
python -m unittest discover -s tests/unit
```

6. 对核心链路增加测试：
   - skill prefix 不误伤普通命令。
   - tool schema 正确暴露。
   - ChatResponsePlan 对异常 LLM 输出可降级。
   - MemoryWriter 不把问题写入长期记忆。
   - ResponseGuard 命中相似回复时调用改写。

#### 验收标准

- 无 API key 的环境也能跑完单元测试。
- 手工测试不会被默认 discover 误跑。
- 每个 bugfix 都能加对应回归测试。

### 10. 可观测性和运维

#### 问题

当前主要依赖控制台日志。出问题时难以把一次 QQ 消息、一次 LLM 请求、一次工具调用和一次数据库写入串起来。

#### 建议

1. 每条进入 Agent 的消息生成 `trace_id`。
2. 日志统一结构：

```text
trace_id
session_type
user_id
group_id
mode
skill_override
llm_model
tool_name
latency_ms
```

3. 增加健康检查：
   - DB 是否可连接
   - Chroma 是否可写
   - LLM 是否可用
   - NapCat 是否连接
4. 增加运行指标：
   - 消息数
   - LLM 调用次数
   - tool 调用次数
   - 错误数
   - 主动消息发送数
   - 视频下载成功/失败数

#### 验收标准

- 用户报告“刚才没回复”时，可以用 trace_id 定位失败阶段。
- 长期运行时可以看到错误率和工具调用耗时。

### 11. 部署方式改进

#### 当前方式

Windows 下通过：

```powershell
.\start_bot.bat
```

循环拉起进程。

#### 建议

1. 增加 Windows 服务部署说明，或提供 NSSM 配置。
2. 增加 Docker Compose：
   - bot
   - MySQL
   - Chroma 数据卷
3. 日志写入文件并按天轮转。
4. 优雅关闭后台任务，减少直接 `os._exit(0)` 对资源清理的影响。
5. 增加备份策略：
   - MySQL dump
   - Chroma 目录备份
   - `data/skills` 备份

#### 验收标准

- 机器重启后 Bot 能自动恢复。
- 日志和数据有明确保留策略。
- 迁移到另一台机器时有可执行步骤。

## 建议执行顺序

### 第一阶段：一周内可完成

1. 修正依赖声明。
2. 增加启动配置校验。
3. 拆分 `agent_chat.py` 中的命令处理。
4. 清理或标记 `proactive_service.py` 与 `proactive_runtime.py` 的关系。
5. 增加 URL 安全校验和工具超时降级。URL 安全校验已完成。

### 第二阶段：两到三周

1. 引入 Alembic。
2. 建立 provider 抽象。
3. 重构测试目录。
4. 增加更多 mock 单元测试。
5. 增加 trace_id 和结构化日志。

### 第三阶段：长期演进

1. 记忆管理命令。
2. 主动聊天管理命令。
3. Web 管理面板。
4. Docker Compose 或服务化部署。
5. 更强的 Skill 权限和确认机制。

## 不建议优先做的事

- 不建议立刻继续堆新命令到 `agent_chat.py`。
- 不建议在没有权限模型前开放更多本地脚本能力。
- 不建议把所有历史聊天原文重新塞进长期向量库。
- 不建议在没有频率限制前增强视频下载和画图的开放能力。
- 不建议把部署依赖继续只写在个人机器路径里。

## 最小可交付改进包

如果只做一个小版本，建议目标是：

1. README 和文档更新。
2. `pyproject.toml` 补依赖。
3. 配置启动校验。
4. `agent_chat.py` 命令拆分第一步。
5. 单元测试命令稳定可运行。

这个版本不会改变用户侧行为，但会显著降低新环境部署和后续开发成本。
