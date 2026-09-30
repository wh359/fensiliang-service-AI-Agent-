"""标准库实现的完整 REST API（含 CORS），供前端直接调用。"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .service import AllocationService, InsufficientStockError
from .storage import JsonStorage
from .ocr import get_parser, DeepSeekStructurer


STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
)

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def serve(data_path: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    service = AllocationService(JsonStorage(data_path))
    service.load()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _ok(self, data) -> None:
            self._send_json(200, {"ok": True, "data": data})

        def _err(self, status: int, code: str, message: str, extra=None) -> None:
            payload = {"ok": False, "error": message, "code": code}
            if extra:
                payload.update(extra)
            self._send_json(status, payload)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return None

        def _serve_static(self, path: str) -> None:
            if path in ("/", "/index.html"):
                path = "/index.html"
            rel = path.lstrip("/")
            root = os.path.normpath(STATIC_DIR)
            full = os.path.normpath(os.path.join(root, rel))
            if not full.startswith(root + os.sep) and full != root:
                return self._err(404, "not_found", "文件不存在")
            if not os.path.isfile(full):
                return self._err(404, "not_found", "文件不存在")
            ext = os.path.splitext(full)[1].lower()
            data = open(full, "rb").read()
            self.send_response(200)
            self.send_header(
                "Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream")
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors_headers()
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            if path.startswith("/api/"):
                try:
                    self._handle_api_get(path, qs)
                except Exception as e:
                    self._err(500, "internal", str(e))
            else:
                self._serve_static(path)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not path.startswith("/api/"):
                return self._err(404, "not_found", "接口不存在")
            data = self._read_body()
            if data is None:
                return self._err(400, "invalid_json", "请求体不是合法 JSON")
            try:
                self._handle_api_post(path, data)
            except InsufficientStockError as e:
                self._err(409, "insufficient", str(e), {"available": e.available})
            except ValueError as e:
                self._err(400, "bad_request", str(e))
            except RuntimeError as e:
                self._err(400, "agent_config", str(e))
            except Exception as e:
                self._err(500, "internal", str(e))

        def _handle_api_get(self, path: str, qs) -> None:
            if path == "/api/health":
                return self._ok({"status": "ok"})
            if path == "/api/records":
                records = [r.to_view_dict() for r in service.list_all()]
                return self._ok({"records": records, "total": len(records)})
            if path == "/api/varieties":
                return self._ok(self._varieties_summary())
            if path == "/api/warehouses":
                return self._ok(sorted({r.warehouse for r in service.records}))
            if path == "/api/customers":
                customers = {
                    c.strip()
                    for r in service.records
                    for c in r.customer.split("/")
                }
                return self._ok(sorted(c for c in customers if c))
            if path == "/api/query":
                variety = qs.get("variety", [""])[0]
                warehouse = qs.get("warehouse", [None])[0]
                customer = qs.get("customer", [None])[0]
                qty = qs.get("qty", [None])[0]
                min_qty = float(qty) if qty not in (None, "") else None
                return self._ok(
                    service.query(
                        variety,
                        warehouse=warehouse,
                        customer=customer,
                        min_qty=min_qty,
                    )
                )
            return self._err(404, "not_found", "接口不存在")

        def _handle_api_post(self, path: str, data) -> None:
            if path == "/api/deduct":
                variety = data.get("variety")
                qty = float(data.get("qty"))
                warehouse = data.get("warehouse")
                with lock:
                    result = service.deduct(variety, qty, warehouse=warehouse)
                return self._ok(result)
            if path == "/api/import":
                with lock:
                    records = self._import_records(data)
                    service.replace_records(records)
                return self._ok({"imported": len(records)})
            if path == "/api/agent":
                from .agent import AllocationAgent

                message = data.get("message") or ""
                with lock:
                    result = AllocationAgent(service).run(message)
                return self._ok(result)
            return self._err(404, "not_found", "接口不存在")

        def _import_records(self, data):
            if data.get("json_path"):
                return get_parser("json").parse(data["json_path"])
            if data.get("image_path"):
                return get_parser(data.get("ocr", "easyocr")).parse(data["image_path"])
            if data.get("image_base64"):
                raw = base64.b64decode(data["image_base64"])
                suffix = os.path.splitext(data.get("filename", "image.png"))[1] or ".png"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(raw)
                    return get_parser(data.get("ocr", "easyocr")).parse(tmp_path)
                finally:
                    os.remove(tmp_path)
            if data.get("text"):
                return DeepSeekStructurer().structure(data["text"])
            raise ValueError("需要 json_path / image_path / image_base64 / text 之一")

        def _varieties_summary(self):
            groups = {}
            for r in service.records:
                g = groups.setdefault(
                    r.variety_code,
                    {
                        "code": r.variety_code,
                        "name": r.variety_name,
                        "available": 0.0,
                        "oversold": 0.0,
                        "warehouses": set(),
                    },
                )
                g["available"] += r.available
                g["oversold"] += -r.unsold_qty if r.oversold else 0.0
                g["warehouses"].add(r.warehouse)
            result = []
            for g in groups.values():
                result.append(
                    {
                        "code": g["code"],
                        "name": g["name"],
                        "available": g["available"],
                        "oversold": g["oversold"],
                        "warehouses": sorted(g["warehouses"]),
                    }
                )
            return result

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"分量表 API 已启动: http://{host}:{port}")
    print(f"  前端演示页: http://{host}:{port}/")
    print("  接口文档:   见 API.md")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
