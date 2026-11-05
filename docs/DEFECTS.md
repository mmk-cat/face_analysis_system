# 缺陷与回归台账

> 本项目是个人自测项目，没有外部缺陷平台单据。下表记录开发/测试过程中真实发现并修复的问题，包含 4 个服务/质量问题和 2 个测试资产问题，便于面试时说明“如何定位、如何回归”。

## 缺陷清单

| ID | 类型 | 严重度 | 现象 | 根因 | 修复 | 回归用例 |
|---|---|---|---|---|---|---|
| FACE-001 | 服务 | 中 | `top_k=１`（全角数字）被当成合法整数 | `\d` 匹配 Unicode 数字，`int()` 又能转换 | 改为 `[0-9]+` ASCII 校验 | `test_search_top_k_rejects_non_ascii_digits` |
| FACE-002 | 质量 | 低 | `/health` 反复调用会累积未关闭的 SQLite 连接 | `Repository.ping()` 直接返回 `conn.execute()`，没有 finally close | 显式关闭连接 | `test_health_is_public` + 长稳观察 |
| FACE-003 | 服务 | 高 | 路由鉴权 Key 在 import 时被固定，切换环境后有效 Key 仍返回 401 | 装饰器参数硬编码了占位 Key | 鉴权在请求时从 `current_app.extensions` 读取 | 全部 `test_*_requires_api_key` |
| FACE-004 | 质量 | 低 | 大量不同 Idempotency-Key 请求后，进程内锁字典只增不减 | 每 key 一个 `threading.Lock`，用完未回收 | 引用计数，最后一个等待者释放后移除 | `test_idempotency_locks_are_reclaimed` |
| FACE-005 | 测试资产 | 高 | JMeter 50/100 并发全部 `Invalid content type`，上游 0 请求 | JMX 文件字段名写成 `ParamName/MimeType`，JMeter 读取为 `File.paramname/File.mimetype` | 修正 JMX 属性名；2 线程冒烟后 50/100 全绿 | `reports/jmeter_50_summary.json` |
| FACE-006 | 测试资产 | 中 | 基线压测被 JSON 断言判定 100% 失败，但实际 HTTP 200 | baseline 响应缺少 `code=0`，断言按统一响应校验 | baseline 补 `code` 字段，重新压测 | `reports/jmeter_baseline_*.jtl` |

## 两轮回归

### Round 1 — 功能回归

- 初始 70 条 pytest：**70 passed**；
- 探索性输入发现 FACE-001；代码审查发现 FACE-002/FACE-004；修正后新增 2 条回归用例；
- 接口 / 安全 / 并发回归全部通过。

### Round 2 — 全量回归 + 压测

- pytest：**72 passed in 2.88 s**（0 failed / 0 skipped）；
- JMeter 50 并发：100 请求，0 错误，P95 **547.1 ms**；
- JMeter 100 并发：100 请求，0 错误，P95 **550.25 ms**；
- 基线对照：P95 **1551.05 / 1552.4 ms**，0 错误；
- 两轮均保留 JUnit / HTML / JTL 结果。

## 备注

- FACE-003 是开发早期路由骨架中的真实问题：`@require_api_key("dev-service-key")` 在模块 import 时求值，导致配置无法生效。
- FACE-005/006 属测试资产缺陷，不计入服务端缺陷数；面试时可说明“6 个自测缺陷，其中 4 个产品/质量问题、2 个测试脚本问题”。
- 未发现但已由测试护栏覆盖的风险：超大图片 413、GIF 415、签名 401→502、CORS 预检、并发同 Key 只调用一次上游。

