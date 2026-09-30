# 分量表服务（PET 贸易）原型

「AI产品实习生 · 环节2」动手任务的 Python 原型：把供应商每天发的**分量表**（图片）解析成结构化数据，提供**查询接口**并支持**出库扣减**。核心代码只用 Python 标准库，零第三方依赖。

## 快速开始

```powershell
cd C:\Users\34930\Documents\Codex\2026-09-29\qin\outputs
python main.py list
python main.py query 油料 --qty 33
python main.py deduct 油料 33
```

> 也可用 `python -m fensiliang_service.cli ...` 替代 `python main.py ...`。

## 命令一览

| 命令 | 说明 |
|------|------|
| `list` | 列出全部分量表记录（超卖行会标注 `[超卖]`） |
| `query <品种> [--qty 数量] [--warehouse 仓库] [--customer 客户]` | 查询并汇总可售量 |
| `deduct <品种> <数量> [--warehouse 仓库]` | 出库扣减，跨仓 FIFO 拆分，库存不足报错且不落盘 |
| `import --json sample_data.json` | 离线导入结构化数据（默认演示方式） |
| `import --image 分量表示例.png --ocr cloud` | 用云端视觉模型 OCR 图片（需 API key） |
| `serve --port 8000` | 启动 HTTP JSON 接口 |
| `agent "我要33吨油料"` | 自然语言智能体（需 DEEPSEEK_API_KEY） |

不带子命令直接运行 `python main.py` 会进入交互式命令行。

## HTTP 接口（给前端用）

```powershell
python main.py serve --port 8000
```

- 前端演示页：打开 `http://127.0.0.1:8000/`
- 完整接口文档：见 [API.md](API.md)

接口前缀统一为 `/api/`，支持 CORS 跨域，统一返回 `{"ok":true,"data":...}` / `{"ok":false,"error":...,"code":...}`。主要接口：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/records` | 全部记录 |
| GET | `/api/varieties` | 品种汇总（下拉框） |
| GET | `/api/warehouses` | 仓库列表 |
| GET | `/api/customers` | 客户列表 |
| GET | `/api/query` | 查询（variety/qty/warehouse/customer） |
| POST | `/api/deduct` | 出库扣减（库存不足返回 409） |
| POST | `/api/import` | 导入（json_path / image_path / image_base64 / text） |
| POST | `/api/agent` | 自然语言智能体（body 传 `{"message":"..."}`） |

## 自然语言智能体（AI Agent）

在业务服务之上加了一层「智能体」：大模型（DeepSeek 函数调用）拿到自然语言后，自主决定调用 `query_available` / `deduct_stock` 工具，多步执行后给出结论。

```powershell
$env:DEEPSEEK_API_KEY="你的key"
python main.py agent "我要33吨油料，从东莞发"
```

HTTP 方式（前端可用）：

```powershell
python main.py serve --port 8000
```

```javascript
const res = await fetch('/api/agent', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: '我要33吨油料' }),
}).then(r => r.json());
// res.data.answer 是自然语言回答，res.data.tool_calls 是工具调用记录
```

## OCR 方案（可插拔）

OCR 层是 `fensiliang_service/ocr/` 下的可插拔接口，默认用 `JsonParser` 离线读结构化 JSON 跑通全流程；另有多种适配器待本机接入：

- **云端视觉模型**（`CloudVisionParser`）：调用 OpenAI 兼容接口，配置环境变量后运行：
  ```powershell
  $env:OCR_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
  $env:OCR_API_KEY="你的key"
  $env:OCR_MODEL="qwen-vl-max"
  python main.py import --image 分量表示例.png --ocr cloud
  ```
- **离线 PaddleOCR**（`PaddleOcrParser`）：需 `pip install paddleocr paddlepaddle`，按真实表格微调行列阈值后运行：
  ```powershell
  python main.py import --image 分量表示例.png --ocr paddle
  ```

- **离线 EasyOCR**（`EasyOcrParser`）：中文识别效果较好、安装相对简单，无需 key：
  ```powershell
  python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple
  python main.py import --image 分量表示例.png --ocr easyocr
  ```

- **DeepSeek 结构化**（`DeepSeekStructurer` / `DeepSeekPipeline`）：DeepSeek 是纯文本模型，不能直接看图，但很适合把 OCR 出来的乱文字整理成 JSON。两段式：
  1. 先用任意工具把图片转成文字（PaddleOCR、手机/微信的图片转文字、在线 OCR 等）；
  2. 再让 DeepSeek 把文字整理成结构化记录。

  方式 A —— 只给 DeepSeek 一段文字（不用装重型 OCR 库）：
  ```powershell
  $env:DEEPSEEK_API_KEY="你的key"
  python main.py import --text raw.txt
  ```
  方式 B —— 一步到位（图片 → PaddleOCR 认字 → DeepSeek 结构化）：
  ```powershell
  $env:DEEPSEEK_API_KEY="你的key"
  python main.py import --image 分量表示例.png --ocr deepseek
  ```

## 数据模型与规则

- 记录字段：`warehouse`(库位)、`variety_code`(品种代码)、`variety_name`(品种名)、`customer`(客户，多家用 `/` 分隔)、`unsold_qty`(未下量，吨)。
- 品种映射：`Y01=油料 / H01=热料 / C01=碳酸 / W01=水料`；`新` 前缀 = 新线产品（如 `新W01` = 新线水料）。
- 查询兼容「代码」或「中文名」两种输入。
- `未下量 < 0` = **超卖**，不计入可售量，仅在查询中标记 `oversold`。
- 扣减按可售量 **FIFO**（库位名排序后贪心）跨仓拆分，单仓不扣成负数；库存不足时**拒绝且不落盘**。

## 测试

```powershell
cd C:\Users\34930\Documents\Codex\2026-09-29\qin\outputs
python -m unittest discover -s tests -t . -v
```

## 说明与限制

- 当前沙箱无网络、无 OCR 库，无法对真实图片跑 OCR；默认用 `sample_data.json` 离线演示，OCR 适配器需在本机联网或安装模型后接入。
- 核心逻辑仅标准库，系统 Python 3.14 与内置 Python 3.12 均可运行。
