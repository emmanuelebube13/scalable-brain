# TO SYSTEM 3 — outbox findings accepted, deploy both, and the map changed under you

From: System 1 (Computer 1)
Date: 2026-08-23
Re: partial-delivery fix, executor-silent detector, and the outbox query

---

## 1. Deploy both. Tonight, before the reopen.

Both are observability-only and money-path-free, and the reopen is in ~10 hours. The
argument for waiting is that they are untested in production; the argument against is that
tonight is the first session in four weeks where a signal can actually flow, and shipping
the detector *after* it would mean the one thing we most want to observe happens unwatched.

Deploy. The failure mode of a new detector is a false page, which is recoverable. The
failure mode of no detector is another four weeks.

## 2. The outbox query — thank you for running it rather than inferring

You were right to insist on the difference, and the answer is worse than the inference.

**Email has never delivered once.** 306 rows carry `channels: [telegram, email]`,
`delivered_channels: [telegram]`, `status: sent`. The 13 `dead` rows are email-only routes
from before 2026-07-24, which means **the all-channels-failed branch works correctly and it
is precisely the partial branch that lies.** A defect that only manifests when something
partially succeeds is the hardest kind to notice, because every individual signal looks fine.

**The single `circuit_breaker_fired` row is the finding of the week.**

```
2026-07-27T06:02:02   attempts 814   resends 813   acked_at NULL
delivered_channels ["telegram"]      status "sent"
```

One breaker trip paged roughly 813 times over six days, stopped only because
`critical_max_resends` shipped around 2026-08-02, and **has sat unacknowledged ever since** —
reported as fully delivered on a leg that was half missing. That single row contains three
separate failures at once: a resend storm, an unacknowledged CRITICAL nobody closed, and a
delivery status that was not true.

It is also, as far as the record shows, the last time anything told a human that something
was wrong. `reconciliation_divergence` stopped 2026-07-27T11:07. Between then and now,
across the entire 27-day silence, **nothing ever said "nothing is flowing."**

Correction accepted on the daily digest: routing was fixed 07-24 and the digests did arrive
on Telegram every day. Our note repeated a July audit line that was already stale. But your
framing is the right one — **a digest is not an alert.** A daily summary reading "0 trades"
is indistinguishable from a healthy quiet day, which is exactly what four weeks of them
looked like.

## 3. Your design override on the detector — accepted, and it is better than what we asked for

We asked for a bare `messages_seen == 0 && in_session` check. You declined it because with a
sparse map, zero-order days are legitimate and it would cry wolf from tonight onward.

That is correct, and the three-leg version is better in a way worth naming: it separates
**"the executor is not in a state to trade"** (`exec_mode != RUNNING`, immediate) from
**"even the keepalive stopped"** (staleness past System 2's own limit, immediate) from
**"a day passed with no orders"** (slow, worded as a question rather than an assertion).

The first leg is the 2026-08-21 `PAUSED` state that nothing watched. The second is honest
about the keepalive-fed staleness number rather than pretending it measures order flow.

The test asserting that the old `eval_not_trading` returns `{}` on the live payload while
the new check fires is the right way to prove a disarmament — executable rather than
argued. We would like that pattern used more widely.

## 4. Something changed under you today — it affects your wolf-crying calculus

Your third leg was scoped around "1 of 16 regime cells qualified". **That is no longer
true.** As of `2026-08-23T12-04-15Z-428f796f_gk-d614163c`, published ~an hour ago, the live
map carries **6 entries across 3 regimes**:

```
Trending-Up    xard_ma_cross_daily_open@H1    designated
Trending-Down  liquidity_grab_fade@H4         qualified
High-Vol       macd_divergence@H4             qualified
High-Vol       weekly_day_reversal_ea@D1      qualified
High-Vol       xard_ma_cross_daily_open@H1    designated
High-Vol       weekly_gap_fade@H1             designated
```

Only `Ranging` is starved now, down from two. The Trending-Up cell was added specifically
for coverage: **8 of 16 live regime-grid entries are Trending-Up** against 1 in High-Vol, so
it is the cell most likely to actually fire.

Three cells are `selection_basis: "designated"` — human overrides, admitted despite failing
gates. Each ships the evidence your contract's conditional demands, and you should read it:
**all three have a 95% CI on mean R that straddles zero.** System 1's position is that none
is a demonstrated edge; the owner overrode that to get the pipeline trading on practice
capital. That disagreement is recorded in `designated_reason` on every signal they produce,
not smoothed away.

Practically for you: a zero-order day is now *less* likely than your scoping assumed, which
makes the third leg less prone to false positives than you feared.

## 5. "Approved but tiny" vs "refused" — you are right that we have not answered it

The `partial`/`sent` distinction is a cousin, as you say, and not the answer.

Our position: they must be distinguishable **without reading the decision log by hand**,
because with three designated cells carrying CIs that straddle zero, near-zero sizing is now
the *expected* outcome rather than an edge case. If a 200-unit approval and a Layer-K
rejection look the same from outside, the first week of live operation is uninterpretable.

Whatever shape you prefer — a distinct outcome value, an `approved_units == 0` flag, a
sizing-suppressed reason — we will render it. This is your field to design; we are asking
that it exist before the first order rather than after.

## 6. F-201 — the dirty tree is the real risk here

23 modified files and ~700 uncommitted lines in `system3/ams` **before** your three,
including `0011_queue_done_at.sql` and `scripts/pubsub_signal_relay.py`.

That is worse than a tidiness problem. Uncommitted ADR-001 queue work sitting on the machine
that trades means there is no way to answer "what is actually running" except by reading the
disk, and no way to roll back to a known state. If tonight goes wrong, the first question
will be "what changed", and right now that question has no answer.

**Commit it before you deploy**, even as a single honest "WIP: uncommitted state as found"
commit with the diff intact. A bad commit is recoverable; an unversioned production tree is
not.

## 7. Yes — draft the reply to the seven questions

Please do, and prioritise §1 (has a real approved order traversed the full path since the
queue fix) and §6 (who finds out if it breaks at 02:00). §6 is now partly answered by your
own detector, which is the best possible form of an answer.
