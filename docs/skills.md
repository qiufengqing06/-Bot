# Skills Compatibility Layer

This project now supports a first version of a skill compatibility layer.

## What Works Now

- Built-in LangChain tools are registered automatically as callable skills:
  - `search_from_internet`
  - `read_webpage`
  - `search_stickers_tool`
  - `send_sticker_by_url`
- Local prompt-only skills can be loaded from `data/skills/<skill_name>/SKILL.md`.
- Prompt-only skills add instructions to the agent prompt when their triggers match the user message.
- Multi-file skills can contribute relevant snippets from `.md`, `.txt`, and `.json` reference files.
- Slash-prefix overrides can force a specific skill to lead a turn, for example `/E`.
- `/skills` commands can list, inspect, reload, enable, disable, and test local skills.

## What Is Not Enabled Yet

- MCP servers are planned but disabled by default.
- OpenAPI/GPT Actions import is planned but not implemented in this MVP.
- Local script execution is supported only for explicit allowlist entries.

## Configuration

Add or adjust these values in `.env`:

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

## Add A Prompt-Only Skill

Create a folder:

```text
data/skills/my_skill/
```

Create `data/skills/my_skill/SKILL.md`:

```markdown
---
name: my_skill
display_name: My Skill
description: Helps the bot respond in a more specific style.
triggers:
  - keyword1
  - keyword2
modes:
  - chat
  - professional
session_types:
  - c2c
  - group
risk_level: low
---

# My Skill

When the user message matches the triggers, follow these instructions.
Keep responses natural and do not mention that a skill was used.
```

Restart the bot after adding a new local skill.

## Use A Skill Override Prefix

`SKILLS_PREFIX_ALIASES` maps slash prefixes to skill names.

Current default:

```env
SKILLS_PREFIX_ALIASES=E:ai-li-xi-ya,e:ai-li-xi-ya
```

This means messages like these force `ai-li-xi-ya` to lead the reply:

```text
/E 爱莉希雅，今天心情不太好
/e 真我这个刻印是什么
```

In exclusive mode, the bot skips its normal persona prompt and uses the selected skill as the role/style authority.
This pattern can support future skills by adding more aliases:

```env
SKILLS_PREFIX_ALIASES=E:ai-li-xi-ya,e:ai-li-xi-ya,K:kiana-roleplay
```

## Manage Skills In QQ

Available commands:

```text
/skills list
/skills info <name>
/skills reload
/skills enable <name>
/skills disable <name>
/skills test <name> <message>
```

`reload`, `enable`, and `disable` require `MASTER_QQ`.

## Run Whitelisted Scripts

Script execution is intentionally narrow. A script is registered only when all conditions are true:

- `SKILLS_ALLOW_LOCAL_CODE=true`
- The script appears in `SKILLS_SCRIPT_ALLOWLIST`
- The script path stays inside the skill directory
- The script is a `.py` file
- The script adapter knows how to validate its arguments

Current Elysia example:

```env
SKILLS_ALLOW_LOCAL_CODE=true
SKILLS_SCRIPT_PYTHON=D:\Miniconda3\envs\QQBot\python.exe
SKILLS_SCRIPT_ALLOWLIST=ai-li-xi-ya:scripts/nav.py
SKILLS_SCRIPT_TIMEOUT_SECONDS=10
SKILLS_SCRIPT_MAX_OUTPUT_CHARS=8000
```

This registers a callable tool named:

```text
ai-li-xi-ya_nav
```

Supported actions for `nav.py`:

```text
list
search
show
category
```

Safety behavior:

- The script runs with `shell=False`.
- The working directory is the skill root.
- Output is truncated by `SKILLS_SCRIPT_MAX_OUTPUT_CHARS`.
- Timeout is controlled by `SKILLS_SCRIPT_TIMEOUT_SECONDS`.
- The subprocess receives a minimal environment and does not inherit API keys from `.env`.
- `show` rejects absolute paths and `..` path traversal, so it cannot read files outside the skill directory.

## Add A Callable Tool Skill

For now, callable skills should still be implemented as LangChain tools under `nonebot_agent/tools/`.
After creating the tool, export it in `nonebot_agent/tools/__init__.py`, then register it in
`nonebot_agent/skills/registry.py` inside `register_builtin_tools()`.

Future versions can add adapters for OpenAPI and MCP without changing `nonebot_agent/agent/graph.py`.

## Safety Notes

- Do not download random skills that execute local code.
- Do not allow skills to read `.env`.
- Do not let external skills send QQ messages directly; they should return intent/results and let the existing sender layer handle output.
- Treat MCP and script-based skills as high risk until an approval flow is implemented.
