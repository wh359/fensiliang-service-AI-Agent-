import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fensiliang_service.models import (
    AllocationRecord,
    VARIETY_CODES,
    normalize_variety,
    variety_name_for,
)
from fensiliang_service.service import AllocationService, InsufficientStockError
from fensiliang_service.storage import JsonStorage


def rec(warehouse, code, customer, qty):
    return AllocationRecord(warehouse, code, variety_name_for(code), customer, qty)


class TestModels(unittest.TestCase):
    def test_variety_mapping(self):
        self.assertEqual(VARIETY_CODES["Y01"], "油料")
        self.assertEqual(variety_name_for("新W01"), "新线水料")

    def test_normalize_variety(self):
        self.assertEqual(normalize_variety("油料"), "Y01")
        self.assertEqual(normalize_variety("y01"), "Y01")
        self.assertEqual(normalize_variety("新W01"), "新W01")
        self.assertEqual(normalize_variety("新油料"), "新Y01")


class TestService(unittest.TestCase):
    def _svc(self, records):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        service = AllocationService(JsonStorage(path))
        service.replace_records(records)
        return service

    def test_query_by_variety(self):
        service = self._svc(
            [
                rec("东莞", "Y01", "甲", 30),
                rec("黄埔", "Y01", "乙", 20),
                rec("东莞", "H01", "丙", 10),
            ]
        )
        result = service.query("油料")
        self.assertEqual(result["total_available"], 50)
        self.assertEqual(len(result["records"]), 2)

    def test_query_filter_warehouse_customer(self):
        service = self._svc(
            [rec("东莞", "Y01", "甲", 30), rec("黄埔", "Y01", "乙", 20)]
        )
        self.assertEqual(service.query("Y01", warehouse="东莞")["total_available"], 30)
        self.assertEqual(service.query("Y01", customer="乙")["total_available"], 20)

    def test_query_min_qty(self):
        service = self._svc(
            [rec("东莞", "Y01", "甲", 30), rec("黄埔", "Y01", "乙", 20)]
        )
        result = service.query("Y01", min_qty=40)
        self.assertTrue(result["fulfillable"])
        self.assertEqual(result["fulfillment_plan"][0]["take"], 30)
        self.assertFalse(service.query("Y01", min_qty=60)["fulfillable"])

    def test_oversold_excluded_from_available(self):
        service = self._svc(
            [rec("东莞", "Y01", "甲", 30), rec("黄埔", "Y01", "乙", -5)]
        )
        result = service.query("Y01")
        self.assertEqual(result["total_available"], 30)
        self.assertEqual(result["oversold_count"], 1)

    def test_deduct_fifo_across_warehouses(self):
        service = self._svc(
            [rec("东莞", "Y01", "甲", 30), rec("黄埔", "Y01", "乙", 20)]
        )
        result = service.deduct("Y01", 40)
        self.assertEqual(result["requested"], 40)
        by_warehouse = {r.warehouse: r.unsold_qty for r in service.list_all()}
        self.assertEqual(by_warehouse["东莞"], 0)
        self.assertEqual(by_warehouse["黄埔"], 10)

    def test_deduct_insufficient_no_mutation(self):
        service = self._svc([rec("东莞", "Y01", "甲", 30)])
        before = [r.to_dict() for r in service.list_all()]
        with self.assertRaises(InsufficientStockError):
            service.deduct("Y01", 50)
        after = [r.to_dict() for r in service.list_all()]
        self.assertEqual(before, after)

    def test_deduct_persists(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        service = AllocationService(JsonStorage(path))
        service.replace_records([rec("东莞", "Y01", "甲", 30)])
        service.deduct("Y01", 10)

        reloaded = AllocationService(JsonStorage(path))
        reloaded.load()
        self.assertEqual(reloaded.list_all()[0].unsold_qty, 20)

    def test_replace_records(self):
        service = self._svc([])
        service.replace_records([rec("东莞", "Y01", "甲", 30)])
        self.assertEqual(len(service.list_all()), 1)


if __name__ == "__main__":
    unittest.main()
