"""分量表核心服务：查询与出库扣减。"""

from __future__ import annotations

from typing import List, Optional

from .models import AllocationRecord, normalize_variety
from .storage import JsonStorage


class InsufficientStockError(Exception):
    def __init__(self, available: float, requested: float):
        self.available = available
        self.requested = requested
        super().__init__(f"库存不足：可售 {available:g} 吨，需求 {requested:g} 吨")


class AllocationService:
    def __init__(self, storage: JsonStorage):
        self.storage = storage
        self.records: List[AllocationRecord] = []

    def load(self) -> None:
        self.records = self.storage.load()

    def save(self) -> None:
        self.storage.save(self.records)

    def list_all(self) -> List[AllocationRecord]:
        return list(self.records)

    def replace_records(self, records: List[AllocationRecord]) -> None:
        self.records = list(records)
        self.save()

    def query(
        self,
        variety: str,
        warehouse: Optional[str] = None,
        customer: Optional[str] = None,
        min_qty: Optional[float] = None,
    ) -> dict:
        """按品种（代码或名称）查询分量表并汇总可售量。"""
        code = normalize_variety(variety)

        matched = []
        total_available = 0.0
        oversold_count = 0
        for record in self.records:
            if code and record.variety_code != code:
                continue
            if warehouse and record.warehouse != warehouse:
                continue
            if customer and customer not in record.customer:
                continue
            matched.append(record)
            total_available += record.available
            if record.oversold:
                oversold_count += 1

        fulfillable = None
        plan = []
        if min_qty is not None:
            fulfillable = total_available >= min_qty
            plan = self._fulfillment_plan(code, min_qty, warehouse)

        return {
            "variety_code": code,
            "records": [r.to_view_dict() for r in matched],
            "total_available": total_available,
            "oversold_count": oversold_count,
            "fulfillable": fulfillable,
            "fulfillment_plan": plan,
        }

    def deduct(
        self,
        variety: str,
        qty: float,
        warehouse: Optional[str] = None,
    ) -> dict:
        """出库扣减：按可售量 FIFO 贪心扣减，跨仓拆分。"""
        if qty <= 0:
            raise ValueError("扣减数量必须大于 0")
        code = normalize_variety(variety)
        if not code:
            raise ValueError("未识别的品种")

        candidates = self._available_lots(code, warehouse)
        total = sum(record.available for _, record in candidates)
        if total < qty:
            raise InsufficientStockError(total, qty)

        remaining = qty
        deductions = []
        for _idx, record in candidates:
            if remaining <= 0:
                break
            take = min(record.available, remaining)
            record.unsold_qty -= take
            deductions.append(
                {
                    "warehouse": record.warehouse,
                    "customer": record.customer,
                    "deducted": take,
                    "remaining_after": record.unsold_qty,
                }
            )
            remaining -= take

        self.save()
        remaining_total = sum(
            record.available for record in self.records if record.variety_code == code
        )
        return {
            "variety_code": code,
            "requested": qty,
            "deductions": deductions,
            "remaining_total_available": remaining_total,
        }

    def _available_lots(self, code: str, warehouse: Optional[str]):
        candidates = []
        for idx, record in enumerate(self.records):
            if record.variety_code != code:
                continue
            if warehouse and record.warehouse != warehouse:
                continue
            if record.available <= 0:
                continue
            candidates.append((idx, record))
        candidates.sort(key=lambda item: (item[1].warehouse, item[0]))
        return candidates

    def _fulfillment_plan(self, code: str, qty: float, warehouse: Optional[str]):
        plan = []
        remaining = qty
        for _idx, record in self._available_lots(code, warehouse):
            if remaining <= 0:
                break
            take = min(record.available, remaining)
            plan.append(
                {
                    "warehouse": record.warehouse,
                    "customer": record.customer,
                    "take": take,
                }
            )
            remaining -= take
        return plan
