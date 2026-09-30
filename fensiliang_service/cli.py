"""命令行交互入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .service import AllocationService, InsufficientStockError
from .storage import JsonStorage
from .ocr import get_parser, DeepSeekStructurer


DEFAULT_DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data.json"
)


def print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _make_service(data_path: str) -> AllocationService:
    return AllocationService(JsonStorage(data_path))


def cmd_list(args) -> None:
    service = _make_service(args.data)
    service.load()
    for record in service.list_all():
        flag = " [超卖]" if record.oversold else ""
        print(
            f"{record.warehouse}\t{record.variety_code}({record.variety_name})"
            f"\t{record.customer}\t{record.unsold_qty}{flag}"
        )


def cmd_query(args) -> None:
    service = _make_service(args.data)
    service.load()
    result = service.query(
        args.variety,
        warehouse=args.warehouse,
        customer=args.customer,
        min_qty=args.qty,
    )
    print_json(result)


def cmd_deduct(args) -> None:
    service = _make_service(args.data)
    service.load()
    try:
        result = service.deduct(args.variety, args.qty, warehouse=args.warehouse)
    except InsufficientStockError as e:
        print(f"错误: {e}", file=sys.stderr)
        raise SystemExit(2)
    print_json(result)


def cmd_import(args) -> None:
    service = _make_service(args.data)
    if args.json:
        records = get_parser("json").parse(args.json)
    elif args.image:
        records = get_parser(args.ocr).parse(args.image)
    elif args.text:
        with open(args.text, "r", encoding="utf-8") as f:
            raw_text = f.read()
        records = DeepSeekStructurer().structure(raw_text)
    else:
        raise SystemExit("import 需要 --json 或 --image 或 --text")
    service.replace_records(records)
    print(f"已导入 {len(records)} 条记录 -> {args.data}")


def cmd_serve(args) -> None:
    from .http_api import serve

    serve(args.data, host=args.host, port=args.port)


def cmd_agent(args) -> None:
    from .agent import AllocationAgent

    service = _make_service(args.data)
    service.load()
    try:
        result = AllocationAgent(service).run(args.message)
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        raise SystemExit(2)
    print(f"回答: {result['answer']}")
    if result["tool_calls"]:
        print("\n工具调用记录:")
        for call in result["tool_calls"]:
            print(f"  - {call['tool']} {call['args']} -> {call['result']}")


def interactive(data_path: str) -> None:
    service = _make_service(data_path)
    service.load()
    print("分量表服务交互模式（输入 help 查看命令，exit 退出）")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        parts = raw.split()
        cmd = parts[0].lower()
        if cmd in ("exit", "quit", "q"):
            break
        if cmd == "help":
            print("list | query <品种> [--qty 数量] [--warehouse 仓库] | deduct <品种> <数量> [仓库]")
            continue
        if cmd == "list":
            for record in service.list_all():
                flag = " [超卖]" if record.oversold else ""
                print(
                    f"{record.warehouse}\t{record.variety_code}({record.variety_name})"
                    f"\t{record.customer}\t{record.unsold_qty}{flag}"
                )
            continue
        if cmd == "query" and len(parts) >= 2:
            variety = parts[1]
            warehouse = None
            qty = None
            rest = parts[2:]
            if "--qty" in rest:
                i = rest.index("--qty")
                if i + 1 < len(rest):
                    qty = float(rest[i + 1])
            if "--warehouse" in rest:
                i = rest.index("--warehouse")
                if i + 1 < len(rest):
                    warehouse = rest[i + 1]
            print_json(service.query(variety, warehouse=warehouse, min_qty=qty))
            continue
        if cmd == "deduct" and len(parts) >= 3:
            variety = parts[1]
            qty = float(parts[2])
            warehouse = parts[3] if len(parts) >= 4 else None
            try:
                print_json(service.deduct(variety, qty, warehouse=warehouse))
            except InsufficientStockError as e:
                print(f"错误: {e}")
            continue
        print("未知命令，输入 help 查看用法")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="fensiliang", description="PET 分量表查询与出库扣减"
    )
    parser.add_argument("--data", default=None, help="数据 JSON 路径")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="列出全部记录")
    p_list.set_defaults(func=cmd_list)

    p_query = sub.add_parser("query", help="查询")
    p_query.add_argument("variety")
    p_query.add_argument("--qty", type=float, default=None)
    p_query.add_argument("--warehouse", default=None)
    p_query.add_argument("--customer", default=None)
    p_query.set_defaults(func=cmd_query)

    p_deduct = sub.add_parser("deduct", help="出库扣减")
    p_deduct.add_argument("variety")
    p_deduct.add_argument("qty", type=float)
    p_deduct.add_argument("--warehouse", default=None)
    p_deduct.set_defaults(func=cmd_deduct)

    p_import = sub.add_parser("import", help="导入数据")
    p_import.add_argument("--json", default=None)
    p_import.add_argument("--image", default=None)
    p_import.add_argument("--text", default=None, help="原始 OCR 文本文件（用 DeepSeek 结构化）")
    p_import.add_argument(
        "--ocr", default="cloud", help="image 解析器: cloud|paddle|easyocr|deepseek"
    )
    p_import.set_defaults(func=cmd_import)

    p_serve = sub.add_parser("serve", help="启动 HTTP 服务")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    p_agent = sub.add_parser("agent", help="自然语言智能体（需 DEEPSEEK_API_KEY）")
    p_agent.add_argument("message")
    p_agent.set_defaults(func=cmd_agent)

    args = parser.parse_args(argv)
    if not getattr(args, "data", None):
        args.data = DEFAULT_DATA

    if getattr(args, "command", None) is None:
        interactive(args.data)
        return
    args.func(args)


if __name__ == "__main__":
    main()
