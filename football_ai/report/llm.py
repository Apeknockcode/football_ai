"""
可选 LLM 润色：将模板报告润色为更连贯的中文。需配置 report.llm.enabled、provider 与 API key。
"""
import os
from typing import Any


def polish_report(
    raw_text: str,
    report_type: str,
    version: str,
    config: dict[str, Any] | None = None,
) -> str:
    """
    调用 LLM 对 raw_text 做润色，保持事实与数据不变、仅改善表述。
    :param config: report.llm 配置（enabled, provider, api_key, model）
    :return: 润色后文本；失败或未配置则返回 raw_text
    """
    if not config or not config.get("enabled"):
        return raw_text
    provider = (config.get("provider") or "").strip().lower()
    if provider == "openai":
        return _polish_openai(raw_text, report_type, version, config)
    return raw_text


def _polish_openai(raw_text: str, report_type: str, version: str, config: dict[str, Any]) -> str:
    api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return raw_text
    model = config.get("model") or "gpt-4o-mini"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = (
            "请将以下足球赛前/赛后分析报告润色为更流畅、专业的中文，"
            "严格保持所有数字、百分比、队名、轮次、时间等事实不变，仅优化语句与段落衔接。"
            "直接输出润色后的完整报告，不要加解释。\n\n"
        ) + raw_text
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
            return resp.choices[0].message.content.strip()
    except Exception:
        pass
    return raw_text
