# VISION — what Scalable Brain is for

**Written:** 2026-09-13 · **Supersedes** the first revision of this file, same day, which made
verifiability the goal. That was wrong: verification is how we avoid fooling ourselves, not the
reason we built anything. The reason is capital.

**Owner decisions of 2026-09-13 encoded below:** first target **~$100k in cumulative profit** —
not account value, not capital deposited · starting capital $100, for testing only; deposits
decided later on evidence · risk uncapped in demo, caps introduced tier by tier on owner
sign-off · **evidence chain closes before live capital.**

**Register:** forward-looking. No current-state numbers — those live in
`docs/critical/REPO_STATE.md` and `SYSTEM1_METRICS_AND_TARGETS.md`, and change faster than
prose can track.

---

## 1. The vision, in one line

> **Compound a small account into real capital, at a rate we choose deliberately, without ever
> fooling ourselves about whether it's working.**

Both halves are load-bearing and the order matters. The first half is the purpose: this is a
wealth-accumulation machine, and every design decision must eventually answer to a return
figure. The second half is the only reason the first is achievable — an edge you believe in
because you never tested it honestly is worth less than no edge, since it spends real money
before it disappoints you.

Not "a system that proves it shouldn't trade." Not "a system that trades whatever it's handed."
**A compounder that refuses to lie to itself.**

---

## 2. The name

`Scalable Brain` was never documented. It should be, because the name encodes the strategy.

**Brain** — the product is *insight*, not orders. This machine's output is a judgement about
what to trade, how, and when, expressed as a versioned artifact. Execution is a hand; risk is a
guardian; the thinking happens here.

**Scalable** — in two independent senses, and the vision needs both:

1. **Scalable in insight.** The system's capacity to find, test and add new sources of edge
   grows over time. A new strategy family, a new instrument, a new regime taxonomy, a new
   feature class — each should be cheaper to evaluate than the last, because the evaluation
   machinery is shared and reusable. A system that can only hold the strategies it was born
   with is a program, not a brain.
2. **Scalable in capital.** The same logic must work at $100 and at $100k without being
   rewritten. What changes with account size is *sizing and risk bindings*, never the strategy
   logic or the standard of evidence. If a decision has to be re-derived when the account grows,
   the architecture leaked.

The three-system split serves the second sense. The research path and the shared vetting
machinery serve the first. **Anything that makes it harder to add a new source of insight, or
that hard-codes a decision to the current account size, is a regression against the name.**

---

## 3. The mandate: strategic capital growth

The purpose is **wealth accumulation — capital increase, strategically and quickly, without
courting ruin.** That ordering is deliberate: growth is the objective, and ruin-avoidance is the
constraint that keeps the objective reachable. Not the reverse.

This corrects a real conflict. The repo's stated first principle was "preservation over
profit," which is a coherent belief for an endowment and an incoherent one for a system that has
yet to earn its first dollar. Preservation is a strategy you apply to capital you already have.
We are building capital we do not have yet. Applied at this stage, "preservation" doesn't protect
anything — it guarantees the system never produces a return worth funding, which is the one
outcome that makes the whole project pointless.

**Restated so it holds at every size:**

> **Never lose the ability to keep playing.**

Ruin-avoidance, not loss-avoidance. This is a single belief whose *bindings* change with
capital, which is why it doesn't split the system's identity:

- At **$100**, almost nothing is off-limits. The account is tuition. Losing it costs a hundred
  dollars and buys knowledge that cannot be obtained any other way.
- At **$10k**, a catastrophic drawdown costs a year of contributions. Some things become
  off-limits.
- At **$100k**, a 60% drawdown costs years you will not get back, and the arithmetic of
  recovery turns hostile. Most things become off-limits.

One belief. Different bindings. **And the bindings only ever tighten as capital grows — never
loosen.**

Worth stating because it's routinely misread: **Kelly is a growth criterion.** It maximises
long-run log wealth; it is not a preservation device. Quarter-Kelly is a *chosen fraction*, not
a law of the system, and where that fraction sits is an owner decision tied to capital and
evidence strength. Treating it as immovable was a mistake inherited from documents written for
an account that doesn't exist yet.

---

## 4. The one distinction that resolves the conflict

The "tight grip" that has kept this system from trading is actually **two different mechanisms
that were being argued about as if they were one.** Separating them is the core of this
document.

| | **Evidence gates** | **Risk caps** |
|---|---|---|
| **What they answer** | Does this strategy have an edge? | How much do we bet on it? |
| **Examples** | PF, Sharpe, MaxDD, win rate, OOS length, look-ahead probes, walk-forward folds, map provenance | Kelly fraction, per-trade risk %, drawdown circuit breaker, exposure caps, deployment stage |
| **Do they scale with capital?** | **Never.** Truth is not a function of account size | **Always.** They are entirely a function of account size and evidence strength |
| **Do they loosen?** | **Never, for any reason.** If nothing qualifies, that is the finding | **Yes — that is their job.** Loose when small, tightening as capital grows |
| **Who moves them** | Nobody. They move only when the *measurement* is shown to be wrong | The owner, explicitly, per tier, in writing |

**Evidence gates never loosen. Risk caps scale.** Every future argument about "are we being too
careful" should first establish which of these two it is about. Almost always it is the second,
and the second is legitimately adjustable.

The reason evidence gates are absolute is not caution, it's economics: a strategy with negative
expectancy loses money *faster* when you bet more on it. Loosening evidence to unlock growth is
the one move that reliably produces the opposite of growth. The live record so far — every
realised trade a loser — was produced by a map that is mostly owner override rather than
measured qualification. That is the cost of this mistake, already paid once.

---

## 5. The risk ladder — tiers entered by signature

Per the owner decision of 2026-09-13: **risk is uncapped in demo. Every live tier is entered by
explicit owner sign-off, and the tier's cap is named in that sign-off.** Caps are not applied
automatically and not applied in advance.

| Tier | Capital | Risk posture | Entered by |
|---|---|---|---|
| **Demo** | $0 real | **No caps.** Maximum aggression, maximum learning. Break it deliberately. Find out what the strategy does in its worst regime at sizes you would never risk live | Default state — no sign-off needed |
| **Proving** | ~$100 | Deliberately generous. The account is tuition; the objective is a working loop, not preservation | Owner sign-off, cap named at entry |
| **Compounding** | post-funding | Set at entry, on evidence. Tightens from the Proving posture | Owner sign-off, cap named at entry |
| **Protecting** | approaching target | Materially tighter. Recovery arithmetic now dominates | Owner sign-off, cap named at entry |

Two rules that make this safe without making it timid:

1. **A tier is never entered silently.** No automation promotes capital to the next tier. The
   owner signs, and the signature names the cap, the date and the evidence relied on.
2. **Demo is not a lesser version of live — it is a different instrument.** Its job is to
   produce the knowledge that live trading is too expensive to buy. Uncapped demo is not
   recklessness; refusing to push demo to destruction is the waste.

---

## 6. The target is profit — and the three quantities that must never be confused

This section replaces an earlier revision that used **account value** as the target. That was
wrong, and wrong in a way that would have let the project declare victory having achieved
nothing: an account holding $100k after $100k of deposits has produced no profit, and a target
expressed as account value cannot tell the difference.

**Three quantities, three different meanings:**

| Quantity | What it measures | Whose job | Can it be faked? |
|---|---|---|---|
| **Capital deployed** — cumulative deposits | Nothing about the system. This money could have sat in a savings account. Reaching a large number here is an achievement of *saving*, not of trading | The owner's | Trivially — just deposit |
| **Return rate, deposit-neutral** | Whether the system works. **This is the system's signature**, and it is fully provable at $100 | The system's | No. This is the honest number |
| **Cumulative profit** — value net of every deposit and withdrawal | The wealth outcome. rate × capital × time | Both | Partly — enough capital at a mediocre rate still accumulates profit |

**The target is $100k of cumulative profit, earned at a rate the system demonstrated before the
capital was committed.** Both halves are required. Profit alone can be bought with capital;
a rate alone buys nothing. The rate is proven in Phase 1, the capital is committed in Phase 2,
and the profit accumulates in Phase 3 — in that order, which is what stops the target from being
gameable.

### What it actually takes

Months to **$100k cumulative profit**, at a sustained 30%/yr deposit-neutral return, from a $100
start:

| Monthly deposit | Time to $100k profit | Capital deployed by then | Profit per $ deposited |
|---|---|---|---|
| $500 | ~7.6 years | ~$46k | 2.2× |
| $2,000 | ~4.6 years | ~$110k | 0.9× |
| $5,000 | ~3.1 years | ~$190k | 0.5× |

Three conclusions:

1. **This is a three-to-five-year target at serious deposit rates, not a multi-decade one.** The
   earlier revision's "~26 years" answered a different question — how long $100 takes to *become*
   $100,000 in account value with no deposits ever, which is 1,000× on the stake. Correct
   arithmetic, irrelevant scenario. Retired.
2. **Deposits buy time; patience buys capital efficiency.** The last column is a real tradeoff,
   not a scoring system. $5k/month reaches the target in three years with the capital doing half
   the work; $500/month takes twice as long and earns $2.20 per dollar deposited. Both are
   legitimate. Choosing deliberately is the point.
3. **$100 proves the rate, and the rate is everything at that size.** $100 at 30%/yr earns $30 a
   year. Judging the proving account by its dollar return is meaningless; judging it by whether
   the realised rate matches the modelled one is the entire purpose.

### The requirement this creates

**Deposits and withdrawals must be recorded as dated events.** An account balance cannot separate
profit from a deposit, so the moment funding begins, an untracked deposit ledger makes the
system's rate — the only number that proves the system works — permanently unmeasurable. Two
things have to be computable at any time:

- **Deposit-neutral return** (time-weighted, chain-linked across deposit events) — judges the
  system.
- **Cumulative profit** (value minus net deposits) — judges the outcome.

This is account state, which is System 3's domain, not System 1's. Obtaining it is a
cross-system request through `docs/comms/` — **not** something to build here. Recorded as a
vision-level dependency so it is not discovered late, at the moment the first real deposit lands
and the measurement silently breaks.

---

## 7. Phases

Sequenced per the owner decision: **the evidence chain closes before live capital.** Dated so
they can expire; a phase that has silently slid is worth knowing about.

### Phase 0 — Evidence (now, through 2026-Q4)

*Nothing is risked. Everything is measured.* No live capital. Demo uncapped and pushed hard.

- At least one strategy clears the evidence gates honestly — leak-free, walk-forward, reported
  per pair × granularity, not only pooled.
- Nothing in the live map that cannot fire in real time; the map's provenance contract holding.
- One signal vocabulary across the three hosts, so a message System 1 emits is one System 3
  accepts.
- The simulation-engine question decided, so vetting qualifies from one measured quantity.
- Regime conditioning either earns its place against honest labels or is removed. Both are
  acceptable; carrying it undecided is not.
- **Exit condition:** a qualified strategy, an emittable signal, and a reproducible expectancy
  figure. Not a date.

### Phase 1 — Proving (~$100, owner sign-off)

*The cheapest possible test of the most expensive assumption: that any of this survives reality.*

- Real money, real fills, deliberately trivial size.
- Measured against the backtest envelope continuously — realised versus modelled r-multiples is
  the only number that can tell us the backtest was honest.
- Parameters frozen for the window. Any change restarts the clock.
- **Exit condition:** live results inside the modelled envelope over a window decided in
  advance. A failure here is a successful phase — it is the finding, bought for $100.

### Phase 2 — The funding decision (owner, on evidence)

*A named gate, not a drift.* The owner decides, in writing, how much capital enters and at what
monthly rate — on the strength of Phase 1's measured rate, not on enthusiasm. This is the
decision that sets the horizon: per §6, the same system reaches the target in three years or
seven depending only on this number.

**Prerequisite:** deposit-event tracking exists and deposit-neutral return is computable. Funding
an account whose rate cannot be measured converts a provable system into an unprovable one.

### Phase 3 — Compounding

*The system becomes the reason for the growth.*

- Qualification spread across several strategies and pairs, so the record is an edge and not a
  concentration.
- Deposit-neutral return holding at or above the rate Phase 1 demonstrated — measured
  continuously, not assumed to persist.
- At least one adverse stretch survived inside the modelled drawdown envelope.
- Risk caps tightening on schedule by signature as capital grows.

### Phase 4 — $100k of profit, proven

*The first destination.* **Cumulative profit, net of every deposit** — not account value, not
capital deployed. Reached at a rate demonstrated before the capital was committed, so the profit
is attributable to the system rather than to the funding.

Not the end — the point at which compounding is demonstrated rather than argued, every later
figure becomes credible, and the conversation about what comes next is worth having. Targets
beyond this are deliberately not set here; they would be guesses made from the wrong rung.

### What would falsify this vision

- Nothing clears honest gates across successive strategy families ⇒ the premise that a
  reachable systematic edge exists at this scale is wrong. Stop; don't widen the search.
- Live expectancy materially below backtest across two independent forward windows ⇒ the
  measurement discipline still leaks somewhere invisible, and no amount of new strategy supply
  fixes it.
- The target requires a return rate the record doesn't support and contributions aren't
  forthcoming ⇒ the target is wrong, and should be restated rather than quietly missed.

---

## 8. Anti-goals — what we will not build

Revised for the growth mandate. The self-deception guards stay absolute; the
preservation-flavoured ones are gone.

**Absolute — these protect the money by protecting the truth:**

- **No evidence gate is ever loosened to admit a strategy.** Not for time pressure, not for a
  thin pipeline, not because nothing else qualifies. If nothing qualifies, that is the finding,
  and the answer is a different strategy family.
- **No re-backtesting to explain a live result.** The live path is the record.
- **No permissive fallback on a defect.** Stale map, mismatched label, missing input ⇒ no
  signals, loudly. A system that trades on broken evidence is worse than one that doesn't trade.
- **No second writer.** One promotion path, one pointer writer, one place labels are computed.
- **No claim without its evidence attached.** Including — especially — claims that the system is
  working.

**Structural — these protect the ability to scale:**

- **No execution, sizing, order routing or account state in System 1.**
- **Nothing new that requires Computer 1 online.** Availability of the factory must never become
  availability of the business.
- **No decision hard-coded to the current account size.** It must work at $100 and $100k.
- **No detector without a consumer.** An alarm nobody acts on is not a control.

**New, from the 2026-09-13 decisions:**

- **No risk cap introduced without owner sign-off**, and none applied in advance of the tier it
  governs. Caps are entered, not inherited.
- **No automatic promotion of capital between tiers.** Ever. The owner signs.
- **No capping of demo.** Demo exists to be pushed to destruction.
- **No target, metric or milestone stated in account value.** Profit, or a deposit-neutral rate,
  or nothing. A balance rises on deposits, and any goal expressible by depositing money is not a
  goal about this system.
- **No funding an account whose rate cannot be measured.** Deposit-event tracking comes before
  the deposit, not after.
- **Do not confuse the proving account with the growth account.** Judging $100 by its dollar
  return is a category error; judging post-funding capital by "it's only tuition" is a much more
  expensive one.

**Retired from the previous revision:** "preservation over profit" as a first principle, and
"no speed as a goal" in its absolute form. Growth rate is now an explicit objective. What
remains true is that this is not a latency business — we will not trade a *check* for a tick,
but we will absolutely trade caution for compounding where the evidence supports it.

---

## 9. How you know it is working

Growth-side and truth-side indicators. Thresholds and failure actions belong in
`SYSTEM1_METRICS_AND_TARGETS.md`.

**Is the system working?** — all deposit-neutral, so none of these can be moved by funding.

| Indicator | Reading it |
|---|---|
| **Expectancy per trade, in R** | The atom. Everything else is this times frequency times size |
| **R per month** | Expectancy × frequency. The growth rate before any sizing or funding decision |
| **Deposit-neutral return (time-weighted)** | The system's signature. The one number a deposit cannot flatter |
| **Realised vs modelled r-multiple distribution** | The only honest answer to "how do I know this isn't curve-fit" |

**Is the wealth accumulating?** — these depend on capital as well as rate, and must never be
read as evidence about the system.

| Indicator | Reading it |
|---|---|
| **Cumulative profit, net of deposits** | The target metric. Account value is *not* a substitute and never will be |
| **Months to $100k profit at the current rate and deposit level** | Recomputed, not assumed. Rising means something is wrong that a growing balance would hide |
| **Profit per dollar deposited** | Whether the system or the savings account is doing the work |

**Is it telling the truth?**

| Indicator | Reading it |
|---|---|
| **Distinct strategies qualified through honest gates** | System 1's headline metric. One number, no caveats |
| **Fraction of map cells qualified rather than designated** | How much of the live map is measured edge versus conviction. A mostly-override map is not evidence |
| **Strategies in the live map vs strategies actually trading** | Catches "the map routes to something that cannot fire" on day one |
| **Look-ahead defects found per quarter** | Should trend to zero. A clean quarter with no probes run is unmeasured, not clean |
| **Time to detect a stalled input** | Measured from the stall, not the first alert |

Three readings that look like progress and are not: **a rising account balance** (it rises on
deposits, and says nothing until profit is separated out), **a green heartbeat with nothing
emitted** (freshness of inputs is not liveness of output), and **a high gatekeeper AUC** (its
target is a win-rate target while the promotion gate is a mean-R gate — a strong score is not an
expected-return result).

---

## 10. How this document is used

```
VISION.md                  why this exists, the mandate, the phases   — revised yearly
  ├── IDENTITY_AND_HABITS.md   who the owner and the agent must be    — revised on conflict
  └── VALUE_MILESTONES.md      the rungs, each with a falsifier       — revised when a rung moves
        └── SYSTEM1_METRICS_AND_TARGETS.md   the instruments          — every retrain
              └── <PERIOD>_GOALS.md          this month's work        — monthly
                    └── task/OPEN.md         what is being done now
```

Three tests when deciding what to work on, in order:

1. **Does it move a rung?** (`VALUE_MILESTONES.md`)
2. **Does it move the growth rate, the contribution rate, or the honesty of the measurement?**
   If none of the three, it is plumbing — finish it, don't polish it.
3. **Does it make the next source of insight cheaper to add, or does it hard-code today's
   account size?** The name is a claim; this is the test of it.

**Revision rule.** This file changes when the destination or the mandate changes — not when the
situation does. If you are updating it to reflect what happened this week, that belongs in
`REPO_STATE.md` or a period-goals file. If a phase above has passed unmet, add a dated note
here rather than sliding the date. A vision that quietly moves its own goalposts is the exact
failure this system exists to make impossible.
