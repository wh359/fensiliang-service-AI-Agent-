"""云端视觉大模型 OCR（OpenAI 兼容接口）。"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import List

from .base import OcrParser
from ..models import AllocationRecord, variety_name_for


class CloudVisionParser(OcrParser):
    """调用 OpenAI 兼容的视觉模型（如通义千问 qwen-vl、OpenAI gpt-4o）识别表格。

    通过环境变量配置：``OCR_API_BASE``、``OCR_API_KEY``、``OCR_MODEL``。
    """

    def parse(self, path: str) -> List[AllocationRecord]:
        api_base = os.environ.get(
            "OCR_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        api_key = os.environ.get("OCR_API_KEY", "")
        model = os.environ.get("OCR_MODEL", "qwen-vl-max")
        if not api_key:
            raise RuntimeError("缺少 OCR_API_KEY 环境变量")

        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"

        prompt = (
            "你是大宗商品分量表解析器。请识别图片中的表格，每一行输出一个 JSON 对象，"
            "字段为：warehouse(库位)、variety_code(品种代码，如Y01或新W01)、"
            "customer(客户，多家用/分隔)、unsold_qty(未下量，吨，数字，负数表示超卖)。"
            "只输出 JSON 数组，不要输出任何解释。"
        )
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        content = body["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        return self._to_records(data)

    def _to_records(self, data) -> List[AllocationRecord]:
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
