"""
Simple connectivity test for the active Conda QQBot environment.

Usage:
    python test.py
"""
import os

from openai import OpenAI


def main() -> None:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("LLM_API_URL") or os.getenv("DEEPSEEK_API_URL") or "https://api.deepseek.com/v1"

    if not api_key:
        raise RuntimeError("请先在当前 Conda 环境加载的 .env 中配置 LLM_API_KEY 或 DEEPSEEK_API_KEY")

    client = OpenAI(api_key=api_key, base_url=base_url)
    models = client.models.list()
    for model in models.data[:10]:
        print(model.id)


if __name__ == "__main__":
    main()
