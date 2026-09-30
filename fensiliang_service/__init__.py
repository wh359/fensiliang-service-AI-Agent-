"""分量表服务：PET 大宗商品分量表的 OCR、查询与出库扣减原型。"""

__version__ = "0.1.0"

from .models import AllocationRecord, VARIETY_CODES, normalize_variety, variety_name_for
from .service import AllocationService, InsufficientStockError
from .storage import JsonStorage

__all__ = [
    "AllocationRecord",
    "VARIETY_CODES",
    "normalize_variety",
    "variety_name_for",
    "AllocationService",
    "InsufficientStockError",
    "JsonStorage",
]
