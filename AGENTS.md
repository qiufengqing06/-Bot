# AGENTS.md — Claude Code 开发约束

## 环境
- **Conda 环境**: `QQBot`，Python 3.11
- 所有命令执行前先 `conda activate QQBot`
- Windows 系统，项目路径: `D:\projects\PythonProjects\New_QQBot_demo\NoneBot_Agent`

---

## 🔴 敏感信息 — 红线规则（修改任何文件前必读）

**以下内容绝对禁止写入任何会被 git 跟踪的文件，包括代码注释、docstring、日志输出：**

- API Key / Token / Secret（任何形式，包括 base64 编码后的）
- 数据库连接字符串（含用户名、密码、IP）
- QQ 号、群号（`MASTER_QQ`、`INDIVIDUAL_QQ`、`GROUP_QQ` 等）
- 内网 IP、服务器地址、SSH 端口
- Cookie、Session Token、JWT
- 任何第三方服务的账号密码

**禁止提交的目录和文件类型：**
- `.env` `.env.*` `*.key` `*secret*` `*.pem` `*.token`
- `data/browser_data/` `data/bili_browser_data/`（含 Cookies、LocalStorage、History）
- `data/chroma/` `data/images/` `data/videos/` `data/skills/.skill_state.json`
- `.tmp/` `*.log` `*.sqlite` `*.sqlite3` `*.db`
- `__pycache__/` `*.pyc` `.pytest_cache/`

**每次 commit 前的自查清单：**
1. `git diff --cached` 逐行确认没有敏感值
2. `.env.example` 中的值是空字符串或占位符，不能是真实值
3. 测试文件中的 API key 必须是 `os.getenv()` 读取，不能写死
4. 浏览器自动化代码中的 Cookie/UserData 路径必须指向 `.gitignore` 覆盖的目录

**如果误提交了敏感信息：**
- 立即 `git reset` 撤销最近 commit，不要 push
- 如果已经 push，立即轮换所有泄露的 key/token

---

## 架构约束
- `nonebot_agent/plugins/agent_chat.py` 已拆分至 342 行，**禁止再往里面加新功能**。新增命令、处理器必须拆到 `plugins/commands/` 下独立文件
- LLM 调用**不能假设模型特定参数**：`extra_body` 中的 `repetition_penalty`、`thinking` 等是 DeepSeek 专属。使用 `agent/llm_provider.py` 的 `get_provider()` 按 provider 分派参数
- 人设/角色 prompt 不能硬编码在代码里，必须可配置
- 任何调用外部 API 的地方（LLM、Vision、WebSearch、ImageGen）必须用 `os.getenv()` 读 key，禁止写死

## 依赖
- NoneBot2 + OneBot V11 adapter
- LangChain 0.3.x / LangGraph 0.2+ / langchain-openai
- SQLAlchemy + PyMySQL（MySQL 数据库）
- ChromaDB（向量记忆）
- DrissionPage（浏览器自动化）
- 豆包 SDK / dashscope

## Git
- 仓库: `git@github.com:qiufengqing06/-Bot.git`
- commit message 用中文，简明描述改动
- **每次提交前必须执行敏感信息检查**

## 代码规范
- 修改后运行 `python -m pytest nonebot_agent/test/ -x --tb=short` 确保不破坏现有测试
- 新增功能必须加测试
- 日志用 `nonebot.log.logger`，不用 `print()`
