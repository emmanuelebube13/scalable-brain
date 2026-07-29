# T5 — De-risk the Money Layer · Executive Summary

**2026-07-29 · Nothing was applied to any live system. This is a hand-off package.**

## The headline you should read first

While working through the System-3 evidence, one fact overtook everything else this task was
meant to do:

> **The live account has taken 10 trades. All ten lost.** Profit factor 0.0, average
> −367 CAD per trade, lifetime −15,935 CAD.

And the reason it stopped losing is an accident: a safety gate jammed shut in a way nobody
intended. **That jammed gate is currently the only thing preventing further loss.**

The report that documented this said it plainly, and I agree: *fixing the gates without first
answering why every trade loses would convert a stalled system into a reliably losing one.*

Everything below is written to respect that.

## What was actually wrong with the money layer

**Two bugs in how position sizes are calculated** — both confirmed, both in code still sitting
in this repository.

**1. The risk cap was computed in the wrong currency.** Your "risk at most 2% per trade" rule
was applied in the currency the *instrument* is quoted in, not the currency your *account* is
denominated in. For three of five pairs that happens to be the same thing, so it looked fine.
For the others it was badly wrong:

| Pair | Intended risk | Actual risk | |
|---|---:|---:|---|
| EUR_USD | 200 | 200.00 | correct by coincidence |
| USD_JPY | 200 | **1.33** | 150× too small |
| USD_CAD | 200 | 147.06 | 26% too small |
| a GBP-quoted cross | 200 | **254.00** | **27% OVER your hard limit** |

That last row is the one that matters: this is not only a "positions too small" bug. On some
pairs it **breaks the hard risk cap** — the specific protection that is supposed to be
unbreakable.

And this already happened to you. For three days in July, sizing ran as though your account
were in **USD** when it is in **CAD**. It was corrected by an incidental restart, not by any
alarm. Nothing checks that the sizing currency matches what your broker says the account is.

**2. Your "maximum 25% portfolio exposure" limit does not measure exposure.** It counts open
positions. `len(positions) >= 0.25 × 10` — it rejects the third position, regardless of size.
A book holding $1,100 and a book holding $110,000 both report the same "0.2" exposure. Two
maximum-size positions would be 2,200% of your equity, and the rule approves them.

## What is now ready for you

A complete package at `task/2026-W31/T5-fix-package/`:

- **Corrected arithmetic**, proven by **23 tests** covering a USD pair, a yen pair, a
  Canadian-dollar pair and a cross — with every expected number worked out by hand.
- **Proof the old code fails**: six risk invariants fail against the unpatched formulas, with
  the output captured.
- **`APPLY.md`** — exact changes, rollback commands, and the order to do them in.
- **`HANDOFF.md`** — a paste-ready session for your Computer-3 machine, including how to spot
  at a glance whether the fix actually took effect (*if a yen position is sized in the
  hundreds of units, it didn't*).

## What is blocked, and it matters

**The code that sizes your real-money positions still exists only on the VM, with no copy in
version control.** This machine cannot reach that VM — no SSH config, and the cloud account it
holds is a storage-only identity with no compute access.

**If that machine is lost, the code that decides how much money to put at risk is lost with
it.** Unblocking this takes under five minutes on the VM; the exact command is in
`DELIVERABLE.md` §1. I'd do that before anything else here.

## What I recommend, in order

1. **Add the currency check** — assert sizing currency equals the broker's account currency.
   Five minutes, and it closes the hole that hid a serious bug for three days.
2. **Apply the risk-cap fix.** Ready and tested.
3. **Make the position list real** before touching the exposure limit — the corrected exposure
   maths still reads zero if the system can't see its own positions, which today it can't.
4. **Then** the exposure fix.
5. **Do not unblock the jammed gate in the same session.** That is a decision about the
   strategy, not a bug to be patched.

## The uncomfortable part

These fixes make your position sizing **correct**. They do not make the strategy
**profitable** — and correct sizing of a losing strategy loses money *faster*, because the
under-sized yen positions were, by accident, limiting the damage.

That connects directly to what System 1 has been saying all week: the entire live model is one
strategy, and the regime classification that is supposed to select strategies doesn't actually
discriminate between them. The live results — ten trades, ten losses — are the empirical
version of the same problem.

**Fix the sizing because wrong is wrong. But the question worth your attention is why the
strategy loses, not why the gate is stuck.**
