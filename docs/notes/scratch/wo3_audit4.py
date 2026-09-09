import json

with open("results/reports/vetting_report_20260908T140240Z.json") as f:
    data = json.load(f)

for cell in data.get("cells", []):
    if cell["qualified"]:
        print(f"{cell['strategy_id']}@{cell['granularity']} | {cell['regime']} | Trades: {cell['trades']} | PF: {cell['pf']} | Sharpe: {cell['sharpe']} | OOS months: {cell['oos_months']} | Basis: {cell['selection_basis']}")
