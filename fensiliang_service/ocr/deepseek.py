"""DeepSeek 文本结构化：把 OCR 得到的原始文字整理成结构化分量表。

DeepSeek 是纯文本模型，不能直接识别图片。这里提供两种用法：
1. ``DeepSeekStructurer`` —— 输入 OCR 得到的原始文本，输出结构化记录。
2. ``DeepSeekPipeline`` —— 先本地 PaddleOCR 认字，再交给 DeepSeek 结构化。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import List

from .base import OcrParser
from ..models import AllocationRecord, variety_name_for


DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _extract_json_array(content: str):
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].lstrip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and "records" in data:
        return data["records"]
    if isinstance(data, list):
        return data
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"无法从模型回复中解析 JSON：{content[:200]}")


class DeepSeekStructurer:
    """把 OCR 原始文本交给 DeepSeek 整理成结构化记录。"""

    def __init__(self):
        self.api_base = os.environ.get("DEEPSEEK_API_BASE", DEFAULT_BASE).rstrip("/")
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY 环境变量")

    def structure(self, raw_text: str) -> List[AllocationRecord]:
        prompt = (
            "你是大宗商品分量表解析助手。下面是图片 OCR 得到的原始文字，"
            "可能顺序乱、有错别字、多行粘连。请把它整理成一个 JSON 对象，"
            "格式为 {\"records\": [...]}，其中 records 是数组，"
            "每个元素是一个对象，字段为：\n"
            "- warehouse: 库位（东莞/黄埔/新会/湛江等仓库名）\n"
            "- variety_code: 品种代码（Y01/H01/C01/W01，或带\"新\"前缀如 新W01）\n"
            "- customer: 客户名称（多家用/分隔）\n"
            "- unsold_qty: 未下量（吨，数字；负数表示超卖，保留负号）\n"
            "规则：Y01=油料、H01=热料、C01=碳酸、W01=水料；\"新\"前缀表示新线产品必须保留；"
            "未下量为负数表示超卖，数字要带负号。\n"
            "只输出 JSON 对象本身，不要输出解释，不要用 markdown 代码块。\n\n"
            f"原始 OCR 文本：\n{raw_text}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        data = _extract_json_array(content)
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


class DeepSeekPipeline(OcrParser):
    """图片 → PaddleOCR 认字 → DeepSeek 结构化。"""

    def parse(self, path: str) -> List[AllocationRecord]:
        raw_text = self._ocr_text(path)
        if not raw_text.strip():
            return []
        return DeepSeekStructurer().structure(raw_text)

    @staticmethod
    def _ocr_text(path: str) -> str:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise RuntimeError(
                "DeepSeek 管线需要先本地 OCR，请安装：pip install paddleocr paddlepaddle"
            ) from e
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(path, cls=True)
        if not result or not result[0]:
            return ""
        return "\n".join(line[1][0] for line in result[0])
