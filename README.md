# 人脸智能分析与比对系统

基于 **Python + Flask + 讯飞 WebAPI 签名 + Postman + JMeter + Fiddler 调试方法** 的人脸检测、属性分析、1:1 比对、1:N 检索和人脸注册服务。默认使用本地签名 Mock，无需讯飞账号即可跑通；配置真实 `IFLYTEK_APP_ID/API_KEY/BASE_URL` 后切换到讯飞 WebAPI。

## 已验收结果

| 指标 | 实测值 |
|---|---:|
| 业务接口 | **5** 个（另含 `/health` 运维接口） |
| pytest | **72 passed in 2.88 s**（0 failed / 0 skipped） |
| 接口级用例 | 51 条；横切安全/并发/契约 21 条 |
| 场景覆盖 | 正常、缺参、类型错误、超大图片、签名失败、重复请求、CORS、并发，共 **8 类** |
| JMeter 50 并发 P95 | 基线 **1551.05 ms** → 优化 **547.1 ms** |
| JMeter 100 并发 P95 | 基线 **1552.4 ms** → 优化 **550.25 ms** |
| JMeter 错误率 | 50/100 并发均 **0%** |
| 自测缺陷 | **6** 个（4 个服务/质量问题 + 2 个测试资产问题），2 轮回归 |
| 讯飞签名失败映射 | 上游 401 → 应用 **502 / 50201** |

> 报告：`reports/pytest-report.html`、`reports/junit.xml`、`reports/performance.md`、`reports/jmeter_*`。  
> 缺陷台账：`docs/DEFECTS.md`；接口文档：`docs/API.md`。

## 快速开始

```powershell
cd "C:\Users\LENOVO\Desktop\项目\03_face_analysis_system"
python -m pip install -r requirements.txt
python tools/generate_samples.py
python -m app.run
# http://127.0.0.1:5003/health
```

默认 `PROVIDER_MODE=mock`，使用进程内确定性合成 provider，适合本地演示。测试与压测默认使用“本地签名 Mock 讯飞服务 + 应用 iflytek 模式”，从而真实验证签名头、失败映射和 HTTP 连接。

### 切换到本地签名 Mock（测试/压测同款）

```powershell
# 终端 1
python -m mock_iflytek.run --port 5100 --latency-ms 30

# 终端 2
$env:PROVIDER_MODE="iflytek"
$env:IFLYTEK_BASE_URL="http://127.0.0.1:5100"
$env:IFLYTEK_APP_ID="demo-app"
$env:IFLYTEK_API_KEY="demo-api-key"
$env:API_KEY="dev-service-key"
python -m app.run
```

## 5 个接口

| # | 方法 | 路径 | 关键参数 | 说明 |
|---:|---|---|---|---|
| 1 | POST | `/api/v1/face/detect` | `image` | 检测人脸、返回 bbox/质量 |
| 2 | POST | `/api/v1/face/analyze` | `image`, `attributes` | 属性分析 |
| 3 | POST | `/api/v1/face/compare` | `image_a`, `image_b` | 1:1 比对 |
| 4 | POST | `/api/v1/face/register` | `image`, `group_id`, `person_id`, `name` | 写入本地人脸库 |
| 5 | POST | `/api/v1/face/search` | `image`, `group_id`, `top_k` | 1:N Top-K 检索 |

认证：除 `/health` 外均需 `X-API-Key`。幂等：可选 `Idempotency-Key`。  
完整错误码与字段约束见 [`docs/API.md`](docs/API.md)。

## 目录

```
03_face_analysis_system/
├─ app/
│  ├─ __init__.py            # Flask 工厂、CORS、错误映射、/health
│  ├─ api.py                 # 5 个业务路由
│  ├─ service.py             # 检测/分析/比对/注册/检索业务
│  ├─ validation.py          # 图片、attributes、top_k、ID 校验
│  ├─ security.py            # API Key、幂等锁、防并发击穿
│  ├─ db.py                  # SQLite 人脸库 + 幂等记录
│  └─ provider/              # mock / 讯飞 WebAPI 客户端
├─ mock_iflytek/             # 签名校验 HTTP Mock（detect/analysis/compare）
├─ tests/                    # 72 条 pytest
├─ postman/                  # 5 接口 Postman collection
├─ jmeter/                   # 参数化 50/100 并发 JMX + README
├─ benchmarks/               # 基线 vs 优化压测、基线服务
├─ reports/                  # JUnit/HTML/JTL/性能报告
├─ docs/                     # API/缺陷台账
└─ tools/generate_samples.py # 生成合成头像
```

## 关键实现

- **签名**：`X-CheckSum = md5(api_key + cur_time + param_b64)`，与讯飞 WebAPI 的 Appid/CurTime/Param/CheckSum 风格一致；Mock 服务严格校验 AppID、时间窗（300s）和 checksum。
- **幂等**：`Idempotency-Key` 持久化到 SQLite；同 key 同参数返回原结果并带 `X-Idempotent-Replay`；同 key 不同参数返回 409；进程内按 key 加锁，避免并发请求同时打上游。
- **图片安全**：先按字节上限拦截（4MiB），再用 Pillow verify、格式白名单（PNG/JPEG/WEBP）、尺寸下限/上限、解压炸弹防护。
- **CORS**：配置白名单回显 Origin；预检不要求 API Key；错误响应同样带 CORS 头。
- **上游错误映射**：签名 401→50201，限流 429→50301，超时→50400，5xx→50202，业务错误→50200。
- **并发**：同 Idempotency-Key 的 8 并发只触发 1 次上游调用；16 并发检测 0 个 500。
- **可观测**：`X-Request-ID`、`X-Process-Time-Ms`、`X-Provider-Mode`，日志脱敏，错误统一 JSON。

## 测试设计

| 模块 | 用例数 | 覆盖 |
|---|---:|---|
| health/contract | 7 | 健康、CORS 白名单/非白名单、404/405、Request-ID |
| detect | 13 | PNG/JPEG、缺参、空文件、非法字节、GIF、小图、超大、鉴权、幂等、预检 |
| analyze | 10 | 默认/指定属性、非法 JSON/类型/未知字段、空文件、超大、鉴权、幂等 |
| compare | 11 | 同人/不同人、缺 A/B、空/非法/超大、鉴权、幂等冲突、CORS |
| register + search | 17 | 注册、重复、缺/非法 person_id、空组、命中/不命中、top_k 边界、group 校验、幂等 |
| provider signature | 6 | 合法签名、缺 checksum、篡改、过期、AppID 错误、应用层 502 |
| concurrency | 4 | 16 并发检测、8 并发同 key、8 并发 compare、锁回收 |
| DB contract | 4 | 人脸图/哈希落库、幂等记录、唯一约束、密钥不泄漏 |

8 类场景：缺参、类型错误、超大图片、签名失败、重复请求、CORS、并发、正常路径。

## Postman / JMeter / Fiddler

- Postman：导入 `postman/Face API.postman_collection.json`，设置 `base_url`、`api_key`、文件路径变量；collection 内含状态码/业务码断言。
- JMeter：
  ```powershell
  Set-Location "C:\Users\LENOVO\Desktop\项目\03_face_analysis_system"
  jmeter -n -t jmeter/face_compare.jmx -Jthreads=50 -Jloops=2 -Jport=5003 `
    -Jsample_dir="$PWD/data/samples" -l reports/jmeter_50.jtl
  ```
  详见 `jmeter/README.md`。**注意**：JMX 的 file 字段属性必须是 `File.paramname` / `File.mimetype`，这是本项目实际踩过的坑。
- Fiddler：过滤 `/api/v1/face/`，重点检查 multipart 字段名（`image`/`image_a`/`image_b`）、`X-API-Key`、`Idempotency-Key`、响应 `X-Request-ID` 与 413/502 响应体；配置方法见 `docs/DEBUGGING.md`。

## 压测结论

固定 500ms mock 上游、50/100 并发：

| 版本 | 上游调用 | P95 @50 | P95 @100 | 错误率 |
|---|---|---:|---:|---:|
| baseline | detect×2 + compare（3 次，新连接） | 1551.05 ms | 1552.4 ms | 0% |
| optimized | compare×1 + 连接池 + 超时/重试 + 幂等 | **547.1 ms** | **550.25 ms** | 0% |

P95 降幅约 **64.7%**。重复提交（同 Idempotency-Key）的 Python 压测 P95 从 1670.97 ms 降到 **245.41 ms**。未把未验证的 3.2s/0.8s 写进报告。

## 简历占位符回填

| 原占位符 | 本项目实测 |
|---|---|
| 5 个接口输出 X 条用例 | **72** 条（51 条接口级 + 21 条横切安全/并发/契约） |
| P95 由 3.2s 降至 0.8s | 实测 **1.55s → 0.55s**（JMeter 100 并发，500ms mock 上游） |
| 提交 X 个缺陷 | 自测 **6** 个（4 服务/质量 + 2 测试资产），见 `docs/DEFECTS.md` |
| 完成 2 轮回归 | Round 1 功能 70 passed；Round 2 全量 **72 passed**，JMeter 50/100 全绿 |

## 边界与说明

- 默认 provider 和 Mock 讯飞服务都是**确定性合成模型**，不是真实人脸识别；示例图片为 PIL 几何头像，不涉及真实个人信息。
- 代码包含真实讯飞 WebAPI 的签名与错误适配，但由于没有付费账号，未验证真实模型准确率；生产使用前需用真实 Key 复测。
- 幂等锁是单进程实现；多副本部署需换 Redis/MySQL 唯一键。
- Fiddler 未在本机安装，未附 `.saz`；调试步骤见 `docs/DEBUGGING.md`。

