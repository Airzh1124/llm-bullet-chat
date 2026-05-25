from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrivacyFinding:
    label: str
    count: int


@dataclass(frozen=True)
class PrivacyFilterResult:
    sanitized_text: str
    findings: list[PrivacyFinding]

    @property
    def changed(self) -> bool:
        return bool(self.findings)

    def summary(self) -> str:
        if not self.findings:
            return "no PII-like text detected"
        return ", ".join(f"{item.label}={item.count}" for item in self.findings)


class PrivacyFilter(ABC):
    @abstractmethod
    def sanitize(self, text: str) -> PrivacyFilterResult:
        raise NotImplementedError


class RegexPrivacyFilter(PrivacyFilter):
    """Local conservative PII redaction.

    This is intentionally simple and fully offline. It is not a replacement for
    OpenAI Privacy Filter, but it catches common OCR-visible secrets before the
    text is sent to a remote LLM.
    """

    PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("secret", re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd|pwd)\s*[:=]\s*[^\s,;，；]{6,}")),
        ("secret", re.compile(r"\b(?:sk|rk|pk|ak)-[A-Za-z0-9_\-]{16,}\b")),
        ("secret", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}\b", re.IGNORECASE)),
        ("private_email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
        ("cn_id_card", re.compile(r"(?<![0-9A-Za-z])\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])")),
        ("private_phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
        ("private_phone", re.compile(r"(?<!\d)(?:\+?\d{1,3}[- ]?)?(?:\(?\d{2,4}\)?[- ]?)?\d{3,4}[- ]?\d{4}(?!\d)")),
        ("account_number", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
        ("private_url", re.compile(r"https?://[^\s，。；;]+", re.IGNORECASE)),
    )

    def sanitize(self, text: str) -> PrivacyFilterResult:
        sanitized = text
        counts: dict[str, int] = {}
        for label, pattern in self.PATTERNS:
            sanitized, count = pattern.subn(f"[REDACTED:{label}]", sanitized)
            if count:
                counts[label] = counts.get(label, 0) + count
        findings = [PrivacyFinding(label=label, count=count) for label, count in sorted(counts.items())]
        return PrivacyFilterResult(sanitized_text=sanitized, findings=findings)


class OpenAIPrivacyFilter(PrivacyFilter):
    """Adapter for OpenAI Privacy Filter (`openai/privacy-filter`).

    The upstream project exposes an OPF Python API and a local CLI. The exact API
    can evolve, so this adapter is deliberately defensive and falls back to the
    regex filter if OPF is unavailable or returns an unexpected shape.
    """

    def __init__(
        self,
        device: str = "cpu",
        checkpoint: str | None = None,
        fallback: PrivacyFilter | None = None,
    ) -> None:
        self.device = device
        self.checkpoint = checkpoint or None
        self.fallback = fallback or RegexPrivacyFilter()
        self._opf = self._load_opf()

    def sanitize(self, text: str) -> PrivacyFilterResult:
        if self._opf is None:
            return self.fallback.sanitize(text)
        try:
            raw = self._opf.redact(text)
            redacted_text = _extract_redacted_text(raw)
            findings = _extract_findings(raw, text, redacted_text)
            return PrivacyFilterResult(sanitized_text=redacted_text, findings=findings)
        except Exception:
            logging.exception("OpenAI Privacy Filter failed; falling back to regex redaction")
            return self.fallback.sanitize(text)

    def _load_opf(self) -> Any:
        try:
            from opf import OPF
        except Exception:
            logging.warning("OpenAI Privacy Filter package is not installed; using regex privacy filter")
            return None

        kwargs: dict[str, Any] = {"device": self.device}
        if self.checkpoint:
            kwargs["checkpoint"] = self.checkpoint
        try:
            return OPF(**kwargs)
        except TypeError:
            return OPF()
        except Exception:
            logging.exception("Failed to initialize OpenAI Privacy Filter; using regex privacy filter")
            return None


def create_privacy_filter(
    engine: str,
    device: str = "cpu",
    checkpoint: str | None = None,
) -> PrivacyFilter:
    if engine == "none":
        return NullPrivacyFilter()
    if engine == "openai":
        return OpenAIPrivacyFilter(device=device, checkpoint=checkpoint)
    if engine == "regex":
        return RegexPrivacyFilter()
    raise ValueError(f"Unsupported privacy filter engine: {engine}")


class NullPrivacyFilter(PrivacyFilter):
    def sanitize(self, text: str) -> PrivacyFilterResult:
        return PrivacyFilterResult(sanitized_text=text, findings=[])


def _extract_redacted_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("redacted_text", "redacted", "masked_text", "output_text", "text"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    for attr in ("redacted_text", "redacted", "masked_text", "output_text", "text"):
        value = getattr(raw, attr, None)
        if isinstance(value, str):
            return value
    raise ValueError(f"Cannot extract redacted text from OPF result: {type(raw)!r}")


def _extract_findings(raw: Any, original: str, redacted: str) -> list[PrivacyFinding]:
    counts: dict[str, int] = {}
    spans = None
    if isinstance(raw, dict):
        spans = raw.get("spans") or raw.get("redactions") or raw.get("entities")
    else:
        spans = getattr(raw, "spans", None) or getattr(raw, "redactions", None) or getattr(raw, "entities", None)

    if isinstance(spans, list):
        for span in spans:
            label = _span_label(span)
            counts[label] = counts.get(label, 0) + 1
    elif original != redacted:
        counts["pii"] = 1

    return [PrivacyFinding(label=label, count=count) for label, count in sorted(counts.items())]


def _span_label(span: Any) -> str:
    if isinstance(span, dict):
        for key in ("label", "type", "category", "entity"):
            value = span.get(key)
            if value:
                return str(value)
    for attr in ("label", "type", "category", "entity"):
        value = getattr(span, attr, None)
        if value:
            return str(value)
    return "pii"
