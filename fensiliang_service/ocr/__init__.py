"""可插拔 OCR 解析器。"""

from .base import OcrParser
from .json_parser import JsonParser
from .cloud_vision import CloudVisionParser
from .paddle_ocr import PaddleOcrParser
from .easyocr import EasyOcrParser
from .deepseek import DeepSeekStructurer, DeepSeekPipeline

__all__ = [
    "OcrParser",
    "JsonParser",
    "CloudVisionParser",
    "PaddleOcrParser",
    "EasyOcrParser",
    "DeepSeekStructurer",
    "DeepSeekPipeline",
]


def get_parser(kind: str = "json") -> OcrParser:
    kind = (kind or "json").lower()
    if kind == "json":
        return JsonParser()
    if kind in ("cloud", "vision", "cloud_vision"):
        return CloudVisionParser()
    if kind in ("paddle", "paddleocr"):
        return PaddleOcrParser()
    if kind in ("easyocr", "easy_ocr"):
        return EasyOcrParser()
    if kind in ("deepseek", "deepseek_pipeline"):
        return DeepSeekPipeline()
    raise ValueError(f"未知的 OCR 解析器: {kind}")
