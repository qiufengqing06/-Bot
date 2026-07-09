import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot_agent.config_validation import (
    assert_runtime_config,
    format_config_issues,
)


config_issues = assert_runtime_config()
warnings = [issue for issue in config_issues if issue.level == "warning"]
if warnings:
    print(format_config_issues(warnings))

# 初始化 NoneBot
nonebot.init()

# 获取驱动器
driver = nonebot.get_driver()

# 注册 OneBot V11 适配器
driver.register_adapter(OneBotV11Adapter)

# 从 pyproject.toml 加载插件
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
