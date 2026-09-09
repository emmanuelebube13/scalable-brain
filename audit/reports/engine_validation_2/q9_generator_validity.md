# Q9 generator validity — computed statistics

Every claim below is a computed comparison of the synthetic random-entry
population against the real replayed bank, per engine x granularity.
No 'by construction' arguments.

| engine | granularity | KS entry-hour (D, p) | KS bars-held (D, p) | n_real | n_synth | long share real | long share synth | chi2 p |
|---|---|---|---|---|---|---|---|---|
| backtest_engine_v1 | H1 | D=0.1551, p=0 | D=0.1069, p=2.18e-218 | 22239 | 1426178 | 0.5058 | 0.5005 | 0.118 |
| backtest_engine_v1 | H4 | D=0.0863, p=8.16e-28 | D=0.0443, p=1.21e-07 | 4245 | 1063171 | 0.5213 | 0.4995 | 0.00473 |
| position_engine_v2 | D1 | D=0.0202, p=0.234 | D=0.5017, p=0 | 2623 | 646476 | 0.4663 | 0.4993 | 0.000785 |
| position_engine_v2 | H1 | D=0.1138, p=2.54e-138 | D=0.1442, p=5.23e-222 | 12343 | 1197904 | 0.4957 | 0.5003 | 0.313 |
| position_engine_v2 | H4 | D=0.0946, p=2.92e-87 | D=0.4112, p=0 | 11247 | 1303819 | 0.5222 | 0.5001 | 3.41e-06 |

**Reading it.** A large D with a tiny p means the synthetic entries do NOT
match the real ones on that axis. The random-entry control is deliberately
unmatched on entry timing — that is the whole point of a zero-information
entry — so a failed hour-of-day KS is expected and is reported, not hidden.
The direction share is the one axis the generator does target (a fair coin
against the real bank's near-50/50 split); its chi-square p is the check.
`bars_held` is an OUTCOME, not an input: it differs because the exits differ.
