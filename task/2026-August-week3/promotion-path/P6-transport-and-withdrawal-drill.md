# P6 — Transport and the withdrawal drill

**Engineer:** Gemini Pro · **Reviewer:** Claude · **Owner:** provisioning
**Est:** 3–4 h · **Risk:** medium — touches cloud infrastructure and the live pointer.
**Needs:** P5 for the transport half to be meaningful.

---

## Why

Two long-standing gaps that both sit on the critical path the moment there is something to
send.

**Transport.** `QUEUE_PROVIDER=local`. Scored signals land in `results/state/queue/` on
Computer 1, which Systems 2 and 3 cannot read. Three topics need creating:
`Scored_Signal_Queue`, `AMS_Outbound_Queue`, `AMS_Inbound_Queue`.

**Reversibility.** `publish_model_set.py --withdraw` exists (FIX-S1-015) and has **never
been run**. A first promotion should be undoable by one documented command that has been
exercised *before* it is needed in anger, not discovered under pressure.

---

## Hard constraints

1. **GCP provisioning is the owner's action**, not the agent's. Prepare exactly what is
   needed, list the commands, and mark BLOCKED until it exists. Do not create billable
   cloud resources unasked.
2. The queue abstraction already exists (`src/common/queue`). Switch the backend; do not
   write Pub/Sub-specific code into callers.
3. The withdrawal drill runs against a **test pointer prefix first**, never the live
   model-set pointer on its first execution.
4. Every publish keeps the ordering: upload → verify → flip. Superseded pointer archived.

---

## Execution plan

### Step 1 — Document what provisioning needs

Topics, subscriptions, IAM roles, and which service account needs what. Write it as
commands the owner can paste. Mark BLOCKED in `STATE.md` with exactly that list.

### Step 2 — Verify the abstraction is really backend-agnostic

Before provisioning, prove the switch is a config change: run the producer's tests against
a Pub/Sub emulator or a fake, and confirm no caller imports anything Pub/Sub-specific.
If a caller does, fix that first — that is the actual work here.

### Step 3 — The withdrawal drill

1. Publish a throwaway model set to a **test prefix**.
2. Run `--withdraw --reason "drill"` against it.
3. Verify: manifest `status="withdrawn"`, `artifacts` empty, reason recorded, superseded
   manifest archived to `previous_model_set.json`, nothing deleted.
4. Reinstate by publishing again — proving withdrawal is reversible.
5. Time it. Write the elapsed time into the runbook; under pressure people need to know
   whether this takes 30 seconds or 10 minutes.

### Step 4 — Write the runbook

`docs/runbooks/WITHDRAW_A_MODEL_SET.md` — the exact command, what it does, what it does not
do (it never deletes), how to verify it worked, how to reinstate, and how long it takes.

### Step 5 — Switch transport, once provisioned

Only after the owner confirms the topics exist. Then re-run P5 step 7's end-to-end
rehearsal against the real transport and show a message arriving.

---

## Definition of done

- [ ] Provisioning requirements written as paste-ready commands; BLOCKED recorded
- [ ] Backend-agnosticism proven, not assumed
- [ ] Withdrawal drill executed against a test prefix and timed
- [ ] Runbook written
- [ ] Transport switched only after owner provisioning, with a message shown arriving

## Reviewer will check

- That no cloud resource was created without the owner asking.
- That the drill ran somewhere other than the live pointer.
- That `--withdraw` provably deletes nothing.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
