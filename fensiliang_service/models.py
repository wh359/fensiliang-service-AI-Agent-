"""数据模型与品种代码规则。"""

from __future__ import annotations

from dataclasses import dataclass


VARIETY_CODES = {
    "Y01": "油料",
    "H01": "热料",
    "C01": "碳酸",
    "W01": "水料",
}

_NAME_TO_CODE = {name: code for code, name in VARIETY_CODES.items()}


def normalize_variety(variety: str) -> str:
    """把用户输入规范化为标准品种代码，支持代码、中文名和“新”前缀。"""
    if variety is None:
        return ""
    value = variety.strip()
    if not value:
        return ""

    new_prefix = value.startswith("新")
    base = value[1:] if new_prefix else value

    upper = base.upper()
    if upper in VARIETY_CODES:
        code = upper
    elif base in _NAME_TO_CODE:
        code = _NAME_TO_CODE[base]
    else:
        code = base

    return ("新" + code) if new_prefix else code


def variety_name_for(code: str) -> str:
    """根据品种代码返回显示名称，处理“新”前缀。"""
    new_prefix = code.startswith("新")
    base = code[1:] if new_prefix else code
    name = VARIETY_CODES.get(base, base)
    return ("新线" + name) if new_prefix else name


@dataclass
class AllocationRecord:
    """分量表中的一行：库位 + 品种 + 客户 + 未下量（吨）。"""

    warehouse: str
    variety_code: str
    variety_name: str
    customer: str
    unsold_qty: float

    @property
    def available(self) -> float:
        return max(self.unsold_qty, 0.0)

    @property
    def oversold(self) -> bool:
        return self.unsold_qty < 0

    def to_dict(self) -> dict:
        return {
            "warehouse": self.warehouse,
            "variety_code": self.variety_code,
            "variety_name": self.variety_name,
            "customer": self.customer,
            "unsold_qty": self.unsold_qty,
        }

    def to_view_dict(self) -> dict:
        data = self.to_dict()
        data["available"] = self.available
        data["oversold"] = self.oversold
        return data
