from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


SYSTEM_PROMPT = "Return only a valid JSON array. Do not include markdown or explanations."

LANGUAGE_PROFILES = {
    "zh": {
        "name": "Chinese",
        "length_rule": "Each item should be 6 to 18 Chinese characters.",
        "examples": [
            "\u8fd9\u6ce2\u6709\u70b9\u62bd\u8c61",
            "\u4e3b\u64ad\u5728\u5e72\u561b\u54c8\u54c8",
            "\u6211\u597d\u50cf\u770b\u61c2\u4e86",
            "\u8fd9\u56fe\u6709\u70b9\u5173\u952e",
            "\u7b49\u4e0b\u8fd9\u4e0d\u5bf9\u5427",
        ],
    },
    "en": {
        "name": "English",
        "length_rule": "Each item should be short, roughly 3 to 8 words.",
        "examples": [
            "wait this is wild",
            "that timing is perfect",
            "I see what happened",
            "this part matters",
            "hold on that is off",
        ],
    },
}

PROMPT_TEMPLATE = """You are simulating live-stream audience bullet comments.
Generate 5 natural {language_name} danmaku comments based on the current screen text.

Rules:
* {length_rule}
* Sound like real viewers, not an assistant.
* Reactions can be amused, surprised, curious, playful, or lightly teasing.
* Do not attack people maliciously.
* Do not include sexual content.
* Do not include political extremism.
* Do not number the items.
* Do not repeat recent comments.
* Return only a JSON array of strings.

Recent comments:
{recent_bullets}

Current screen text:
{screen_context}

Expected style:
{examples}
"""


class DanmakuGenerator(ABC):
    @abstractmethod
    def generate(self, screen_context: str, recent_bullets: list[str] | None = None) -> list[str]:
        raise NotImplementedError


class DeepSeekDanmakuGenerator(DanmakuGenerator):
    """DeepSeek adapter via the OpenAI-compatible Python client."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_sec: float = 20.0,
        output_language: str = "zh",
    ) -> None:
        from openai import OpenAI

        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.output_language = normalize_output_language(output_language)
        self.enabled = bool(api_key)
        self._client = OpenAI(
            api_key=api_key or "missing",
            base_url=base_url,
            timeout=timeout_sec,
        )

    def generate(self, screen_context: str, recent_bullets: list[str] | None = None) -> list[str]:
        if not self.enabled or not screen_context.strip():
            return []

        payload = self.build_request_payload(screen_context, recent_bullets)
        try:
            response = self._client.chat.completions.create(**payload)
            content = response.choices[0].message.content or ""
            return filter_recent_bullets(
                parse_danmaku_response(content, self.output_language),
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
        profile = LANGUAGE_PROFILES[self.output_language]
        prompt = PROMPT_TEMPLATE.format(
            language_name=profile["name"],
            length_rule=profile["length_rule"],
            screen_context=screen_context[:1600],
            recent_bullets=json.dumps(recent_bullets[-20:], ensure_ascii=False),
            examples=json.dumps(profile["examples"], ensure_ascii=False),
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 240,
            "timeout": self.timeout_sec,
        }

    def test_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "DEEPSEEK_API_KEY is empty"
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Return only ok."},
                    {"role": "user", "content": "Test the connection."},
                ],
                temperature=0,
                max_tokens=8,
            )
            content = (response.choices[0].message.content or "").strip()
            return True, content or "ok"
        except Exception as exc:
            logging.exception("DeepSeek API test failed")
            return False, str(exc)


def normalize_output_language(value: str) -> str:
    normalized = (value or "zh").strip().lower()
    if normalized in {"zh", "cn", "chinese", "zh-cn", "zh_cn"}:
        return "zh"
    if normalized in {"en", "english", "en-us", "en_us"}:
        return "en"
    logging.warning("Unknown DANMAKU_OUTPUT_LANGUAGE=%r; falling back to zh", value)
    return "zh"


def test_deepseek_connection_stdlib(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    if not api_key:
        return False, "DEEPSEEK_API_KEY is empty"

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only ok."},
                {"role": "user", "content": "Test the connection."},
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


def parse_danmaku_response(content: str, output_language: str = "zh") -> list[str]:
    parsed = _parse_jsonish(content)
    if isinstance(parsed, list):
        candidates = [str(item) for item in parsed]
    else:
        candidates = _split_lines(content)

    output: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = _clean_bullet(item)
        if not _is_valid_bullet(text, output_language):
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
    return re.split(r"[\n\r;；]+", content)


def _clean_bullet(text: str) -> str:
    text = text.strip().strip("\"'`[]，。,.!?！？")
    text = re.sub(r"^\s*(?:[-*]|\d+[.、)]?)\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_valid_bullet(text: str, output_language: str = "zh") -> bool:
    if not (2 <= len(text) <= 60):
        return False
    if any(bad in text.lower() for bad in ("http://", "https://", "<script", "{", "}")):
        return False
    if normalize_output_language(output_language) == "zh":
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        return cjk_count >= 2 and len(text) <= 28
    word_count = len(re.findall(r"[A-Za-z0-9]+", text))
    return 2 <= word_count <= 12


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
