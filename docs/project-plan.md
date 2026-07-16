# NoneBot Agent 项目完善计划

> 目标：将一个能跑的 QQ Bot 升级为可以写进简历的工程级项目

---

## 一、当前状态

### 已完成（22 commits）
- ✅ 代码模块化拆分（agent_chat.py 1171→342行）
- ✅ Git 管理 + 敏感信息防护（.gitignore 全拦截）
- ✅ 人设 Skill 化（天雨雪从硬编码迁移到 SKILL.md）
- ✅ 动态时间状态注入（早困→晚活跃）
- ✅ 沉默机制（10%随机不回复）
- ✅ LLM 语义记忆提取（从正则→LLM 理解）
- ✅ 记忆管理命令（/记忆 查看/删除/清空）
- ✅ 回复重复检测（窗口6→20，阈值0.82→0.70）
- ✅ 视频下载修复（抖音HTML回退 + B站直链检测）
- ✅ DB 会话加固 + Chroma 降级 + trace_id 全链路追踪
- ✅ print→logger 统一日志 + draw.py provider 规范化
- ✅ README 致谢声明

### 正在执行
- 🔄 代码瘦身：情绪系统 | 主动聊天合并 | 记忆模块拆分
- 🔄 LangChain/LangGraph 升级（0.3.x→1.3.x）

---

## 二、离"简历级"还差什么

### 🔴 P0 — 致命短板（面试官一眼看出不专业）

| 项目 | 现状 | 目标 |
|---|---|---|
| **测试** | 0% 覆盖率，7个手工脚本 | pytest 单测 ≥60%，核心链路全覆盖 |
| **CI/CD** | 无 | GitHub Actions：push→lint→test |
| **数据库迁移** | migrate_db.py 手写SQL | Alembic 版本化管理 |
| **配置管理** | 裸 os.getenv() | Pydantic Settings 强类型校验 |

### 🟡 P1 — 明显短板（懂行的人会说不够工程化）

| 项目 | 现状 | 目标 |
|---|---|---|
| **类型标注** | partial | pyright standard 零错误 |
| **日志系统** | 有 trace_id 但非结构化 | JSON 结构化日志 |
| **异常处理** | 部分有 try/except | 统一错误类型，全链路兜底 |
| **依赖锁定** | pyproject.toml 无 lock | pip freeze → requirements.txt |
| **架构文档** | README 很全 | ARCHITECTURE.md + 模块图 |

### 🟢 P2 — 锦上添花

| 项目 | 说明 |
|---|---|
| **Docker 部署** | Dockerfile + docker-compose.yml |
| **健康检查** | /health 端点：DB/Chroma/LLM/NapCat 连通性 |
| **pre-commit** | 本地提交前自动 ruff + pyright |
| **性能监控** | LLM 延迟统计、请求量、错误率 |

---

## 三、分步执行计划

### 第一阶段：工程基建（1-2天）

```
1.1 Pydantic Settings 配置改造
    - 替换 os.getenv() → pydantic-settings BaseSettings
    - 分组校验：LLM/DB/Vision/Memory/Video
    - 启动时打印校验报告（不泄漏 key）
    文件：config.py, config_validation.py

1.2 pytest 单元测试框架搭建
    - 先写 10 个核心函数测试：
      ChatResponsePlan 解析、MemoryWriter 提取
      URL 安全校验、Skill 路由、情绪标签映射
    - Mock 外部依赖（API/DB/Chroma）
    - pytest.ini 配置 + conftest.py fixtures
    目录：tests/unit/, tests/integration/

1.3 GitHub Actions CI
    - .github/workflows/test.yml
    - 触发：push + PR
    - 流程：setup python → install deps → ruff lint → pytest
    - 不需要 MySQL/Chroma（用 mock）
```

### 第二阶段：专业化（3-5天）

```
2.1 Alembic 数据库迁移
    - 从现有 models.py 生成 baseline migration
    - 删除 migrate_db.py
    - 文档化迁移命令

2.2 类型标注清零
    - 逐步修 pyright 报错
    - 重点：agent/graph.py, memory/, services/

2.3 架构文档
    - ARCHITECTURE.md：模块图 + 数据流 + 设计决策
    - API 文档：docstring Google 风格

2.4 依赖锁定
    - pip freeze → requirements.txt
    - 区分 production vs dev 依赖
```

### 第三阶段：打磨（持续）

```
3.1 Docker 一键部署
3.2 结构化日志 + 健康检查
3.3 pre-commit hooks
3.4 性能基准测试
```

---

## 四、不建议做的事

- ❌ 继续堆新功能（在基建做完之前）
- ❌ 引入新的重依赖（加重维护负担）
- ❌ 过度设计（比如微服务拆分——这是单体 Bot）
