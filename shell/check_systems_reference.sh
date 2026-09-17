#!/usr/bin/env bash
# Detect drift between the local S2/S3 reference clones, their remotes, and what is
# actually deployed on trading-1.
#
# Read-only. Never pushes, never writes to the VM, never changes a checkout.
# Exit 0 = aligned, 1 = drift found, 2 = could not determine.
#
# Established 2026-09-13. Rationale in docs/critical/SYSTEMS_REFERENCE.md: the previous
# "reference copy" mechanism was two directory paths that did not exist, and nothing
# detected that for weeks. Staleness has to be measurable or it is not managed.

set -uo pipefail

REF_ROOT="${SYSTEMS_REFERENCE_ROOT:-/home/emmanuel/Documents/Scalable_Brain/systems-reference}"
ZONE="europe-west1-b"
VM="trading-1"
RC=0

say() { printf '%s\n' "$*"; }
warn() { printf 'DRIFT: %s\n' "$*"; RC=1; }

say "=== reference clones ($REF_ROOT)"
for repo in system2Executor scalablebrain-ams; do
  d="$REF_ROOT/$repo"
  if [[ ! -d "$d/.git" ]]; then
    say "  $repo: ABSENT — clone it (see docs/critical/SYSTEMS_REFERENCE.md)"
    RC=2; continue
  fi
  local_head=$(git -C "$d" rev-parse --short HEAD 2>/dev/null)
  git -C "$d" fetch --all --quiet 2>/dev/null
  # origin/HEAD is NOT reliably main in scalablebrain-ams — report both.
  main_tip=$(git -C "$d" rev-parse --short origin/main 2>/dev/null || echo "n/a")
  deflt=$(git -C "$d" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo "n/a")
  say "  $repo: local=$local_head origin/main=$main_tip origin/HEAD->$deflt"
  [[ "$deflt" != "origin/main" && "$deflt" != "n/a" ]] && \
    say "    note: default branch is not main — a plain clone gets $deflt"
done

say "=== deployed on $VM"
SSH="gcloud compute ssh $VM --zone $ZONE --tunnel-through-iap --command"
remote_out=$(timeout 120 $SSH "
  for p in /opt/scalablebrain/system2/system-2-execution-engine /opt/scalablebrain/system3/ams; do
    printf '%s ref=%s\n' \"\$p\" \"\$(sudo cat \$p/.git/HEAD 2>/dev/null | sed 's|ref: refs/heads/||')\"
    printf '%s sha=%s\n' \"\$p\" \"\$(sudo cat \$p/.git/refs/heads/main 2>/dev/null | cut -c1-7)\"
  done
  printf 'scoredsignal_sha256=%s\n' \"\$(sudo sha256sum /opt/scalablebrain/system3/ams/contracts/v1/ScoredSignal.schema.json 2>/dev/null | cut -c1-16)\"
  printf 's3_state=%s\n' \"\$(curl -s --max-time 8 localhost:8300/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"state\"], d[\"mode\"], \"rejects=\"+str(d[\"metrics\"][\"counters\"].get(\"decisions_rejected_total\")), d[\"metrics\"].get(\"rejects_by_layer\"))' 2>/dev/null)\"
  printf 's2_messages_seen=%s\n' \"\$(curl -s --max-time 8 localhost:8002/status | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"queue\"][\"messages_seen\"])' 2>/dev/null)\"
" 2>/dev/null | grep -vE 'NumPy|please see|^WARNING|^$')

if [[ -z "$remote_out" ]]; then
  say "  unreachable — check gcloud auth and IAP permissions"
  exit 2
fi
say "$remote_out" | sed 's/^/  /'

# The specific defect that motivated this script: the deployed contract must accept the three
# provenance fields System 1 stamps unconditionally (producer, bundle_id, drill).
# 0856914c1d5a93cb = feat/adr001-reanchor-and-drills (accepts all three)
# 16c4a315d7ca33e1 = origin/main                     (rejects all three -> total signal loss)
deployed_schema=$(say "$remote_out" | sed -n 's/^scoredsignal_sha256=//p')
case "$deployed_schema" in
  0856914c1d5a93cb) say "  contract OK: deployed schema accepts producer/bundle_id/drill" ;;
  16c4a315d7ca33e1) warn "deployed S3 schema is origin/main — it REJECTS producer/bundle_id/drill. Every System 1 signal fails validation. See ISSUE-1, 2026-09-13" ;;
  "")               say "  contract: could not read"; RC=2 ;;
  *)                warn "deployed S3 schema is an unrecognised revision ($deployed_schema) — diff it before trusting the wire" ;;
esac

exit $RC
