# AGENTS.md — Claude Code 开发约束

## 环境
- **Conda 环境**: `QQBot`，Python 3.11
- 所有命令执行前先 `conda activate QQBot`
- Windows 系统，项目路径: `D:\projects\PythonProjects\New_QQBot_demo\NoneBot_Agent`

## 架构约束
- `nonebot_agent/plugins/agent_chat.py` 已 1171 行，**禁止再往里面加新功能**。新增命令、处理器必须拆到独立文件
- LLM 调用**不能假设模型特定参数**：`extra_body` 中的 `repetition_penalty`、`thinking` 等是 DeepSeek 专属，对其他 provider（Qwen/OpenAI/Gemini）会炸。需要按 provider 分派
- 浏览器缓存 (`utils/browser_data/`) **不能在项目目录内**，移到 `data/` 下
- 人设/角色 prompt 不能硬编码在代码里，必须可配置

## 依赖
- NoneBot2 + OneBot V11 adapter
- LangChain 0.3.x / LangGraph 0.2+ / langchain-openai
- SQLAlchemy + PyMySQL（MySQL 数据库）
- ChromaDB（向量记忆）
- DrissionPage（浏览器自动化）
- 豆包 SDK / dashscope

## Git
- 仓库: `git@github.com:qiufengqing06/-Bot.git`
- 修改完成后提交，commit message 用中文，简明描述改动
- 不要提交 `.env`、`data/chroma/`、`data/images/`、`data/videos/`、`data/browser_data/`、`__pycache__/`、`*.pyc`

## 代码规范
- 修改后运行 `python -m pytest nonebot_agent/test/ -x --tb=short` 确保不破坏现有测试
- 新增功能必须加测试
- 日志用 `nonebot.log.logger`，不用 `print()`
