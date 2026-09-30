"""离线默认解析器：从 JSON 文件读取结构化分量表。"""

from __future__ import annotations

import json
from typing import List

from .base import OcrParser
from ..models import AllocationRecord, variety_name_for


class JsonParser(OcrParser):
    def parse(self, path: str) -> List[AllocationRecord]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = []
        for item in data:
            code = str(item["variety_code"]).strip()
            records.append(
                AllocationRecord(
                    warehouse=str(item["warehouse"]).strip(),
                    variety_code=code,
                    variety_name=item.get("variety_name") or variety_name_for(code),
                    customer=str(item.get("customer", "")).strip(),
                    unsold_qty=float(item["unsold_qty"]),
                )
            )
        return records
