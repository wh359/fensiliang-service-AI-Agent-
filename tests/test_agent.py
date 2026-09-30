import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fensiliang_service.agent import AllocationAgent
from fensiliang_service.models import AllocationRecord, variety_name_for
from fensiliang_service.service import AllocationService
from fensiliang_service.storage import JsonStorage


def rec(warehouse, code, customer, qty):
    return AllocationRecord(warehouse, code, variety_name_for(code), customer, qty)


class TestAgent(unittest.TestCase):
    def setUp(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.service = AllocationService(JsonStorage(self.path))
        self.service.replace_records([rec("东莞", "Y01", "甲", 100)])

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _fake_chat(self, agent, payload):
        tool_count = sum(1 for m in payload["messages"] if m.get("role") == "tool")
        if tool_count == 0:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {
                                        "name": "query_available",
                                        "arguments": json.dumps(
                                            {"variety": "Y01", "qty": 33}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        if tool_count == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c2",
                                    "type": "function",
                                    "function": {
                                        "name": "deduct_stock",
                                        "arguments": json.dumps(
                                            {"variety": "Y01", "qty": 33}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "已从东莞扣减33吨油料。",
                        "tool_calls": [],
                    }
                }
            ]
        }

    def test_agent_query_then_deduct(self):
        agent = AllocationAgent(self.service)
        agent._chat = lambda payload: self._fake_chat(agent, payload)
        result = agent.run("我要33吨油料")

        self.assertEqual(result["answer"], "已从东莞扣减33吨油料。")
        self.assertEqual(len(result["tool_calls"]), 2)
        self.assertEqual(
            [c["tool"] for c in result["tool_calls"]],
            ["query_available", "deduct_stock"],
        )
        self.assertEqual(self.service.list_all()[0].unsold_qty, 67)


if __name__ == "__main__":
    unittest.main()
