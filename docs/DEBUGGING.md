# Fiddler / 抓包调试指南

本机未安装 Fiddler，因此仓库不附 `.saz` 会话文件。以下步骤用于在 Windows 上复现接口抓包与问题定位。

## 1. 启动服务

```powershell
# 终端 1：讯飞签名 mock
python -m mock_iflytek.run --port 5100 --latency-ms 30

# 终端 2：业务服务（iflytek 模式）
$env:PROVIDER_MODE="iflytek"
$env:IFLYTEK_BASE_URL="http://127.0.0.1:5100"
$env:IFLYTEK_APP_ID="demo-app"
$env:IFLYTEK_API_KEY="demo-api-key"
$env:API_KEY="dev-service-key"
python -m app.run
```

## 2. Fiddler 配置

1. `Tools → Options → HTTPS` 勾选 `Capture HTTPS CONNECTs` 与 `Decrypt HTTPS traffic`；
2. `Connections` 端口默认 8888；本机请求可通过 `http://127.0.0.1:8888` 代理，或在 Fiddler 直接抓 loopback（部分版本需用 machine name 而非 `localhost`）；
3. 过滤器只保留 `Host: 127.0.0.1` 且 `Path contains /api/v1/face/`；
4. Postman 设置 `Proxy → Use system proxy` 或手动 `127.0.0.1:8888`。

## 3. 重点检查项

| 检查项 | 期望 |
|---|---|
| Content-Type | `multipart/form-data; boundary=...` |
| 文件字段 | detect/analyze/search/register 用 `image`；compare 用 `image_a`、`image_b` |
| 鉴权 | `X-API-Key: dev-service-key` |
| 幂等 | 重试请求保留同一个 `Idempotency-Key` |
| 追踪 | 响应头/体 `X-Request-ID` 一致 |
| 413 | JSON `{"code":41300}`，不是 HTML 错误页 |
| 502 | 签名失败 `code=50201`，body 不泄漏 API Key |
| 预检 | `OPTIONS` 返回 200，且无 API Key 也可通过 |

## 4. 常见现象

- **`Invalid content type`（JMeter）**：不是应用问题，检查 JMX 的 file 字段是否为 `File.paramname`、`File.mimetype`；
- **CORS 无 ACAO**：检查请求 `Origin` 是否在 `ALLOWED_ORIGINS`；
- **重试仍打上游**：确认重试携带同一个 `Idempotency-Key`；更换 key 会被视为新请求；
- **413 HTML**：确认请求体未超过 Flask `MAX_CONTENT_LENGTH`（应用为单图上限 + 64 KiB）。

## 5. 可复现的 curl

```bash
curl -i -X POST http://127.0.0.1:5003/api/v1/face/detect \
  -H "X-API-Key: dev-service-key" \
  -F "image=@data/samples/face_a.png"

curl -i -X OPTIONS http://127.0.0.1:5003/api/v1/face/compare \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-api-key"
```
