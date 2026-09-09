import argparse
import datetime
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

def load_check(filepath):
    module_name = filepath.stem
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return None

def main():
    parser = argparse.ArgumentParser(description="Scalable-Brain System Audit Runner")
    parser.add_argument("--mode", choices=["full", "sentinel"], default="sentinel", help="Audit mode")
    args = parser.parse_args()

    mode = args.mode
    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d_%H%M")
    
    audit_dir = Path(__file__).parent
    checks_dir = audit_dir / "checks"
    reports_dir = audit_dir.parent.parent / "audit" / "reports" / timestamp_str
    reports_dir.mkdir(parents=True, exist_ok=True)

    findings = []
    summary = {
        "P0": {"pass": 0, "fail": 0, "inconclusive": 0},
        "P1": {"pass": 0, "fail": 0, "inconclusive": 0},
        "P2": {"pass": 0, "fail": 0, "inconclusive": 0},
        "P3": {"pass": 0, "fail": 0, "inconclusive": 0}
    }

    if not checks_dir.exists():
        print(f"No checks directory found at {checks_dir}")
        sys.exit(1)

    check_files = sorted(checks_dir.glob("*.py"))
    
    for check_file in check_files:
        if check_file.name == "__init__.py":
            continue
            
        print(f"Running {check_file.name}...")
        try:
            module = load_check(check_file)
            if hasattr(module, "run"):
                finding = module.run(mode)
                if finding:
                    findings.append(finding)
                    
                    # Update summary
                    sev = finding.get("severity", "P3")
                    status = finding.get("status", "INCONCLUSIVE").lower()
                    
                    if sev in summary and status in summary[sev]:
                        summary[sev][status] += 1
            else:
                print(f"Skipping {check_file.name}: no run(mode) function found.")
        except Exception as e:
            err_trace = traceback.format_exc()
            findings.append({
                "id": check_file.stem,
                "title": f"Failed to execute {check_file.name}",
                "severity": "P0", # Execution failure of a check is critical
                "status": "INCONCLUSIVE",
                "verdict": f"Exception raised during execution: {e}",
                "evidence": {"traceback": err_trace},
                "notes": "Check failed to run."
            })
            summary["P0"]["inconclusive"] += 1

    # Output findings.json
    output_data = {
        "run_id": timestamp_str,
        "mode": mode,
        "started_at": now.isoformat(),
        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "findings": findings,
        "summary": summary
    }

    findings_file = reports_dir / "findings.json"
    with open(findings_file, "w") as f:
        json.dump(output_data, f, indent=2)

    # Output report.md
    report_file = reports_dir / "report.md"
    with open(report_file, "w") as f:
        f.write(f"# Scalable-Brain Audit Report\n\n")
        f.write(f"**Run ID:** {timestamp_str}\n")
        f.write(f"**Mode:** {mode.upper()}\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Severity | PASS | FAIL | INCONCLUSIVE |\n")
        f.write("|---|---|---|---|\n")
        for sev in ["P0", "P1", "P2", "P3"]:
            f.write(f"| **{sev}** | {summary[sev]['pass']} | {summary[sev]['fail']} | {summary[sev]['inconclusive']} |\n")
        f.write("\n")
        
        f.write("## Findings\n\n")
        
        # Sort findings by severity (P0 first, then P1, etc.)
        def sev_score(finding):
            s = finding.get("severity", "P3")
            return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(s, 4)
            
        sorted_findings = sorted(findings, key=sev_score)
        
        for fnd in sorted_findings:
            f.write(f"### [{fnd.get('id', 'N/A')}] {fnd.get('title', 'Unknown')} - {fnd.get('severity', 'UNKNOWN')}\n\n")
            f.write(f"**Status:** {fnd.get('status', 'UNKNOWN')}\n\n")
            f.write(f"**Verdict:** {fnd.get('verdict', '')}\n\n")
            
            if "evidence" in fnd:
                f.write("**Evidence:**\n")
                if isinstance(fnd["evidence"], dict):
                    for k, v in fnd["evidence"].items():
                        f.write(f"- `{k}`: {v}\n")
                else:
                    f.write(f"{fnd['evidence']}\n")
                f.write("\n")
                
            if "notes" in fnd and fnd["notes"]:
                f.write(f"**Notes:** {fnd['notes']}\n\n")
            
            f.write("---\n\n")

    print(f"\nAudit complete. Findings saved to {findings_file}")
    print(f"Report saved to {report_file}")
    
    # Return exit code based on P0/P1 failures
    if summary["P0"]["fail"] > 0 or summary["P0"]["inconclusive"] > 0:
        print("\nCRITICAL: P0 checks failed or were inconclusive.")
        sys.exit(1)
    if summary["P1"]["fail"] > 0:
        print("\nWARNING: P1 checks failed.")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
