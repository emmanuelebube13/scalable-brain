# FIX-XC-003 — Live DB password committed in git-tracked files (and in history)

**Severity:** P1 (secret exposure; the live `ForexBrainDB` `sa` password is in the tracked tree)
**Status:** Proposed
**Author:** Claude (cross-cutting auditor)
**Date raised:** 2026-06-26
**System:** Cross-cutting (secrets handling)

---

## 1. Executive summary

The roadmap (`docs/implementation-roadmap/.../03-secrets-management-and-rotation.md`) treats the DB
password as a **`.env`-on-disk** problem and notes `.env` is gitignored. But the password
`Emm5$manuel` for role `sa` on the canonical `ForexBrainDB` is **committed in git-tracked files in `HEAD`**,
including a full DSN, and appears in prior commits. This is a strictly worse exposure than the documented
`.env` case: anyone with repo read access (or a clone/fork) has the live credential.

---

## 2. Evidence

Tracked files in `HEAD` containing the secret (`git grep -l 'Emm5' HEAD`):

```
HEAD:configuration/postgresql_connection_details.txt
HEAD:index.html
```

`configuration/postgresql_connection_details.txt` (tracked) contains the credential in the clear, including
a ready-to-use DSN:

```
Username: sa
Password: Emm5$manuel
postgresql://sa:Emm5$manuel@localhost:5432/ForexBrainDB
```

`index.html` (tracked) embeds it in a troubleshooting note (line ~995): "Quotes included in DB_PASS …
('Emm5$manuel' …)". The secret also rode in earlier commits (`git log -S 'Emm5$manuel'` →
`3ffb504`, `93cc50e`; e.g. `results/qualification_report_20260406_194514.md`,
`results/layer2_strategies_bypass.sql`), so it lives in **history** as well as the working tree.

Scope check (good news, to bound the finding): no literal OANDA token is committed — OANDA code reads the
key from the environment (`docs/reference/schoolsubmission/ICE3.py:30` `OANDA_API_KEY = os.getenv(...)`),
and `docker-compose.yml:33` uses `${DB_PASS}` (not a literal). So this finding is specifically the **DB
password in tracked files + history**.

---

## 3. Root cause

A connection-details memo and a static status page were committed with the live password inlined, and
generated `results/` artifacts captured it. There is no pre-commit secret scanner and no separation between
"docs you can commit" and "secrets you cannot."

---

## 4. Proposed fix

1. **Rotate the `sa` password now** — assume it is compromised (it is in clones, forks, and history).
2. **Remove the secret from the tree:** delete/redact `configuration/postgresql_connection_details.txt`
   and the `index.html` note; replace with a placeholder (`postgresql://sa:<DB_PASS>@localhost:5432/...`).
3. **Purge history** (`git filter-repo` / BFG) for the password string, then force-push and re-clone — or,
   if history rewrite is unacceptable, rotate (step 1) so the leaked value is dead.
4. **Add a pre-commit secret scan** (gitleaks/trufflehog) and a `.gitignore`/`.git/info/attributes` guard
   for `configuration/*connection*`.
5. Cross-link to roadmap task `03-secrets-management-and-rotation.md` (this is the concrete, tracked-tree
   instance that task must also remediate, not just `.env`).

---

## 5. Validation plan

- `git grep -i 'Emm5' $(git rev-list --all)` returns nothing after history purge (or the value is rotated
  and dead).
- Pre-commit secret scanner blocks re-introduction (add a unit test secret to confirm it trips).
- App still connects using only `.env` / secret-manager values.

---

## 6. Rollout / risk

- **Rollout:** rotate first (instant, no history rewrite needed to neutralise), then redact files, then
  optionally purge history. Coordinate a history rewrite with all clone holders.
- **Risk if not fixed:** the canonical store's superuser credential is readable by anyone with repo access;
  combined with the DSN, it is directly usable.

---

## 7. One-paragraph summary

The live `ForexBrainDB` `sa` password `Emm5$manuel` is committed in two git-tracked files in `HEAD` —
`configuration/postgresql_connection_details.txt` (a full `postgresql://sa:Emm5$manuel@...` DSN) and
`index.html` — and is present in history (commits `3ffb504`, `93cc50e`). The roadmap only frames this as a
gitignored-`.env` concern; the tracked-tree exposure is worse. Fix: rotate the password immediately, redact
the files, purge/neutralise history, and add a pre-commit secret scanner. (OANDA keys are *not* leaked —
they are read from env — so this is scoped to the DB password.)
