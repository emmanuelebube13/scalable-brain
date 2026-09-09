import json

files = {
    "Control": "results/reports/attribution_report_20260908T133944Z.json",
    "Treatment": "results/reports/attribution_report_20260908T134051Z.json"
}

for name, fpath in files.items():
    with open(fpath) as f:
        data = json.load(f)
    print(f"=== {name} ===")
    print("Label:", data.get("regime_label", "missing"))
    print("Engine:", data.get("engine_used", "missing"))
    dist = data.get("regime_distribution", {})
    for k, v in dist.items():
        print(f"{k}: {v}")
    
    total = sum(dist.values())
    unknown = dist.get("UNKNOWN", 0)
    print(f"UNKNOWN share: {unknown/total*100:.2f}%")

