"""JSON 文件持久化（原子写）。"""

from __future__ import annotations

import json
import os
import tempfile
from typing import List

from .models import AllocationRecord, variety_name_for


class JsonStorage:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> List[AllocationRecord]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = []
        for item in data:
            item = dict(item)
            item.setdefault("variety_name", variety_name_for(item["variety_code"]))
            records.append(AllocationRecord(**item))
        return records

    def save(self, records: List[AllocationRecord]) -> None:
        payload = [record.to_dict() for record in records]
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".alloc_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
