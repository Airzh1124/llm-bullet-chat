from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


SYSTEM_PROMPT = "你只输出可解析的 JSON 数组。"

PROMPT_TEMPLATE = """你正在模拟一个 B 站直播间的实时观众弹幕。根据当前屏幕内容，生成 5 条自然的中文弹幕。
要求：
* 每条 6 到 18 个字
* 像真实观众，不要太像 AI
* 可以吐槽、惊讶、提问、玩梗
* 不要恶意攻击
* 不要色情内容
* 不要政治极端内容
* 不要编号
* 不要重复最近已经出现过的弹幕
* 只输出 JSON 数组

最近已经出现过的弹幕：
{recent_bullets}

当前屏幕内容：
{screen_context}

期望输出：["这波有点抽象", "主播在干啥哈哈", "我好像看懂了", "这图有点关键", "等下这不对吧"]"""


class DanmakuGenerator(ABC):
    @abstractmethod
    def generate(self, screen_context: str, recent_bullets: list[str] | None = None) -> list[str]:
        raise NotImplementedError


class DeepSeekDanmakuGenerator(DanmakuGenerator):
    """DeepSeek adapter via the OpenAI-compatible Python client."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        from openai import OpenAI

        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.enabled = bool(api_key)
        self._client = OpenAI(api_key=api_key or "missing", base_url=base_url)

    def generate(self, screen_context: str, recent_bullets: list[str] | None = None) -> list[str]:
        if not self.enabled or not screen_context.strip():
            return []

        payload = self.build_request_payload(screen_context, recent_bullets)
        try:
            response = self._client.chat.completions.create(**payload)
            content = response.choices[0].message.content or ""
            return filter_recent_bullets(
                parse_danmaku_response(content),
                recent_bullets or [],
            )
        except Exception:
            logging.exception("DeepSeek API call failed")
            return []

    def build_request_payload(
        self,
        screen_context: str,
        recent_bullets: list[str] | None = None,
    ) -> dict[str, Any]:
        recent_bullets = recent_bullets or []
        prompt = PROMPT_TEMPLATE.format(
            screen_context=screen_context[:1600],
            recent_bullets=json.dumps(recent_bullets[-20:], ensure_ascii=False),
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 240,
        }

    def test_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "DEEPSEEK_API_KEY is empty"
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "只输出 ok。"},
                    {"role": "user", "content": "测试连接"},
                ],
                temperature=0,
                max_tokens=8,
            )
            content = (response.choices[0].message.content or "").strip()
            return True, content or "ok"
        except Exception as exc:
            logging.exception("DeepSeek API test failed")
            return False, str(exc)


def test_deepseek_connection_stdlib(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    if not api_key:
        return False, "DEEPSEEK_API_KEY is empty"

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "只输出 ok。"},
                {"role": "user", "content": "测试连接"},
            ],
            "temperature": 0,
            "max_tokens": 8,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"].get("content", "").strip()
        return True, content or "ok"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return False, str(exc)


def parse_danmaku_response(content: str) -> list[str]:
    parsed = _parse_jsonish(content)
    if isinstance(parsed, list):
        candidates = [str(item) for item in parsed]
    else:
        candidates = _split_lines(content)

    output: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = _clean_bullet(item)
        if not _is_valid_bullet(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        output.append(text)
        if len(output) >= 8:
            break
    return output


def filter_recent_bullets(bullets: list[str], recent_bullets: list[str]) -> list[str]:
    recent_keys = {_similarity_key(text) for text in recent_bullets}
    output: list[str] = []
    for bullet in bullets:
        key = _similarity_key(bullet)
        if key in recent_keys:
            continue
        if any(_too_similar(key, _similarity_key(item)) for item in recent_bullets):
            continue
        output.append(bullet)
    return output


def _parse_jsonish(content: str) -> Any:
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _split_lines(content: str) -> list[str]:
    lines = re.split(r"[\n\r]+", content)
    if len(lines) <= 1:
        lines = re.split(r"[，,;；]", content)
    return lines


def _clean_bullet(text: str) -> str:
    text = text.strip().strip("\"'`[]，。")
    text = re.sub(r"^\s*(?:[-*]|\d+[.。])\s*", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _is_valid_bullet(text: str) -> bool:
    if not (2 <= len(text) <= 28):
        return False
    if any(bad in text.lower() for bad in ("http://", "https://", "<script", "{", "}")):
        return False
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk_count >= 2


def _similarity_key(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text).lower()


def _too_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left in right or right in left:
        return min(len(left), len(right)) >= 5
    left_chars = set(left)
    right_chars = set(right)
    overlap = len(left_chars & right_chars) / max(len(left_chars | right_chars), 1)
    return overlap >= 0.82 and min(len(left), len(right)) >= 6
