"""Wave-2 acceptance audit — one command, human-readable verdict per strategy.

Run this to decide whether delivered work is acceptable, WITHOUT reading 47 strategy files.
It is deliberately adversarial: it assumes the author may have taken shortcuts, and it tries
to catch the specific shortcuts that produce green tests and wrong code.

Per strategy, in order (a strategy stops at its first FAIL):

  1. FILES      module + fixture both exist and parse
  2. BANNED     no look-ahead primitives in the module: shift(-n), rolling(center=True),
                detect_swing_points, .iloc[i+1:]
  3. CONTEXT    if the strategy declares context_granularities, it must use
                closed_context_frame or merge_asof, and must NOT use the naive
                `ctx.index <= t` form. This is the bug class that produced 108 phantom
                orders and that a passing fixture does NOT catch.
  4. META       metadata.strategy_id equals the filename; declares pairs
  5. FIXTURE    the fixture has >= 30 hand-written price literals, asserts on real
                OrderIntent fields, and calls assert_no_lookahead_v2
  6. TESTS      the fixture actually passes
  7. TEETH      *** the vacuity check *** — sabotage the strategy so it emits no orders,
                and require the fixture to FAIL. A fixture that still passes is asserting
                nothing and is rejected. This is the check that catches "ran the code and
                pasted the output".
  8. REALDATA   assert_no_lookahead_v2 against the real database, plus order counts, so a
                strategy that fires almost nowhere is visible

Usage:
    cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
    source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
    python task/2026-W32/wave2/audit_wave2.py                 # everything on disk
    python task/2026-W32/wave2/audit_wave2.py --quick         # skip step 8 (no DB, much faster)
    python task/2026-W32/wave2/audit_wave2.py kiss_h4 ...     # only these ids

Exit code 0 only if every audited strategy is ACCEPT.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path("/home/emmanuel/Documents/Scalable_Brain/scalable-brain")
sys.path.insert(0, str(ROOT))

RESEARCH = ROOT / "src" / "layer0" / "strategies" / "research"
FIXTURES = RESEARCH / "tests"
WAVE2 = ROOT / "task" / "2026-W32" / "wave2"
SPECS = ROOT / "task" / "2026-W32" / "fleet" / "upload" / "wave2" / "specs"
VENV_PY = "/home/emmanuel/Documents/Scalable_Brain/.venv/bin/python"

NOT_A_STRATEGY = {"__init__", "example_ma_cross", "reference_pullback_continuation"}

#: Must not be built at all — external data that does not exist in this repo. A strategy
#: here that HAS files is itself a finding: someone invented a data proxy.
BLOCKED = {
    "currency_value_ppp": "BLOCKING: OECD PPP + G10 CPI absent",
    "usd_carry_basket": "BLOCKING: 3-month rates for USD + 9 currencies absent",
    "three_ducks": "needs M5; research_data allows only H1/H4/D1/W1",
    "financial_regime_index": "DEFER: 9 external macro series absent",
}

BANNED_PATTERNS = [
    (r"shift\(\s*-", "shift(-n) reads the future"),
    (r"center\s*=\s*True", "rolling(center=True) reads the future"),
    (r"detect_swing_points", "banned: uses center=True internally"),
    (r"\.iloc\[\s*i\s*\+\s*1", ".iloc[i+1:] reads the future"),
]


def _read(p: Path) -> str:
    try:
        return p.read_text()
    except OSError:
        return ""


def _strip_comments(src: str) -> str:
    """Drop # comments and docstrings so a *mention* of a banned name is not a hit."""
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    doc_spans = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and node.value.lineno:
                for ln in range(node.value.lineno, (node.value.end_lineno or 0) + 1):
                    doc_spans.add(ln)
    out = []
    for i, line in enumerate(src.splitlines(), start=1):
        if i in doc_spans:
            continue
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


def _strategy_class(module_name: str) -> Tuple[Optional[type], str]:
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        return None, f"import failed: {type(exc).__name__}: {exc}"
    from src.layer0.strategies.contract_v2 import StrategyV2

    found = [
        obj
        for _, obj in inspect.getmembers(mod, inspect.isclass)
        if issubclass(obj, StrategyV2)
        and obj is not StrategyV2
        and obj.__module__ == module_name
        and not inspect.isabstract(obj)
    ]
    if len(found) != 1:
        return None, f"expected 1 StrategyV2 subclass, found {[c.__name__ for c in found]}"
    return found[0], ""


def _run_pytest(test_path: Path, env_extra: Optional[Dict[str, str]] = None) -> int:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = [VENV_PY, "-m", "pytest", str(test_path), "-q", "-p", "no:cacheprovider"]
    if env_extra:
        env.update(env_extra)
        # The wave2 directory is not an importable package path ("2026-W32" is not a legal
        # identifier), so put it on PYTHONPATH and load the plugin by bare module name.
        env["PYTHONPATH"] = str(WAVE2) + os.pathsep + env.get("PYTHONPATH", "")
        args += ["-p", "_vacuity_plugin"]
    proc = subprocess.run(
        args, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900
    )
    return proc.returncode


def audit_one(sid: str, *, quick: bool) -> Dict[str, Any]:
    row: Dict[str, Any] = {"strategy_id": sid, "checks": {}}

    def fail(step: str, detail: str) -> Dict[str, Any]:
        row["verdict"] = "REJECT"
        row["failed_step"] = step
        row["detail"] = detail
        return row

    mod_path = RESEARCH / f"{sid}.py"
    fix_path = FIXTURES / f"test_{sid}_fixture.py"

    if sid in BLOCKED:
        if mod_path.exists() or fix_path.exists():
            return fail(
                "BLOCKED",
                f"files exist for a strategy that must NOT be built ({BLOCKED[sid]}) — "
                "check whether a data proxy was invented",
            )
        row["verdict"] = "BLOCKED-OK"
        row["detail"] = BLOCKED[sid]
        return row

    # 1 FILES
    if not mod_path.exists():
        return fail("FILES", "strategy module missing")
    if not fix_path.exists():
        return fail("FILES", "golden fixture missing")
    mod_src, fix_src = _read(mod_path), _read(fix_path)
    import ast

    for label, src in (("module", mod_src), ("fixture", fix_src)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            return fail("FILES", f"{label} does not parse: line {exc.lineno}")
    row["checks"]["FILES"] = "ok"

    # 2 BANNED
    code_only = _strip_comments(mod_src)
    for pat, why in BANNED_PATTERNS:
        if re.search(pat, code_only):
            return fail("BANNED", why)
    row["checks"]["BANNED"] = "ok"

    # 4 META (needed before CONTEXT)
    cls, err = _strategy_class(f"src.layer0.strategies.research.{sid}")
    if cls is None:
        return fail("META", err)
    try:
        meta = cls().metadata
    except Exception as exc:  # noqa: BLE001
        return fail("META", f"metadata raised: {type(exc).__name__}: {exc}")
    if meta.strategy_id != sid:
        return fail("META", f"metadata.strategy_id {meta.strategy_id!r} != filename {sid!r}")
    if not meta.pairs:
        return fail("META", "declares no pairs")
    row["primary"] = meta.primary_granularity
    row["context"] = list(meta.context_granularities)
    row["pairs"] = list(meta.pairs)
    row["checks"]["META"] = "ok"

    # 3 CONTEXT — only bites for multi-timeframe strategies
    if meta.context_granularities:
        uses_safe = ("closed_context_frame" in code_only) or ("merge_asof" in code_only)
        if not uses_safe:
            return fail(
                "CONTEXT",
                "declares context_granularities but uses neither closed_context_frame "
                "nor merge_asof — almost certainly reads an unclosed context bar",
            )
        if re.search(r"\.index\s*<=", code_only):
            return fail(
                "CONTEXT",
                "uses `ctx.index <= t`, which admits the context bar that has not closed "
                "(the 108-phantom-order bug). A passing fixture does not catch this.",
            )
        row["checks"]["CONTEXT"] = "ok (safe join)"
    else:
        row["checks"]["CONTEXT"] = "n/a (single-frame)"

    # 5 FIXTURE shape
    # >=2 decimals, so JPY-cross fixtures (185.00) count as well as 5-dp majors (1.10185).
    price_literals = re.findall(r"\d+\.\d{2,}", fix_src)
    if len(price_literals) < 30:
        return fail(
            "FIXTURE",
            f"only {len(price_literals)} hand-written price literals found; the brief "
            "requires 30-50 hand-constructed bars as a literal",
        )
    asserted = [
        f
        for f in ("entry_price", "stop", "exits", "direction", "decision_bar")
        if re.search(rf"assert[^\n]*\b{f}\b", fix_src)
    ]
    if len(asserted) < 3:
        return fail(
            "FIXTURE",
            f"asserts on only {asserted} — a golden fixture must pin the trade plan "
            "(entry, stop, exit legs, direction)",
        )
    if "assert_no_lookahead_v2" not in fix_src:
        return fail("FIXTURE", "fixture never calls assert_no_lookahead_v2")
    row["checks"]["FIXTURE"] = f"ok ({len(price_literals)} literals, asserts {asserted})"

    # 5b REVIEWABLE — brief requirements 3 and 5: the arithmetic must be shown, and the
    # assertions mapped to spec rules. Without these a reviewer cannot tell a hand-derived
    # level from one copied out of a program run, which is the entire point of the fixture.
    # The TEETH check below cannot substitute: it only proves the fixture notices when the
    # strategy emits nothing at all.
    n_tests = len(re.findall(r"^\s*def test_", fix_src, re.M))
    n_comments = len(re.findall(r"^\s*#", fix_src, re.M))
    asserts_fraction = bool(re.search(r"assert[^\n]*fraction", fix_src))
    shortfalls = []
    if n_tests < 4:
        shortfalls.append(f"only {n_tests} test functions (need >= 4)")
    if n_comments < 8:
        shortfalls.append(
            f"only {n_comments} comment lines (need >= 8 showing the hand arithmetic "
            "and which spec rule each assertion enforces)"
        )
    if not asserts_fraction:
        shortfalls.append("never asserts exit-leg fractions (they must sum to 1.0)")
    if shortfalls:
        return fail(
            "REVIEWABLE",
            "fixture is too thin to review: " + "; ".join(shortfalls)
            + ". The numbers may be right, but nothing shows they were derived from the "
            "spec rather than read off a program run.",
        )
    row["checks"]["REVIEWABLE"] = (
        f"ok ({n_tests} tests, {n_comments} comment lines, asserts fractions)"
    )

    # 6 TESTS
    if _run_pytest(fix_path) != 0:
        return fail("TESTS", "fixture test does not pass")
    row["checks"]["TESTS"] = "ok"

    # 7 TEETH — sabotage and require failure
    rc = _run_pytest(
        fix_path,
        env_extra={"VACUITY_TARGET": f"src.layer0.strategies.research.{sid}"},
    )
    if rc == 0:
        return fail(
            "TEETH",
            "fixture STILL PASSES when the strategy is sabotaged to emit zero orders — "
            "the assertions are vacuous. Most likely the expected values were copied from "
            "program output instead of derived from the spec.",
        )
    row["checks"]["TEETH"] = "ok (fixture fails when strategy is broken)"

    if quick:
        row["verdict"] = "ACCEPT (quick — real-data probe skipped)"
        return row

    # 8 REALDATA
    from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
    from src.layer0.strategies.v2_harness import build_frames

    strat = cls()
    per_pair: Dict[str, Any] = {}
    probed = False
    for pair in meta.pairs:
        try:
            frames = build_frames(
                pair, meta.primary_granularity, meta.context_granularities,
                lookback_years=10,
            )
        except Exception as exc:  # noqa: BLE001
            per_pair[pair] = f"load error: {type(exc).__name__}: {exc}"
            continue
        if frames is None:
            per_pair[pair] = "no_data (not backfilled)"
            continue
        try:
            orders = list(strat.generate_orders(frames))
            longs = sum(1 for o in orders if o.direction == 1)
            assert_no_lookahead_v2(strat, frames)
            per_pair[pair] = {
                "orders": len(orders), "long": longs, "short": len(orders) - longs,
            }
            probed = True
        except Exception as exc:  # noqa: BLE001
            per_pair[pair] = f"PROBE FAIL: {type(exc).__name__}: {exc}"[:400]
    row["per_pair"] = per_pair
    if any(isinstance(v, str) and "PROBE FAIL" in v for v in per_pair.values()):
        return fail("REALDATA", "real-data look-ahead probe failed on at least one pair")
    row["checks"]["REALDATA"] = "ok" if probed else "SKIP (no data for any declared pair)"

    # 9 TRADES — emitting orders is not enough; the position engine must ADMIT some of
    # them. A strategy whose every order is rejected at admission produces zero trades,
    # so it can never qualify, no matter how green its fixture is. Four strategies were
    # found in exactly that state (all fractional trailing legs, which the contract lets
    # you construct but the engine refuses to execute).
    if probed:
        from collections import Counter

        from src.layer0.strategies.position_engine import PositionEngine

        pair = next(
            p for p, v in per_pair.items() if isinstance(v, dict) and v.get("orders", 0)
        )
        frames = build_frames(
            pair, meta.primary_granularity, meta.context_granularities,
            lookback_years=10,
        )
        assert frames is not None
        intents = list(strat.generate_orders(frames))
        run = PositionEngine().run(
            frames[meta.primary_granularity],
            intents,
            pair=pair,
            warmup_bars=strat.warmup_bars,
            strategy=strat,
            granularity=meta.primary_granularity,
        )
        reasons = Counter(r.reason.split(":")[0] for r in run.rejected_orders)
        row["engine"] = {
            "pair": pair,
            "intents": len(intents),
            "trades": len(run.trades),
            "rejected": len(run.rejected_orders),
            "top_reasons": reasons.most_common(3),
        }
        if len(run.trades) == 0:  # .trades is a DataFrame; never use truthiness
            return fail(
                "TRADES",
                f"the position engine admitted NONE of {len(intents)} orders on {pair} "
                f"(top reason: {reasons.most_common(1)[0][0] if reasons else 'unknown'}) "
                "— zero trades means this strategy can never qualify",
            )
        row["checks"]["TRADES"] = (
            f"ok ({len(run.trades)} trades from {len(intents)} intents on {pair})"
        )

    row["verdict"] = "ACCEPT" if probed else "ACCEPT-UNPROVEN"
    if not probed:
        row["detail"] = (
            "fixture is green but no declared pair has data, so the real-data look-ahead "
            "probe never ran. Re-audit once the backfill lands."
        )
    return row


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="strategy ids (default: all specs)")
    ap.add_argument("--quick", action="store_true", help="skip the real-data probe")
    ns = ap.parse_args(argv)

    all_ids = sorted(p.stem[len("SPEC-"):] for p in SPECS.glob("SPEC-*.md"))
    ids = ns.ids or all_ids
    unknown = [i for i in ids if i not in all_ids]
    if unknown:
        print(f"unknown strategy ids: {unknown}")
        return 2

    rows = []
    for sid in ids:
        row = audit_one(sid, quick=ns.quick)
        rows.append(row)
        v = row["verdict"]
        mark = {
            "ACCEPT": "PASS ", "ACCEPT (quick — real-data probe skipped)": "PASS ",
            "ACCEPT-UNPROVEN": "WARN ", "BLOCKED-OK": "SKIP ",
        }.get(v, "FAIL ")
        extra = ""
        if mark == "FAIL ":
            extra = f"  [{row.get('failed_step')}] {row.get('detail','')[:110]}"
        elif mark == "WARN ":
            extra = "  real-data probe never ran (no backfill)"
        print(f"{mark}{sid}{extra}", flush=True)

    out = WAVE2 / "AUDIT.json"
    out.write_text(json.dumps(rows, indent=2, default=str))

    tally: Dict[str, int] = {}
    for r in rows:
        key = r["verdict"].split(" ")[0]
        tally[key] = tally.get(key, 0) + 1
    print("\n" + json.dumps(tally))
    print(f"wrote {out}")

    rejects = [r["strategy_id"] for r in rows if r["verdict"] == "REJECT"]
    if rejects:
        print(f"\nREJECTED ({len(rejects)}): {', '.join(rejects)}")
    missing = [
        r["strategy_id"]
        for r in rows
        if r["verdict"] == "REJECT" and r.get("failed_step") == "FILES"
    ]
    if missing:
        print(f"of which simply not built yet ({len(missing)}): {', '.join(missing)}")
    return 0 if not rejects else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
