"""自然语言智能体：用大模型函数调用完成分量表查询与出库扣减。"""

from __future__ import annotations

import json
import os
import urllib.request

from .service import AllocationService, InsufficientStockError
from .ocr.deepseek import DEFAULT_BASE, DEFAULT_MODEL


SYSTEM_PROMPT = (
    "你是新希望化工贸易的库存助手，帮助业务助理查询「分量表」并进行出库。"
    "品种代码：Y01油料、H01热料、C01碳酸、W01水料，'新'前缀表示新线产品。"
    "负数未下量表示超卖。规则：扣减前先调用 query_available 确认库存充足；"
    "扣减成功后要说明从哪些仓各扣了多少。用简洁中文回答。"
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_available",
            "description": "查询某品种在各仓的可售库存，可带需求数量得到能否满足与凑货方案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "variety": {
                        "type": "string",
                        "description": "品种代码或中文名，如 Y01 或 油料",
                    },
                    "qty": {"type": "number", "description": "需求数量（吨），可选"},
                    "warehouse": {"type": "string", "description": "仓库名，可选"},
                },
                "required": ["variety"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deduct_stock",
            "description": "出库扣减某品种指定数量的库存；扣减前应先查询确认充足。",
            "parameters": {
                "type": "object",
                "properties": {
                    "variety": {"type": "string", "description": "品种代码或中文名"},
                    "qty": {"type": "number", "description": "扣减数量（吨）"},
                    "warehouse": {
                        "type": "string",
                        "description": "仓库名，可选，留空则跨仓 FIFO",
                    },
                },
                "required": ["variety", "qty"],
            },
        },
    },
]


class AllocationAgent:
    """调用大模型（OpenAI 兼容函数调用）完成查询/扣减的智能体。"""

    def __init__(self, service: AllocationService):
        self.service = service
        self.api_base = os.environ.get("DEEPSEEK_API_BASE", DEFAULT_BASE).rstrip("/")
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise RuntimeError("智能体需要 DEEPSEEK_API_KEY 环境变量")

    def run(self, user_message: str, max_steps: int = 5) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        transcript = []

        for _ in range(max_steps):
            body = self._chat(
                {
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOLS,
                    "temperature": 0,
                }
            )
            message = body["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                return {
                    "answer": message.get("content") or "",
                    "tool_calls": transcript,
                }

            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
            messages.append(assistant_msg)

            for call in tool_calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                result = self._exec(name, args)
                transcript.append({"tool": name, "args": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return {"answer": "已达到最大调用步数，未得到最终结论。", "tool_calls": transcript}

    def _chat(self, payload) -> dict:
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _exec(self, name: str, args: dict):
        try:
            if name == "query_available":
                return self.service.query(
                    args.get("variety"),
                    warehouse=args.get("warehouse"),
                    min_qty=args.get("qty"),
                )
            if name == "deduct_stock":
                return self.service.deduct(
                    args.get("variety"),
                    args.get("qty"),
                    warehouse=args.get("warehouse"),
                )
            return {"error": f"未知工具：{name}"}
        except InsufficientStockError as e:
            return {"error": str(e), "available": e.available}
        except Exception as e:
            return {"error": str(e)}
