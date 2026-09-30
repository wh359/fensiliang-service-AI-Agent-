"""OCR 解析器抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import AllocationRecord


class OcrParser(ABC):
    @abstractmethod
    def parse(self, path: str) -> List[AllocationRecord]:
        """把图片或结构化文件解析为分量表记录列表。"""
        raise NotImplementedError
