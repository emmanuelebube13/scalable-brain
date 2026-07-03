# FND-010 — Cost Optimization Audit

- **Task ID**: FND-010
- **System**: Foundational & Cross-Cutting
- **Priority**: P2-Medium
- **Estimated Effort**: 1d
- **Prerequisites**: FND-001, FND-002, FND-008
- **External Dependencies**:
  - Billing/pricing data from the chosen providers: object storage (Cloudflare R2 or self-hosted MinIO), the always-on Computer 3 host (VPS vs owned hardware), the VPN (Tailscale free tier vs self-hosted WireGuard), and any notification/monitoring services. *Why:* the audit reconciles real recurring spend against the capital constraint.
  - Access to the FND-005 metrics (actual storage/egress/compute usage) to right-size, not guess.

## Objective
Audit recurring infrastructure cost against the ~$4,000/month capital and $70k-by-Dec-2027 constraint, and recommend the cheapest reliable topology that meets the availability and safety SLOs.

## Current State
The system runs on a single owned machine with effectively zero incremental infra cost (SQL Server in Docker, local files). The three-system evolution introduces recurring costs not yet quantified: object storage, an always-on Computer 3, a VPN, a message broker, monitoring, and possibly a Docker registry. With only ~$4,000/month of trading capital, infra spend directly erodes the compounding base and must be deliberately minimized.

## Target State
A short cost model and recommendation that:
- Enumerates every recurring cost line introduced by FND-001..008 and the three systems.
- Compares self-hosted (owned hardware, zero/low recurring) vs cloud (small recurring, higher availability) for each, with an availability note.
- Recommends a target monthly infra budget and the topology that hits it without breaching the critical SLOs (Computer 3 uptime, queue availability, artifact integrity).

## Technical Specification

### Cost inventory (to be priced)
| Line item | Self-hosted option | Cloud option | Availability sensitivity |
|-----------|--------------------|--------------|--------------------------|
| Object storage (FND-001) | MinIO on Computer 1 (~$0) | Cloudflare R2 (~$/GB-mo, no egress) | High — needed during market hours; couples to Computer 1 uptime if self-hosted |
| Computer 3 / AMS host (FND-008) | old laptop / Raspberry Pi 4 (~$0 + power) | small VPS (~$5–10/mo) | Critical — must be 24/7; VPS removes home-power/uptime risk |
| Message broker (FND-002) | Redis on an existing host (~$0) | managed Redis (~$/mo) | High — execution path |
| VPN (FND-008) | self-hosted WireGuard (~$0) | Tailscale free tier (~$0 personal) | Medium |
| Monitoring (FND-005) | Grafana/Loki/Uptime Kuma self-hosted (~$0) | SaaS (avoid) | Low/Medium |
| Docker registry (FND-007) | GHCR free / self-hosted (~$0) | paid registry (avoid) | Low |
| Notifications (AMS-011) | Telegram (free) + existing email (~$0) | paid SMTP (~$/mo) | Medium |
| Training compute (System 1) | existing PC (~$0) | cloud GPU burst (only if needed) | Low — scheduled, not live |

### Analysis approach
- Right-size from FND-005 actuals: artifact volume is MB-scale (FND-001 note), queue payloads are tiny, AMS is low-compute — so storage/egress/compute costs are negligible; the only genuine recurring need is **24/7 availability** for Computer 3 and the broker/object store during market hours.
- Recommend the minimal reliable mix, e.g.: small VPS for Computer 3 + broker + R2 for artifacts + Tailscale free + self-hosted monitoring — targeting a low double-digit monthly figure.
- Flag any line that scales with usage (object versioning/WAL retention from FND-006) and set retention caps accordingly.

## Testing & Validation
- The cost model reconciles against one real billing cycle (or vendor calculator) within a reasonable margin.
- A sensitivity check: confirm projected monthly infra cost is a small single-digit percentage of monthly capital and does not materially impair the $70k trajectory.
- Availability cross-check: the recommended topology still satisfies the FND-005 critical SLOs (Computer 3 uptime, broker/object-store availability during market hours).
- Retention caps (FND-006) are set so backup/versioning storage cannot grow unbounded.

## Rollback Plan
This is an analysis/decision task with no runtime change; "rollback" is simply not adopting a recommendation. Any infra change it triggers (e.g. moving object storage from MinIO to R2) is executed under that component's own task with its own rollback.

## Acceptance Criteria
- [ ] Every recurring cost line from FND-001..008 + the three systems is enumerated with self-hosted vs cloud options priced.
- [ ] A recommended topology and target monthly infra budget are documented, justified against the capital constraint.
- [ ] The recommendation is shown to still meet the critical availability SLOs (Computer 3, broker, object store).
- [ ] Usage-scaling lines (backup/versioning retention) have caps set.
- [ ] Projected infra spend is confirmed immaterial to the $70k-by-2027 trajectory.

## Notes & Risks
- **Availability beats raw cost** on the execution path: saving a few dollars by self-hosting Computer 3 on a home machine that loses power/network defeats the purpose — the AMS must be the most reliable component. Bias the recommendation toward a cheap-but-always-on VPS for Computer 3.
- Self-hosting everything on Computer 1 minimizes cost but couples availability to the training box; quantify that trade-off explicitly.
- Revisit annually or when capital grows — at higher capital the calculus shifts toward more managed/redundant services.
