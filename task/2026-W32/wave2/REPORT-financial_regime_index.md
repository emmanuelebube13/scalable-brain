# REPORT-financial_regime_index

> Transcribed verbatim by the orchestrator from the authoring agent's returned text (this
> harness refuses subagent writes to `.md` report files).

**Status: BLOCKED — DEFERRED, not implemented. No strategy module or fixture written.**

**Spec:** `task/2026-W32/fleet/upload/wave2/specs/SPEC-financial_regime_index.md`
**Gap note:** `task/2026-W32/wave0/DATA-GAP-financial_regime_index.md` (recommendation: DEFER)

## Implemented

Nothing. The agent read the run brief, the spec, and the DATA-GAP note in full, then
confirmed against the repo that the data gap is real before writing any code.

## Why it stopped

The spec's own header states an **IMPLEMENTATION BLOCKER**: the strategy's entire signal
(`BFCI`) is computed from **nine external daily series — SPY, ACWI, HYG, LQD, VIX, DXY,
US02Y, US10Y, BIL** — none of which exist anywhere in this database or codebase, and none of
which are obtainable through the existing OANDA FX ingest. Verified independently:

- No `fact_macro_series` table or macro loader exists in `src/`.
- `grep` across `src/layer0/data_access/` for SPY/ACWI/HYG/LQD/DXY/BIL/VIX/US02Y/US10Y
  returns nothing relevant — only doc mentions confirming their *absence*, e.g.
  `DATA_AVAILABILITY.md:59` ("no VIX, no DXY series").
- The DATA-GAP note explicitly recommends **DEFER**, states "there is no meaningful
  reduced-coverage run" (dropping components changes every remaining z-score's inverse-vol
  weighting, so a partial composite would measure a different, uncitable signal), and
  explicitly rejects substituting an FX-derived sentiment proxy (e.g. AUD/JPY) as "silently
  testing a different hypothesis, violating the no-invented-data rule."
- Per §2 of the spec, `context_granularities: ()` — "the 'context' is the external macro
  composite, not an FX timeframe" — so there is no `ctx` DataFrame this strategy could
  legitimately read even via `closed_context_frame`. The composite has no home in
  `contract_v2`'s frame model as currently available.

The only executable residue without the macro data would be the bare SMA200 trend filter on
an FX pair — which is not this strategy, would misrepresent the hypothesis under test, and is
exactly the outcome the DATA-GAP note warns against ("would flatter or damn it by accident").

This matches the run brief's carve-out: *"if the spec relies on data that does not exist in
this repo, stop and report that rather than inventing a proxy."* Inventing a macro-series
stub, hardcoding a fake composite, or substituting an FX proxy would all violate hard rule 5
and the DATA-GAP note's explicit rejection, and would produce a strategy that tests a
fabricated hypothesis rather than the specified one.

## Deviations

None — no code was written, no files created or touched. Neither
`research/financial_regime_index.py` nor its fixture exists. No aborted-run partial exists
for this id either.

## Uncertainties

- Whether the reviewer wants a placeholder file explicitly marked `NotImplemented` for
  tracking. The agent did not create one, since the brief says to deliver exactly the two
  files and touch nothing else, and an unimplementable strategy arguably should not exist as
  a stub in the research registry. **Reviewer's call.**
- The DATA-GAP note also flags that even once the macro ingest lands, the Pine-script
  threshold defaults (+0.50 / +1.00 / 0.00 / −0.50) are **reconstructed, not confirmed** — a
  second gate beyond data availability.

## Fixture rationale

N/A — no fixture, since there is no correct implementation to test against without the
underlying data.

## Verification

Not run; `black`/`mypy`/`pytest` are meaningless against files correctly never created.
No shared file was touched or found newly broken.

**Recommendation:** keep this row DEFERRED per its own DATA-GAP note until the macro ingest
(`fact_macro_series` + FRED/stooq loaders) lands.
