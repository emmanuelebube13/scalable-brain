# Scalable-Brain Audit Report

**Run ID:** 2026-09-09_0651
**Mode:** SENTINEL

## Summary

| Severity | PASS | FAIL | INCONCLUSIVE |
|---|---|---|---|
| **P0** | 0 | 0 | 4 |
| **P1** | 0 | 0 | 1 |
| **P2** | 0 | 0 | 0 |
| **P3** | 0 | 0 | 0 |

## Findings

### [a1_lookahead] Failed to execute a1_lookahead.py - P0

**Status:** INCONCLUSIVE

**Verdict:** Exception raised during execution: No module named 'src'

**Evidence:**
- `traceback`: Traceback (most recent call last):
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 53, in main
    module = load_check(check_file)
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 15, in load_check
    spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 995, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/checks/a1_lookahead.py", line 10, in <module>
    from src.layer0.data_access.data_loader import load_assets, load_market_prices
ModuleNotFoundError: No module named 'src'


**Notes:** Check failed to run.

---

### [a2_lookahead] Failed to execute a2_lookahead.py - P0

**Status:** INCONCLUSIVE

**Verdict:** Exception raised during execution: No module named 'src'

**Evidence:**
- `traceback`: Traceback (most recent call last):
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 53, in main
    module = load_check(check_file)
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 15, in load_check
    spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 995, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/checks/a2_lookahead.py", line 3, in <module>
    from src.common.db import get_engine
ModuleNotFoundError: No module named 'src'


**Notes:** Check failed to run.

---

### [a4_lookahead] Failed to execute a4_lookahead.py - P0

**Status:** INCONCLUSIVE

**Verdict:** Exception raised during execution: No module named 'src'

**Evidence:**
- `traceback`: Traceback (most recent call last):
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 53, in main
    module = load_check(check_file)
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 15, in load_check
    spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 995, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/checks/a4_lookahead.py", line 3, in <module>
    from src.common.db import get_engine
ModuleNotFoundError: No module named 'src'


**Notes:** Check failed to run.

---

### [d3_null_at_edge] Failed to execute d3_null_at_edge.py - P0

**Status:** INCONCLUSIVE

**Verdict:** Exception raised during execution: No module named 'src'

**Evidence:**
- `traceback`: Traceback (most recent call last):
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/run_audit.py", line 55, in main
    finding = module.run(mode)
              ^^^^^^^^^^^^^^^^
  File "/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src/audit/checks/d3_null_at_edge.py", line 5, in run
    from src.common.db import get_engine
ModuleNotFoundError: No module named 'src'


**Notes:** Check failed to run.

---

### [B1_B2] Cost Model: Price semantics and omitted spread magnitude - P1

**Status:** INCONCLUSIVE

**Verdict:** Failed to compute: No module named 'src'

**Evidence:**

---

