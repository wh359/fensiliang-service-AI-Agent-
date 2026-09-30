"""EasyOCR 离线识别适配器。"""

from __future__ import annotations

from typing import List

from .base import OcrParser
from ..models import AllocationRecord, variety_name_for


class EasyOcrParser(OcrParser):
    """使用 EasyOCR 离线识别中文表格，需先安装 easyocr。"""

    def parse(self, path: str) -> List[AllocationRecord]:
        try:
            import easyocr
        except ImportError as e:
            raise RuntimeError(
                "需要安装 easyocr：python -m pip install easyocr"
            ) from e

        reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        results = reader.readtext(path)
        if not results:
            return []

        boxes = []
        for bbox, text, _confidence in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            boxes.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, text))

        boxes.sort(key=lambda b: (b[1], b[0]))
        rows = []
        row_threshold = 20
        for cx, cy, text in boxes:
            if not rows or abs(cy - rows[-1][0][1]) > row_threshold:
                rows.append([(cx, cy, text)])
            else:
                rows[-1].append((cx, cy, text))

        records = []
        for row in rows:
            cells = sorted(row, key=lambda b: b[0])
            if len(cells) < 4:
                continue
            warehouse, variety, customer, qty = (
                cells[0][2],
                cells[1][2],
                cells[2][2],
                cells[3][2],
            )
            code = variety.strip()
            number = self._to_float(qty)
            if number is None or code in ("品种", "代码"):
                continue
            records.append(
                AllocationRecord(
                    warehouse=warehouse.strip(),
                    variety_code=code,
                    variety_name=variety_name_for(code),
                    customer=customer.strip(),
                    unsold_qty=number,
                )
            )
        return records

    @staticmethod
    def _to_float(text: str):
        try:
            return float(str(text).replace(",", "").replace("，", ""))
        except (ValueError, TypeError):
            return None
