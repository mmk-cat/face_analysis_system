# API 说明

Base URL：`http://127.0.0.1:5003`  
业务前缀：`/api/v1/face`  
认证：`X-API-Key: dev-service-key`（除 `/health` 外）  
上传：`multipart/form-data`  
请求追踪：可选 `X-Request-ID`，响应头/响应体回传。  
幂等：可选 `Idempotency-Key`（1-128 位 `[A-Za-z0-9._:-]`）。

## 5 个业务接口

| # | 方法 | 路径 | 说明 |
|---:|---|---|---|
| 1 | POST | `/api/v1/face/detect` | 检测人脸，返回人脸框、质量、图片尺寸 |
| 2 | POST | `/api/v1/face/analyze` | 返回年龄/性别/眼镜/口罩/情绪等属性 |
| 3 | POST | `/api/v1/face/compare` | 1:1 比对，返回 similarity、阈值、same_person |
| 4 | POST | `/api/v1/face/register` | 注册人脸到分组（group_id + person_id） |
| 5 | POST | `/api/v1/face/search` | 1:N 检索，返回 Top-K 匹配 |

运维接口：`GET /health`（不计入 5 个业务接口）。

## 统一成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "ce522ca2d2664d5282cd83fc203ed777"
}
```

## 幂等

- 相同 `Idempotency-Key` + 相同参数：返回第一次成功结果，响应头 `X-Idempotent-Replay: true`，不再调用上游。
- 相同 key + 不同图片/表单：`409 40900`。
- key 格式非法：`400 40006`。
- 缓存 TTL：600 秒；服务端按 key 加锁，避免并发击穿。

## CORS

允许来源通过 `ALLOWED_ORIGINS` 配置；`OPTIONS` 预检不要求 API Key，返回：

```
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-API-Key, Idempotency-Key, X-Request-ID
```

不在白名单的 Origin 不返回 `Access-Control-Allow-Origin`。

## 错误码

| code | HTTP | 含义 |
|---:|---:|---|
| 40001 | 400 | 缺少文件/字段 |
| 40002 | 400 | 空文件 |
| 40003 | 400 | 非法图片字节 |
| 40005 | 400 | 表单值非法（attributes/top_k/group_id/person_id/name） |
| 40006 | 400 | Idempotency-Key 格式非法 |
| 40100 | 401 | 缺少 X-API-Key |
| 40101 | 401 | X-API-Key 无效 |
| 40400 | 404 | 路由不存在 |
| 40500 | 405 | 方法不允许 |
| 40900 | 409 | 相同幂等键但参数不一致 |
| 40901 | 409 | 分组内 person_id 已存在 |
| 41300 | 413 | 图片/请求体超过上限 |
| 41500 | 415 | 图片格式不支持（仅 PNG/JPEG/WEBP） |
| 42202 | 422 | 图片分辨率过小/过大 |
| 42204 | 422 | 解压炸弹防护 |
| 50200 | 502 | 上游业务错误 |
| 50201 | 502 | 上游签名鉴权失败 |
| 50202 | 502 | 上游不可用 |
| 50301 | 503 | 上游限流（带 Retry-After） |
| 50400 | 504 | 上游超时 |
| 50000 | 500 | 未处理异常 |

## 字段约束

- 图片格式：PNG / JPEG / WEBP；单图 ≤ 4 MiB；边长 32~8000 px。
- `attributes`：JSON 数组，可选 `age/gender/glasses/mask/emotion/quality`，默认前四项。
- `top_k`：整数 1~50，只接受 ASCII 数字。
- `group_id`：1~32 位字母/数字/下划线/连字符。
- `person_id`：3~32 位字母/数字/下划线/连字符。
- `name`：≤ 50 字符，缺省等于 person_id。

## 讯飞签名

`IFLYTEK_APP_ID`、`IFLYTEK_API_KEY`、`IFLYTEK_BASE_URL` 配置真实服务后，客户端发送：

```
X-Appid: <app id>
X-CurTime: <unix 秒>
X-Param: <base64(JSON)>
X-CheckSum: md5(api_key + cur_time + param)
```

签名失败由上游返回 401，应用层映射为 `502 50201`。测试默认指向本地 mock server；未使用付费账号验证真实模型效果。

## curl 示例

```bash
curl -X POST http://127.0.0.1:5003/api/v1/face/compare \
  -H "X-API-Key: dev-service-key" \
  -F "image_a=@data/samples/face_a.png" \
  -F "image_b=@data/samples/face_a.png"
```

> 示例图片是 PIL 生成的几何头像，不包含真实人脸或个人数据。
