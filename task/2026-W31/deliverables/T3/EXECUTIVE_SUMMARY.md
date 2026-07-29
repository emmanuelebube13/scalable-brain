# T3 — Promote the Verified Work · Executive Summary

**2026-07-29 · Nothing has been promoted. Your live model is untouched.**

## What this task found

The safety gate meant to stop a worse model from going live **has never actually worked.**

Every time the system retrains, it is supposed to compare the new model against the one
currently running and refuse to replace it with something worse. That comparison has never
happened. On all three promotions this year — 1 July, 19 July, 26 July — the system looked for
the current live model, failed to find it, shrugged, and promoted anyway.

The cause is mundane and completely silent: the code that decides *where* to look for the live
model reads a configuration file that the retrain process never loads. So instead of checking
the real model in cloud storage, it checked an empty folder on this machine, found nothing,
and treated that as "there's nothing to compare against — go ahead."

**A genuinely worse model could have replaced a good one at any point this year, and nothing
would have objected.** That is now fixed.

## The second problem: a bar that could only ever go up

Separately, the comparison itself was written so that each new model had to be *at least as
good* as the last one — with no allowance for normal measurement noise.

That sounds sensible and is a well-known trap. Because every promotion resets the bar to the
new model's own score, the bar can only climb, never fall. Over time it settles at the luckiest
score ever recorded and then rejects everything — including models that are genuinely better
but happened to measure slightly lower on the day. The bar had already climbed from 0.717 to
0.860 to 0.965 in three promotions.

Fixed: the bar now follows whatever model is *currently live*, with a small tolerance for
noise, so it can move down as well as up. A hard floor still prevents any real decline.

**A note on the brief:** the task described this as "a 0.965 factor". That number is not a
setting anywhere in the code — it is the current live model's score, which had been mistaken
for a threshold. The underlying concern was right; the mechanism was different.

## What a promotion today would actually change: almost nothing

A full evaluation was run on the freshly repaired trade data. All four safety gates pass. But
the candidate is **not an improvement**:

- Accuracy: **identical** to the live model (0.965 vs 0.965).
- Its measured edge is **slightly worse** (0.0377 vs 0.0389).
- The strategy map is **structurally identical** — same four entries, same single strategy,
  nothing gained, nothing dropped.

The one real difference: the live model was built while trade results had been frozen since
23 June. The candidate is the first built on genuinely current data. Same numbers — but
honestly measured.

## My recommendation: don't promote today

It is a close call, and it is your decision.

Promoting buys nothing measurable — identical accuracy, slightly worse edge, identical map —
while adding one more change on the same day two gate defects were repaired.

The stronger option is to let **Sunday's scheduled retrain (2 August)** be the first run where
this safety gate genuinely works, with the new daily heartbeat watching. If that candidate
passes a real comparison, you promote with a track record behind the repaired gate rather than
on the day it was fixed.

**If you'd rather promote now, say "promote"** and I'll run it through the orchestrator and
verify the cloud pointer, the archived previous version, and that the integrity check ran
before the switch.

## Also worth knowing

- **Automatic promotion stays off**, as instructed. Before turning it on I'd want to see the
  repaired gate actually bind on at least one real retrain, three clean weekly runs with the
  heartbeat green, and a deliberate decision about the ~4-point jump in trade approval rate
  that the recalibrated gatekeeper brings — that is real extra volume for your other two
  machines to absorb.
- **The task's premise that "the live model still reflects the pre-fix world" is out of date.**
  The seven verified fixes are already in the live 26 July bundle. What that bundle reflects is
  stale *data*, not stale code.
- **Unchanged and still the real concerns:** your entire live model is one strategy, and the
  High-Volatility regime has no qualifying strategy at all.
