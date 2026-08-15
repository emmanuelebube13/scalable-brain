# T3 — Promote the Verified Work · Executive Summary

**2026-07-29 · You signed off. Bundle `2026-07-29T11-46-42Z-55dacdbf` is now live.**

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

## What happened

I recommended waiting for Sunday's scheduled retrain, on the grounds that the candidate was not
an improvement. You chose to promote, and it went through the orchestrator — the only path
allowed to touch the live model.

**This is the first promotion in the project's history where that safety gate actually
compared anything.** The new model was measured against the live one (0.965 against a required
0.931) and passed on the merits rather than by default.

The live model is now `2026-07-29T11-46-42Z-55dacdbf`, built on genuinely current trade data for the first time since
June.

## Two things you should know

**1. Your other two machines may still be on the old model.** There are two pointers. The one
naming the System-1 model was updated; the one that pairs the model with its gatekeeper — the
"model set" — was **not**, because it sits behind a separate deliberate switch for staged
rollout. If Systems 2 and 3 read the model set, they are still running the 26 July version and
this promotion has not reached them.

Publishing it is one command and a rollout decision, not an automatic consequence of today's
sign-off, so I did not run it. **Tell me if you want it published.**

**2. There is no rollback pointer, and there never was.** The documentation says the superseded
version is archived to `previous.json` so you can roll back in one step. **No code implements
that.** The file does not exist and did not exist before today either. Rolling back means
manually re-pointing to `2026-07-26T00-27-51Z-b48f48d3`, which is still safely stored — so
recovery is possible, just not one-click. Worth fixing.

**One honest note on the numbers:** the promoted model's recorded edge came out at 0.0365
versus the old model's 0.0389 — about 6% lower. That measurement varies between runs, and the
safety gate only compares accuracy, so nothing flagged it. It is not alarming, but it is real,
and it is the kind of thing a bundle-level edge check should be catching.

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
