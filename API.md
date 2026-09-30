# 分量表服务 · 前端接口文档

启动服务后，基地址为 `http://127.0.0.1:8000`（默认端口，可用 `--port` 修改）。

```powershell
cd C:\Users\34930\Documents\Codex\2026-09-29\qin\outputs
python main.py serve --port 8000
```

- 浏览器打开 `http://127.0.0.1:8000/` 有自带演示页。
- 所有接口均支持 CORS（`Access-Control-Allow-Origin: *`），前端可跨域调用。

## 统一返回格式

成功（HTTP 2xx）：

```json
{ "ok": true, "data": { } }
```

失败（HTTP 4xx/5xx）：

```json
{ "ok": false, "error": "错误描述", "code": "错误码" }
```

## 接口清单

### 1. 健康检查

`GET /api/health`

响应：`{ "ok": true, "data": { "status": "ok" } }`

### 2. 全部记录

`GET /api/records`

响应 `data`：

```json
{
  "records": [
    {
      "warehouse": "东莞",
      "variety_code": "Y01",
      "variety_name": "油料",
      "customer": "广州石化",
      "unsold_qty": 120.5,
      "available": 120.5,
      "oversold": false
    }
  ],
  "total": 16
}
```

### 3. 品种汇总（下拉框用）

`GET /api/varieties`

响应 `data`：

```json
[
  { "code": "Y01", "name": "油料", "available": 273.5, "oversold": 0, "warehouses": ["东莞", "黄埔", "新会", "湛江"] }
]
```

### 4. 仓库列表

`GET /api/warehouses` → `["东莞","黄埔","新会","湛江"]`

### 5. 客户列表

`GET /api/customers` → `["广州石化","江门塑业", ...]`

### 6. 查询

`GET /api/query?variety=油料&warehouse=东莞&customer=广州石化&qty=33`

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| variety | 是 | 品种代码或中文名（`Y01` / `油料` / `新W01`） |
| qty | 否 | 需求数量（吨），给定时返回能否满足与凑货方案 |
| warehouse | 否 | 按仓库过滤 |
| customer | 否 | 按客户过滤（子串匹配） |

响应 `data` 含：`records`、`total_available`、`oversold_count`、`fulfillable`、`fulfillment_plan`。

### 7. 出库扣减

`POST /api/deduct`

请求体：

```json
{ "variety": "Y01", "qty": 33, "warehouse": "东莞" }
```

- 成功（200）：`data` 含 `requested`、`deductions`（每仓扣了多少）、`remaining_total_available`。
- 库存不足（409）：`{ "ok": false, "error": "...", "code": "insufficient", "available": 240.5 }`。
- 参数错误（400）：`code` 为 `bad_request`。

### 8. 导入 / OCR

`POST /api/import`

四选一传参：

```json
{ "json_path": "sample_data.json" }
```

```json
{ "image_path": "分量表示例.png", "ocr": "easyocr" }
```

```json
{ "image_base64": "<图片base64>", "filename": "分量表示例.png", "ocr": "easyocr" }
```

```json
{ "text": "东莞 Y01 广州石化 120.5\n...", }
```

- `ocr` 可选值：`easyocr`（默认）、`paddle`、`cloud`。
- `text` 方式使用 DeepSeek 结构化，需先设置 `DEEPSEEK_API_KEY` 环境变量。
- 成功（200）：`{ "ok": true, "data": { "imported": 16 } }`。

### 9. 自然语言智能体

`POST /api/agent`

请求体：

```json
{ "message": "我要33吨油料，从东莞发" }
```

- 由大模型（DeepSeek 函数调用）自主决定调用查询/扣减工具，多步执行后返回结论。
- 需设置 `DEEPSEEK_API_KEY` 环境变量。
- 成功（200）`data`：

```json
{
  "answer": "已从东莞扣减33吨油料。",
  "tool_calls": [
    { "tool": "query_available", "args": { "variety": "Y01", "qty": 33 }, "result": { } },
    { "tool": "deduct_stock", "args": { "variety": "Y01", "qty": 33 }, "result": { } }
  ]
}
```

- 未配置 key 时返回 400，`code` 为 `agent_config`。

## 前端调用示例（fetch）

```javascript
// 查询
const r = await fetch('/api/query?variety=油料&qty=33').then(res => res.json());

// 扣减
const d = await fetch('/api/deduct', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ variety: 'Y01', qty: 33 }),
}).then(res => res.json());

// 上传图片 OCR
const file = document.querySelector('input[type=file]').files[0];
const base64 = await new Promise(res => {
  const reader = new FileReader();
  reader.onload = () => res(reader.result.split(',')[1]);
  reader.readAsDataURL(file);
});
const imp = await fetch('/api/import', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ image_base64: base64, filename: file.name, ocr: 'easyocr' }),
}).then(res => res.json());
```

## 错误码

| HTTP | code | 含义 |
|------|------|------|
| 400 | `bad_request` / `invalid_json` | 参数错误 / JSON 解析失败 |
| 404 | `not_found` | 接口或文件不存在 |
| 409 | `insufficient` | 库存不足（附 `available`） |
| 500 | `internal` | 服务端异常 |
