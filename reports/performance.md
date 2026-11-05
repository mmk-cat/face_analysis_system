# 性能与压测结果

## 1. 结论

| 指标 | 基线实现 | 优化实现 | 变化 |
|---|---:|---:|---:|
| JMeter 50 并发 P95 | **1551.05 ms** | **547.1 ms** | **-64.7%** |
| JMeter 100 并发 P95 | **1552.4 ms** | **550.25 ms** | **-64.6%** |
| JMeter 50 并发错误率 | 0% | 0% | 持平 |
| JMeter 100 并发错误率 | 0% | 0% | 持平 |
| Python 冷请求 50 并发 P95 | 1682.15 ms | 1009.4 ms | -40.0% |
| Python 重复请求 50 并发 P95 | 1670.97 ms | 245.41 ms | -85.3% |

> 环境：Windows 11、Python 3.12、JMeter 5.6.3、Java 21、mock 上游每次调用固定 500 ms。  
> 基线：`detect(image_a)` + `detect(image_b)` + `compare` 串行 3 次上游调用，每次新建连接。  
> 优化：一次 `face_compare`，requests Session 连接池，超时/有限重试，Idempotency-Key 去重与 SQLite 持久化。

## 2. JMeter 50 / 100 并发

计划：`jmeter/face_compare.jmx`，POST `/api/v1/face/compare`，multipart 上传两张同一图片，50 线程 × 2 循环 / 100 线程 × 1 循环。

| 服务 | 并发 | samples | 成功 | 错误 | P50 | P90 | P95 | P99 | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 50 | 100 | 100 | 0 | 1524.0 | 1542.3 | **1551.05** | 1554.05 | 1559.0 |
| optimized | 50 | 100 | 100 | 0 | 522.0 | 541.0 | **547.1** | 557.09 | 566.0 |
| baseline | 100 | 100 | 100 | 0 | 1523.0 | 1541.4 | **1552.4** | 1566.0 | 1566.0 |
| optimized | 100 | 100 | 100 | 0 | 521.0 | 544.1 | **550.25** | 566.16 | 582.0 |

原始 JTL：`reports/jmeter_baseline_50.jtl`、`jmeter_baseline_100.jtl`、`jmeter_50.jtl`、`jmeter_100.jtl`。  
汇总 JSON：`reports/jmeter_*_summary.json`。

## 3. Python 对照压测

命令：

```powershell
python -m benchmarks.benchmark --latency-ms 500 --requests 100 --concurrency 50 100
```

结果保存在 `reports/benchmark.json` / `reports/benchmark.md`：

- `cold-c50`：基线 P95 1682.15 ms，优化 P95 1009.4 ms；
- `optimized-retry-c50`：重复 Idempotency-Key 场景 P95 245.41 ms；
- 100 并发时基线 P95 约 1691 ms，优化冷请求 P95 约 1291 ms。

## 4. 解读与局限

- 本压测定位的第一瓶颈是 **逐图 detect + compare 的串行上游调用**；优化为单次 face_compare 后，P95 从约 1.55 s 降到约 0.55 s。
- `Idempotency-Key` 主要解决客户端重试/重复提交造成的重复上游调用；在重复请求场景，P95 可降到约 0.25 s。
- mock 上游固定延迟 500 ms，未模拟真实讯飞限流；`IFlytekClient` 已带 429 重试、超时和 502/503/504 映射，仍建议在真实环境用 JMeter 复测。
- 50/100 并发均为 0 错误；未做长时间稳定性/内存泄漏测试。
- 原始简历模板中的 3.2 s → 0.8 s 没有照搬；以本机实测 **1.55 s → 0.55 s** 为准。
