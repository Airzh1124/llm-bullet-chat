from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterable

import numpy as np


class OcrEngine(ABC):
    @abstractmethod
    def extract_text(self, image_bgr: np.ndarray) -> list[str]:
        raise NotImplementedError


class RapidOcrEngine(OcrEngine):
    """RapidOCR adapter using its documented Python callable API."""

    def __init__(self) -> None:
        try:
            from rapidocr import RapidOCR
        except ImportError:
            from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def extract_text(self, image_bgr: np.ndarray) -> list[str]:
        output = self._engine(image_bgr)

        # RapidOCR 3.x returns RapidOCROutput(txts=..., scores=...); older
        # rapidocr_onnxruntime examples returned (result, elapse). Support both.
        if hasattr(output, "txts"):
            txts = getattr(output, "txts", None)
            if txts:
                return [str(text) for text in txts if text]

            word_results = getattr(output, "word_results", None)
            if word_results:
                return [str(item[0]) for item in word_results if item and item[0]]
            return []

        if isinstance(output, tuple):
            result = output[0]
        else:
            result = output

        if not result:
            return []

        lines: list[str] = []
        for item in result:
            if len(item) >= 2 and item[1]:
                lines.append(str(item[1]))
        return lines


class PaddleOcrEngine(OcrEngine):
    def __init__(self) -> None:
        from paddleocr import PaddleOCR

        self._engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def extract_text(self, image_bgr: np.ndarray) -> list[str]:
        result = self._engine.ocr(image_bgr, cls=True)
        lines: list[str] = []
        for page in result or []:
            for item in page or []:
                if len(item) >= 2 and item[1]:
                    lines.append(str(item[1][0]))
        return lines


class EasyOcrEngine(OcrEngine):
    def __init__(self) -> None:
        import easyocr

        self._engine = easyocr.Reader(["ch_sim", "en"], gpu=False)

    def extract_text(self, image_bgr: np.ndarray) -> list[str]:
        return [str(row[1]) for row in self._engine.readtext(image_bgr) if len(row) >= 2]


class ScreenUnderstanding:
    def __init__(self, engine_name: str = "rapidocr", max_context_chars: int = 1200) -> None:
        self.engine_name = engine_name
        self.max_context_chars = max_context_chars
        self.engine = self._create_engine(engine_name)

    def understand(self, image_bgr: np.ndarray) -> str:
        lines = self.engine.extract_text(image_bgr)
        cleaned = self._clean_lines(lines)
        return "\n".join(cleaned)[: self.max_context_chars]

    @staticmethod
    def _create_engine(engine_name: str) -> OcrEngine:
        if engine_name == "rapidocr":
            return RapidOcrEngine()
        if engine_name == "paddleocr":
            return PaddleOcrEngine()
        if engine_name == "easyocr":
            return EasyOcrEngine()
        raise ValueError(f"Unsupported OCR engine: {engine_name}")

    @staticmethod
    def _clean_lines(lines: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for line in lines:
            cleaned = _normalize_text(line)
            if not _looks_useful(cleaned):
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(cleaned)
        return output


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[^\w\u4e00-\u9fff，。！？、：；（）《》【】“”\"'.,!?%:/+\-#@ ]", "", text)
    return text.strip()


def _looks_useful(text: str) -> bool:
    if len(text) < 2:
        return False
    if len(text) > 120:
        return False
    alnum_or_cjk = re.findall(r"[\w\u4e00-\u9fff]", text)
    return len(alnum_or_cjk) / max(len(text), 1) >= 0.45
