# JMeter 压测

`face_compare.jmx` 是一个参数化计划，默认 50 线程 × 2 循环；通过 `-J` 覆盖为 100 并发。

## 启动被测服务（500ms 上游延迟）

```powershell
python -m mock_iflytek.run --port 5100 --latency-ms 500
$env:PROVIDER_MODE="iflytek"
$env:IFLYTEK_BASE_URL="http://127.0.0.1:5100"
$env:IFLYTEK_APP_ID="demo-app"
$env:IFLYTEK_API_KEY="demo-api-key"
$env:API_KEY="dev-service-key"
python -m app.run
```

## 执行

```powershell
Set-Location "C:\Users\LENOVO\Desktop\项目\03_face_analysis_system"
jmeter -n -t jmeter/face_compare.jmx -Jthreads=50 -Jloops=2 -Jramp=5 `
  -Jsample_dir="$PWD/data/samples" `
  -l reports/jmeter_50.jtl -e -o reports/jmeter_50

jmeter -n -t jmeter/face_compare.jmx -Jthreads=100 -Jloops=1 -Jramp=5 `
  -Jsample_dir="$PWD/data/samples" `
  -l reports/jmeter_100.jtl -e -o reports/jmeter_100
```

`-e -o` 会生成 HTML Dashboard。JTL 可直接用 `python scripts/summarize_jtl.py` 汇总 P50/P90/P95/P99。

## 与 Python benchmark 的关系

`benchmarks/benchmark.py` 使用同一组场景（cold + retry-storm）和同一 mock 上游延迟，便于在无 JMeter 的环境复现趋势；JMeter 计划用于手工/CI 压测。
