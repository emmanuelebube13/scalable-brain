#!/usr/bin/env bash
# Provision Pub/Sub for System 1 -> System 3 -> System 2.
#
# WHY THIS EXISTS RATHER THAN THE COMMANDS IN STATE.md
# ----------------------------------------------------
# The drafted commands would have created topics the code cannot find. Corrections:
#
#  1. TOPIC NAMES ARE CASE-SENSITIVE. `.env` sets SCORED_SIGNAL_QUEUE=scored_signal_queue
#     and src/common/queue/pubsub.py calls topic_path(project, queue) with that value
#     verbatim. A topic named `Scored_Signal_Queue` would never be published to — the
#     producer would target `scored_signal_queue`, get NOT_FOUND, and the pipeline would
#     look provisioned while carrying nothing.
#  2. THE DEAD-LETTER TOPIC WAS MISSING. `.env` sets DLQ_NAME=scored_signal_dlq and the
#     producer routes invalid/unpublishable messages there. Without the topic, a message
#     that should be quarantined is simply lost.
#  3. THE SERVICE ACCOUNT NAME WAS WRONG. There is no `system1-sa`. The real identity is
#     system1-rw@scalable-brain.iam.gserviceaccount.com (from secrets/system1-rw.json and
#     the active gcloud config).
#  4. PROJECT IS `scalable-brain`, passed explicitly rather than relying on active config.
#
# YOU MUST RUN THIS AS YOURSELF. The machine's active gcloud identity is system1-rw, a
# storage-scoped service account that cannot list, create, or set IAM on Pub/Sub. Verified:
# `gcloud pubsub topics list` returns PERMISSION_DENIED for it.
#
# Usage:
#   bash shell/provision_pubsub.sh --dry-run     # print every command, change nothing
#   bash shell/provision_pubsub.sh               # apply

set -euo pipefail

PROJECT="scalable-brain"
USER_ACCOUNT="emmanuelebubembachu@gmail.com"

# Names taken from .env, NOT from the design docs. CLAUDE.md writes these in TitleCase;
# the code reads the lowercase values. Implementation wins.
SIGNAL_TOPIC="scored_signal_queue"
DLQ_TOPIC="scored_signal_dlq"

# System 3's queues. These names are NOT in this repo's .env — System 3 owns them, so
# confirm them with Computer 3 before relying on them. Names below follow CLAUDE.md.
AMS_OUT_TOPIC="AMS_Outbound_Queue"
AMS_IN_TOPIC="AMS_Inbound_Queue"

# The topology is a CHAIN, not a broadcast (README.md:68):
#
#     S1 --Scored_Signal_Queue--> S3 --AMS_Outbound_Queue--> S2 --AMS_Inbound_Queue--> S3
#
# System 1 publishes scored signals. System 3 subscribes, runs the 10-layer risk gate and
# sizes the order, then publishes an APPROVED, SIZED order. System 2 subscribes to that and
# executes it, then reports fills back to System 3.
#
# System 2 never reads from System 1. Nothing reaches the broker without passing the
# Guardian — that is the "preservation over profit" rule in the README, expressed as IAM.
SYSTEM1_SA="system1-rw@${PROJECT}.iam.gserviceaccount.com"

# Confirmed 2026-08-17 from `gcloud iam service-accounts list`: there is no system2-sa and
# no system3-sa. Systems 2 and 3 run on ONE VM under ONE identity, `trading-vm`.
#
# Consequence worth knowing: because S2 and S3 share an identity, IAM cannot enforce the
# "System 2 never reads System 1's signals directly" boundary — trading-vm needs subscriber
# rights on Scored_Signal_Queue for its System 3 role, and that same credential is what
# System 2 runs under. The separation is real in the code and in the contracts, but it is a
# convention on that VM, not something the cloud enforces. Splitting them into two service
# accounts is the fix if that boundary ever needs to be more than a promise.
TRADING_VM_SA="trading-vm@${PROJECT}.iam.gserviceaccount.com"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

run() {
  if [[ $DRY -eq 1 ]]; then
    echo "  + $*"
  else
    echo "  + $*"
    "$@"
  fi
}

echo "== 0. Authenticate as a human. system1-rw cannot do any of this. =="
echo "  current: $(gcloud config get-value account 2>/dev/null)"
if [[ $DRY -eq 0 ]]; then
  gcloud config set account "$USER_ACCOUNT"
  # If this errors with 'credentials not found', run: gcloud auth login
fi

echo "== 1. Enable the API (no-op if already enabled) =="
run gcloud services enable pubsub.googleapis.com --project="$PROJECT"

echo "== 2. Topics =="
for t in "$SIGNAL_TOPIC" "$DLQ_TOPIC" "$AMS_OUT_TOPIC" "$AMS_IN_TOPIC"; do
  run gcloud pubsub topics create "$t" --project="$PROJECT"
done

echo "== 3. Subscriptions — one per consumer in the chain =="
# S3 consumes scored signals from S1.
run gcloud pubsub subscriptions create "${SIGNAL_TOPIC}_sub" \
    --topic="$SIGNAL_TOPIC" --project="$PROJECT"
# S2 consumes approved orders from S3. MISSING from the original command list — without it
# System 3 publishes approved orders into a topic nobody can read, and the chain dead-ends
# one hop before the broker.
run gcloud pubsub subscriptions create "${AMS_OUT_TOPIC}_sub" \
    --topic="$AMS_OUT_TOPIC" --project="$PROJECT"
# S3 consumes fill confirmations from S2.
run gcloud pubsub subscriptions create "${AMS_IN_TOPIC}_sub" \
    --topic="$AMS_IN_TOPIC" --project="$PROJECT"
# A DLQ nobody reads is a black hole, not a safety net.
run gcloud pubsub subscriptions create "${DLQ_TOPIC}_sub" \
    --topic="$DLQ_TOPIC" --project="$PROJECT"

echo "== 4. IAM — per topic/subscription, never project-wide =="
# --- System 1: publishes scored signals, and quarantines bad ones. Publisher only.
#     It is never granted subscriber rights: S1 does not consume its own output, and
#     "S1 never knows if it's live" is one of the inviolable principles.
run gcloud pubsub topics add-iam-policy-binding "$SIGNAL_TOPIC" \
    --member="serviceAccount:${SYSTEM1_SA}" --role="roles/pubsub.publisher" --project="$PROJECT"
run gcloud pubsub topics add-iam-policy-binding "$DLQ_TOPIC" \
    --member="serviceAccount:${SYSTEM1_SA}" --role="roles/pubsub.publisher" --project="$PROJECT"

# --- trading-vm, acting as System 3: read signals, publish approved orders, read fills.
run gcloud pubsub subscriptions add-iam-policy-binding "${SIGNAL_TOPIC}_sub" \
    --member="serviceAccount:${TRADING_VM_SA}" --role="roles/pubsub.subscriber" --project="$PROJECT"
run gcloud pubsub topics add-iam-policy-binding "$AMS_OUT_TOPIC" \
    --member="serviceAccount:${TRADING_VM_SA}" --role="roles/pubsub.publisher" --project="$PROJECT"
run gcloud pubsub subscriptions add-iam-policy-binding "${AMS_IN_TOPIC}_sub" \
    --member="serviceAccount:${TRADING_VM_SA}" --role="roles/pubsub.subscriber" --project="$PROJECT"

# --- trading-vm, acting as System 2: read approved orders, report fills.
#     Both bindings were absent from the original list, which left System 2 with no access
#     to anything at all.
run gcloud pubsub subscriptions add-iam-policy-binding "${AMS_OUT_TOPIC}_sub" \
    --member="serviceAccount:${TRADING_VM_SA}" --role="roles/pubsub.subscriber" --project="$PROJECT"
run gcloud pubsub topics add-iam-policy-binding "$AMS_IN_TOPIC" \
    --member="serviceAccount:${TRADING_VM_SA}" --role="roles/pubsub.publisher" --project="$PROJECT"

echo "== 5. Verify =="
run gcloud pubsub topics list --project="$PROJECT"
run gcloud pubsub subscriptions list --project="$PROJECT"

cat <<'NOTE'

== 6. AFTERWARDS — the repo still points at the local queue ==

Provisioning alone changes nothing. `.env` must also be updated:

    QUEUE_PROVIDER=pubsub          # currently 'local' — signals dead-end on this machine
    GOOGLE_CLOUD_PROJECT=scalable-brain

That second line is not optional and is not currently set. `src/common/queue/__init__.py`
defaults it to the literal string "test-project", so without it the producer would publish
into a project that does not exist and fail at runtime rather than at configuration time.

Then re-run the P5 end-to-end rehearsal against the real transport and confirm a message
arrives, before anything is trusted.
NOTE
