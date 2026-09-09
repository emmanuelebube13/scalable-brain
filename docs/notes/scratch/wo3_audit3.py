import json
with open("results/reports/attribution_report_20260908T140229Z.json") as f:
    data = json.load(f)
dist = data.get("regime_distribution", {})
for k, v in dist.items():
    print(f"{k}: {v}")
