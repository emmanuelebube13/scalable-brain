"""FIX-S1-010 — governed writer for the TOP-LEVEL ``latest.json`` model-set manifest.

System 2's model downloader (EXEC-001) reads a single top-level ``latest.json`` naming
every artifact of the currently-live model set: the four System-1 bundle files plus the
three gatekeeper files, each with a SHA256 it verifies after download.

Until this module existed **nothing in System 1 wrote that file.** It was hand-authored.
On 2026-07-24 it still advertised ``model_set_id 2026-07-01T12-56-32Z_gk-656f09e2``
(``published_at 2026-07-10T00:00:00Z``) while ``system1/latest.json`` had already moved to
the 2026-07-19 bundle — so any consumer following the spec was loading a model set three
weeks and two promotions stale. Note the shape of that failure: the per-bundle publish
contract (upload → verify → flip) was intact and working, and was defeated by a
hand-maintained pointer sitting above it.

Design — the manifest is a *pure function of the two sub-pointers*:

  1. read ``system1/latest.json`` and ``models/gatekeeper/latest.json``
  2. resolve each pointer to its immutable versioned prefix and enumerate the artifacts
  3. verify every object exists and read its SHA256 **from the backend** (never from a
     local file, so the manifest describes what a consumer will actually download)
  4. atomic_pointer_update("latest.json", ...) LAST

Because the manifest only ever describes whatever the two sub-pointers currently point
at, it is coherent by construction: if a gatekeeper publish is refused (candidate did not
beat the incumbent), this packages the new System-1 bundle with the still-live gatekeeper,
which is exactly what is live. It never invents a pairing.

FIX-S1-015 — withdrawal. The contract above can only move the pointer *forward* to a
better model set; it was never given a way to say "there is no model". That gap surfaced
on 2026-08-14, when FIX-S1-014 disqualified the only qualified strategy: the correct live
state became "nothing qualifies", the ``non_empty_map`` deployment gate rightly refused to
promote an empty bundle, and so the pointer went on serving a model set whose whole map
was a strategy that cannot fire (see the fix doc). Withdrawal is therefore a **separate
verb**, not a promotion with zero artifacts:

  * ``withdraw()`` writes a manifest with ``status="withdrawn"``, an empty ``artifacts``
    list and a mandatory human reason. A consumer that iterates artifacts downloads
    nothing; one that requires artifacts fails closed, which is the direction the
    project's default-safe posture asks for (missing/stale/error ⇒ REJECT).
  * It never deletes anything. The superseded manifest is archived to
    ``previous_model_set.json``, so reinstating is a normal ``publish()``.
  * Withdrawing twice is a no-op, specifically so the second call cannot overwrite the
    rollback breadcrumb with the withdrawal itself.
  * It is CLI-only and requires ``--reason``. The orchestrator must never call it: an
    automated retrain deciding on its own to blank the live model is exactly the
    single-flag failure mode Computer 2 objected to on 2026-08-02.

Usage:
    python -m src.serializer.publish_model_set [--dry-run]
    python -m src.serializer.publish_model_set --withdraw --reason "..." [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common.storage import build_storage
from src.serializer.serialize import POINTER_KEY as S1_POINTER_KEY

logger = logging.getLogger("system1.publish_model_set")

SCHEMA_VERSION = 1
POINTER_KEY = "latest.json"
PREVIOUS_KEY = "previous_model_set.json"
GK_POINTER_KEY = "models/gatekeeper/latest.json"

# Fixed timestamp for every zip entry (D4): identical source must produce an
# identical zip on any machine, and the mtimes zipfile embeds by default would
# defeat that. 1980-01-01 is the earliest date the ZIP format's DOS-time field
# can represent.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# Inference-parity evidence bundled into code_bundle.zip. System 2's whole basis for
# trusting that its inference matches System 1's rests on these three files; a bundle
# missing any of them ships without proof, so they are REQUIRED (D3), not best-effort.
CODE_BUNDLE_REQUIRED_FILES = (
    "DETERMINISM.md",
    "reference_vector.json",
    "candle_fingerprint.json",
)

# Artifacts expected in each half of the set. A missing artifact aborts the publish:
# an incomplete model set is worse than a stale one, because the consumer's own
# verification would fail mid-download after it had already discarded its staging copy.
S1_ARTIFACTS = (
    "hmm_model.joblib",
    "regime_strategy_map.json",
    "strategy_weights.json",
    "model_metadata.json",
    "code_bundle.zip",
    # An artifact and the telemetry describing it are one inseparable unit. Listing the
    # card here is what enforces that: _collect() aborts the publish if it is absent, so
    # a set can never reach the pointer without its contemporaneously generated card, and
    # the card's SHA256 rides in the manifest under the same verify-then-flip contract as
    # the model itself. See ``_ensure_model_card`` and ``src/monitoring/model_card.py``.
    "model_card.json",
)
GK_ARTIFACTS = (
    "champion_model.pkl",
    "champion_preprocessor.pkl",
    "champion_manifest.json",
)


# Consumer contract, agreed with System 2 in S2-REPLY-2026-08-15 §4.1:
#   any of missing / unreadable / status != "published" / empty artifacts /
#   an unrecognised status  =>  REJECT.
# "Unknown is not a permissive default", so a manifest MUST state its status explicitly.
# Before 2026-08-15 this module emitted no ``status`` at all; under the agreed rule that
# reads as "not published" and every real promotion would be refused downstream.
STATUS_PUBLISHED = "published"
STATUS_WITHDRAWN = "withdrawn"


class ModelSetRefused(Exception):
    """Raised when the model set cannot be assembled coherently (never publishes)."""


def _read_json(storage, key: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON object from the backend, or None if it is not there."""
    if not storage.exists(key):
        return None
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ptr.json")
        storage.get_object(key, p)
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)


def _collect(storage, prefix: str, names: tuple) -> List[Dict[str, Any]]:
    """Resolve ``names`` under ``prefix`` to manifest entries, verified against the backend."""
    prefix = prefix.rstrip("/")
    out: List[Dict[str, Any]] = []
    for name in names:
        key = f"{prefix}/{name}"
        if not storage.exists(key):
            raise ModelSetRefused(f"model set incomplete — missing object {key!r}")
        meta = storage.head(key)
        out.append(
            {
                "name": name,
                "path": key,
                "sha256": meta.get("sha256"),
                "bytes": meta.get("size"),
            }
        )
    return out


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_code_bundle_zip(zip_path: str) -> None:
    """Build ``code_bundle.zip`` deterministically at ``zip_path``.

    Byte-identical for byte-identical inputs (D4): every entry is collected into a
    dict first, written out in sorted-by-arcname order, and stamped with a fixed
    ``date_time`` via an explicit ``ZipInfo`` — ``zf.write()``'s default embeds the
    source file's mtime, which is why the old version produced a different zip on
    every machine (and every checkout) even from identical source.

    Raises ``ModelSetRefused`` if any inference-parity artifact is missing (D3):
    those files are System 2's only evidence its inference matches System 1's, so a
    bundle without them ships with the safety argument silently missing.
    """
    repo_root = _repo_root()
    serializer_dir = os.path.abspath(os.path.dirname(__file__))
    contents: Dict[str, bytes] = {}

    strategies_dir = os.path.join(repo_root, "src", "layer0", "strategies")
    for root, _dirs, files in os.walk(strategies_dir):
        for f in sorted(files):
            if f.endswith(".py"):
                p = os.path.join(root, f)
                arcname = os.path.relpath(p, repo_root)
                with open(p, "rb") as fh:
                    contents[arcname] = fh.read()

    for arcname, rel_parts in (
        (
            "src/layer0/data_access/indicators.py",
            ("src", "layer0", "data_access", "indicators.py"),
        ),
        ("src/regime/structural.py", ("src", "regime", "structural.py")),
    ):
        with open(os.path.join(repo_root, *rel_parts), "rb") as fh:
            contents[arcname] = fh.read()

    for name in CODE_BUNDLE_REQUIRED_FILES:
        p = os.path.join(serializer_dir, name)
        if not os.path.exists(p):
            raise ModelSetRefused(
                f"code bundle refused — required inference-parity artifact missing: "
                f"{name!r} (looked in {serializer_dir!r})"
            )
        with open(p, "rb") as fh:
            contents[name] = fh.read()

    contents["requirements.txt"] = (
        "\n".join(
            [
                "numpy==2.4.4",
                "pandas==2.3.3",
                "scikit-learn==1.8.0",
                "joblib==1.5.3",
                "hmmlearn==0.3.3",
            ]
        )
        + "\n"
    ).encode("utf-8")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(contents):
            info = zipfile.ZipInfo(arcname, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, contents[arcname])


def _git_provenance(repo_root: str) -> Dict[str, Any]:
    """Identify the commit the bundled code came from (D5).

    Fails closed: if git can't be asked (not a repo, ``git`` missing, etc.) this
    raises ``ModelSetRefused`` rather than publish a manifest with no provenance or
    a fabricated one. A dirty working tree is still allowed to publish, but the
    manifest must say so rather than silently recording a commit hash that does not
    match what actually got bundled.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        # Scope the dirty check to the paths that actually end up in code_bundle.zip.
        # Over the whole tree it was permanently true — untracked runtime outputs under
        # results/ are written by ordinary pipeline runs — and a flag that is always set
        # is a flag nobody acts on. Narrow it to source and contracts so ``code_dirty``
        # means what a consumer would take it to mean: the bundled code does not match
        # the recorded commit.
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "contracts"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ModelSetRefused(f"could not determine git provenance: {exc}") from exc
    return {"code_commit": commit, "code_dirty": bool(status.strip())}


def _ensure_model_card(storage, regenerate: bool = False) -> Optional[str]:
    """Guarantee this bundle version has its telemetry card, or refuse to publish.

    **The atomic-deployment gate.** A model artifact may not ship without the
    contemporaneously generated payload that describes it, so if the card cannot be built
    this raises and the pointer is never touched.

    Generated *once per bundle version*, into the bundle's own immutable prefix. If the
    card already exists the bundle has not changed, so neither should its telemetry:
    regenerating would rewrite the measurements under an unchanged artifact and make the
    manifest digest — and therefore every publish — non-deterministic.

    Runs under ``--dry-run`` too, and writes the card when one is absent. That follows the
    ``code_bundle.zip`` precedent directly above: the versioned prefix is staging, and the
    *pointer flip* is the publish. Staging the card during a dry run is what lets the dry
    run answer the question it is asked — "would this publish succeed?" — since a set whose
    card cannot be built must not report a clean dry run.

    Returns the card's storage key, or ``None`` when there is no bundle pointer to attach
    one to (``build_manifest`` raises on that case immediately after).
    """
    from src.monitoring.model_card import CARD_ARTIFACT_NAME, ModelCardRefused
    from src.monitoring import model_card as mc

    s1 = _read_json(storage, S1_POINTER_KEY)
    gk = _read_json(storage, GK_POINTER_KEY)
    if not s1 or not s1.get("bundle_version") or not gk or not gk.get("version"):
        return None

    s1_version = str(s1["bundle_version"])
    gk_version = str(gk["version"])
    s1_prefix = str(s1.get("path") or f"system1/{s1_version}").rstrip("/")
    gk_prefix = str(gk.get("path") or f"models/gatekeeper/{gk_version}").rstrip("/")
    card_key = f"{s1_prefix}/{CARD_ARTIFACT_NAME}"

    if storage.exists(card_key):
        if not regenerate:
            logger.info("model card already pinned to bundle %s — reusing", s1_version)
            return card_key
        # Escape hatch for a card that is wrong rather than stale — a schema fix, or a
        # field that turned out to be unrenderable. Without it the only way to correct a
        # published card is to mint a new bundle version, and the temptation is to reach
        # for the bucket by hand instead. Deliberately explicit and never automatic: the
        # card's SHA256 changes, so the manifest changes, so the pointer flips.
        logger.warning(
            "REGENERATING the model card pinned to bundle %s — the model set's manifest "
            "digest will change and the pointer will flip",
            s1_version,
        )
        storage.delete_prefix(card_key)

    # A provisional pointer, carrying only what the card builder needs to resolve the
    # artifacts it reads. The card describes the set being packaged, not whatever is
    # currently live — that is what makes it contemporaneous.
    provisional = {
        "model_set_id": f"{s1_version}_gk-{gk_version.split('-')[-1]}",
        "system1_bundle_version": s1_version,
        "gatekeeper_version": gk_version,
        "artifacts": _collect(storage, s1_prefix, ("regime_strategy_map.json",))
        + _collect(storage, gk_prefix, GK_ARTIFACTS),
    }

    try:
        card = mc.build(storage, provisional)
    except ModelCardRefused as exc:
        raise ModelSetRefused(
            f"HALTING PUBLISH — model set {provisional['model_set_id']} has no telemetry "
            f"payload and an artifact may not ship undescribed: {exc}"
        ) from exc
    except Exception as exc:
        raise ModelSetRefused(
            f"HALTING PUBLISH — model card build failed for "
            f"{provisional['model_set_id']}: {type(exc).__name__}: {exc}"
        ) from exc

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, CARD_ARTIFACT_NAME)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(card, fh, indent=2, sort_keys=True)
        storage.put_object(card_key, path)
    logger.info("model card generated and pinned to bundle %s", s1_version)
    return card_key


def build_manifest(storage) -> Dict[str, Any]:
    """Assemble the model-set manifest from the two live sub-pointers (no writes)."""
    s1 = _read_json(storage, S1_POINTER_KEY)
    if not s1 or not s1.get("bundle_version"):
        raise ModelSetRefused(
            f"no System-1 bundle pointer at {S1_POINTER_KEY!r} — nothing to package"
        )
    gk = _read_json(storage, GK_POINTER_KEY)
    if not gk or not gk.get("version"):
        raise ModelSetRefused(
            f"no gatekeeper pointer at {GK_POINTER_KEY!r} — nothing to package"
        )

    s1_version = str(s1["bundle_version"])
    gk_version = str(gk["version"])
    s1_prefix = str(s1.get("path") or f"system1/{s1_version}")
    gk_prefix = str(gk.get("path") or f"models/gatekeeper/{gk_version}")

    artifacts = _collect(storage, s1_prefix, S1_ARTIFACTS) + _collect(
        storage, gk_prefix, GK_ARTIFACTS
    )

    # Provenance, requested by System 2 in S2-REPLY-2026-08-15: bind the manifest to the
    # qualification run that produced the map inside it. Their 2026-08-15 incident is the
    # argument — two stale artefacts AGREED with each other, so internal consistency
    # proved nothing; only binding to the running qualification run caught it. Read from
    # the bundle in the backend, never from a local file, so it describes what a consumer
    # will actually download.
    qual_run_id = (
        _read_json(storage, f"{s1_prefix.rstrip('/')}/regime_strategy_map.json") or {}
    )

    # Git provenance (D5): the commit the bundled code came from. Fails closed via
    # _git_provenance — never publish a manifest that can't say where the code in
    # code_bundle.zip came from.
    provenance = _git_provenance(_repo_root())

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PUBLISHED,
        "qualification_run_id": qual_run_id.get("qualification_run_id"),
        # Keeps the historical ``<s1_version>_gk-<short>`` shape so an existing consumer's
        # "has the id changed?" comparison keeps working across this cutover.
        "model_set_id": f"{s1_version}_gk-{gk_version.split('-')[-1]}",
        "published_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "system1_bundle_version": s1_version,
        "gatekeeper_version": gk_version,
        "code_commit": provenance["code_commit"],
        "code_dirty": provenance["code_dirty"],
        "artifacts": artifacts,
    }


#: Fields that legitimately differ between two publishes of the same material content.
#: ``published_at`` is a wall-clock stamp; comparing it would make every publish "changed".
_VOLATILE_MANIFEST_FIELDS = frozenset({"published_at"})


def _is_materially_identical(prev: Dict[str, Any], manifest: Dict[str, Any]) -> bool:
    """True when republishing ``manifest`` would tell a consumer nothing new.

    Keying this on ``model_set_id`` alone was not enough, and the gap was found in
    production: ``model_set_id`` is derived from the two sub-pointer *versions*, so it is
    stable while artifact *content* changes underneath it. When the code bundle was
    rebuilt to include the determinism evidence, the zip in the bucket changed but the
    pointer was left untouched — leaving the manifest advertising a SHA256 that no longer
    matched the object. A consumer following this guide would download the bundle, compute
    its hash, and correctly refuse the whole model set.

    So compare everything that a consumer can observe: the artifact list including every
    checksum, the code provenance, and the status — not just the identifier.
    """
    a = {k: v for k, v in prev.items() if k not in _VOLATILE_MANIFEST_FIELDS}
    b = {k: v for k, v in manifest.items() if k not in _VOLATILE_MANIFEST_FIELDS}
    return bool(json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))


def publish(
    dry_run: bool = False, storage=None, regenerate_card: bool = False
) -> Dict[str, Any]:
    """Build and (unless ``dry_run``) atomically flip the top-level model-set pointer."""
    storage = storage or build_storage()

    # Build (or refresh) code_bundle.zip before manifest verification. Rebuilt whenever
    # its contents would differ from what's already stored (D2) — the bug this closes:
    # gating the build on "does the key exist" meant a zip built before DETERMINISM.md /
    # reference_vector.json / candle_fingerprint.json existed was never rebuilt once they
    # did, so the published bundle silently shipped without them. Comparing content
    # hashes instead keeps this idempotent: identical inputs produce an identical zip
    # (D4), so unchanged code never triggers a re-upload.
    s1 = _read_json(storage, S1_POINTER_KEY)
    if s1 and s1.get("bundle_version"):
        s1_version = str(s1["bundle_version"])
        s1_prefix = str(s1.get("path") or f"system1/{s1_version}").rstrip("/")
        bundle_key = f"{s1_prefix}/code_bundle.zip"
        with tempfile.TemporaryDirectory() as td:
            zip_path = os.path.join(td, "code_bundle.zip")
            _build_code_bundle_zip(zip_path)
            new_sha = _sha256_file(zip_path)
            existing_sha = (
                storage.head(bundle_key)["sha256"]
                if storage.exists(bundle_key)
                else None
            )
            if existing_sha != new_sha:
                if storage.exists(bundle_key):
                    # Objects are immutable (put_object refuses to overwrite), so a
                    # content change must clear the old object first.
                    storage.delete_prefix(bundle_key)
                storage.put_object(bundle_key, zip_path)

    # Atomic-deployment gate. Runs BEFORE build_manifest so the card is present to be
    # enumerated and hashed into the manifest; raises ModelSetRefused if it cannot be
    # built, which halts the publish with the pointer untouched.
    _ensure_model_card(storage, regenerate=regenerate_card)

    manifest = build_manifest(storage)

    logger.info(
        "model set %s: s1=%s gk=%s (%d artifacts)",
        manifest["model_set_id"],
        manifest["system1_bundle_version"],
        manifest["gatekeeper_version"],
        len(manifest["artifacts"]),
    )
    if dry_run:
        logger.info("dry-run — pointer NOT flipped")
        return {**manifest, "published": False}

    prev = _read_json(storage, POINTER_KEY)
    if prev is not None and _is_materially_identical(prev, manifest):
        logger.info(
            "model set %s already live — pointer left untouched",
            manifest["model_set_id"],
        )
        return {**manifest, "published": False, "unchanged": True}
    if prev is not None:
        storage.atomic_pointer_update(PREVIOUS_KEY, prev)  # rollback breadcrumb

    # Generate and upload the detached signature. Fails CLOSED (D6): if the signing key
    # is present but signing raises for any reason, the publish must abort here — before
    # the pointer flip below — rather than log-and-continue into an unsigned manifest
    # System 2 would have no way to detect as unsigned.
    priv_path = os.path.join(_repo_root(), "secrets", "manifest_signing_key.pem")
    if os.path.exists(priv_path):
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
            from cryptography.hazmat.primitives import serialization
            import base64

            with open(priv_path, "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(), password=None
                )
            if not isinstance(private_key, rsa.RSAPrivateKey):
                raise ValueError(
                    f"manifest signing key is {type(private_key).__name__}, "
                    "expected an RSA key (RSA-PSS/SHA256 is the agreed scheme)"
                )
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
            signature = private_key.sign(
                manifest_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            sig_b64 = base64.b64encode(signature).decode("utf-8")

            with tempfile.TemporaryDirectory() as td:
                sig_path = os.path.join(td, "latest.json.sig")
                with open(sig_path, "w", encoding="utf-8") as f:
                    f.write(sig_b64)
                sig_key = f"{POINTER_KEY}.sig"
                if storage.exists(sig_key):
                    # Not a versioned artifact — it legitimately changes on every
                    # publish (the manifest it's over does), so clear the old one
                    # first rather than let put_object's immutability guard fire.
                    storage.delete_prefix(sig_key)
                storage.put_object(sig_key, sig_path)
        except Exception as exc:
            raise ModelSetRefused(
                f"manifest signing failed — aborting publish: {exc}"
            ) from exc
    else:
        logger.warning(
            "no manifest signing key at %s — publishing an UNSIGNED manifest", priv_path
        )

    # Distribute the public key alongside the manifest (D7) so System 2 can verify the
    # signature above. Never the private key. Cheap and idempotent — re-uploaded on every
    # publish so a rotated key stays in sync with what's signing; harmless if unchanged.
    pub_path = os.path.join(_repo_root(), "secrets", "manifest_signing_key.pub")
    if os.path.exists(pub_path):
        pub_key_bucket_key = "system1_manifest_signing_key.pub"
        if storage.exists(pub_key_bucket_key):
            storage.delete_prefix(pub_key_bucket_key)
        storage.put_object(pub_key_bucket_key, pub_path)
    else:
        logger.warning(
            "no public signing key at %s — System 2 will be unable to verify "
            "the manifest signature",
            pub_path,
        )

    storage.atomic_pointer_update(POINTER_KEY, manifest)
    logger.info(
        "published model set %s (supersedes %s)",
        manifest["model_set_id"],
        (prev or {}).get("model_set_id"),
    )

    # Project the pinned card onto the frontend key. This is a copy, not a recomputation,
    # so it cannot disagree with what shipped. It is deliberately AFTER the flip: the
    # "pointer flip last" contract is inviolable, and the card is already live inside the
    # set by this point — the mirror is a convenience surface, not the source of truth.
    # A failure here leaves the frontend stale, not wrong; the hourly cron re-asserts it
    # and ``model_card --verify`` reports the gap in the meantime.
    try:
        from src.monitoring.model_card import mirror

        mirror(storage, pointer=manifest)
    except Exception as exc:
        logger.error(
            "model set %s is live but its telemetry mirror failed to update (%s) — "
            "the pinned card in the set is authoritative; run "
            "`python -m src.monitoring.model_card --mirror` to repair",
            manifest["model_set_id"],
            exc,
        )

    return {
        **manifest,
        "published": True,
        "supersedes": (prev or {}).get("model_set_id"),
    }


def build_withdrawal(reason: str, supersedes: Optional[str]) -> Dict[str, Any]:
    """The withdrawal manifest. Pure — no I/O, so the shape is testable on its own."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("--reason is mandatory: a withdrawal must say why in words")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_WITHDRAWN,
        # Explicitly null rather than absent: a consumer keying on model_set_id sees a
        # value that cannot match anything it has, instead of a missing key it might
        # treat as "unchanged".
        "model_set_id": None,
        "withdrawn_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "reason": reason,
        "supersedes": supersedes,
        "artifacts": [],
    }


def withdraw(reason: str, dry_run: bool = False, storage=None) -> Dict[str, Any]:
    """State in the live artefact that there is no model set.

    This is a **separate verb from publish**, not a promotion with zero artifacts.
    ``publish()`` can only move the pointer forward to a better set; it has no way to
    say "there is none", which is why the pointer went on serving a withdrawn map for
    a day after FIX-S1-014 emptied the qualified set.

    Never deletes. The superseded manifest is archived to ``previous_model_set.json``,
    so reinstating is an ordinary ``publish()``.
    """
    storage = storage or build_storage()
    prev = _read_json(storage, POINTER_KEY)

    if prev is not None and prev.get("status") == STATUS_WITHDRAWN:
        # Idempotent on purpose. A second withdrawal must NOT archive the first one over
        # the rollback breadcrumb — that would replace the last real model set with an
        # empty manifest and leave nothing to reinstate.
        logger.info("model set already withdrawn — pointer left untouched")
        return {**prev, "published": False, "unchanged": True}

    manifest = build_withdrawal(reason, (prev or {}).get("model_set_id"))

    if dry_run:
        logger.info("dry-run — pointer NOT flipped")
        return {**manifest, "published": False}

    if prev is not None:
        storage.atomic_pointer_update(PREVIOUS_KEY, prev)  # rollback breadcrumb

    storage.atomic_pointer_update(POINTER_KEY, manifest)
    logger.warning(
        "WITHDRAWN model set %s — reason: %s",
        (prev or {}).get("model_set_id"),
        manifest["reason"],
    )
    return {**manifest, "published": True}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the top-level model-set manifest"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble and print the manifest without flipping the pointer.",
    )
    parser.add_argument(
        "--withdraw",
        action="store_true",
        help=(
            "Withdraw the live model set: publish an empty manifest with "
            'status="withdrawn". Requires --reason. CLI only — the orchestrator '
            "must never call this."
        ),
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Mandatory human explanation for --withdraw. Recorded in the manifest.",
    )
    parser.add_argument(
        "--regenerate-card",
        action="store_true",
        help=(
            "Rebuild the model card pinned to the current bundle instead of reusing it. "
            "For a card that is WRONG (schema fix, unrenderable field) — not for "
            "refreshing its numbers, which must stay pinned to the artifact they "
            "describe. Changes the manifest digest and flips the pointer."
        ),
    )
    args = parser.parse_args()
    if args.reason and not args.withdraw:
        parser.error("--reason is only meaningful with --withdraw")
    if args.regenerate_card and args.withdraw:
        parser.error("--regenerate-card is meaningless with --withdraw")
    if args.withdraw and not args.reason.strip():
        parser.error("--withdraw requires --reason: say why, in words, in the manifest")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            ".env",
        )
    )
    try:
        if args.withdraw:
            print(
                json.dumps(withdraw(reason=args.reason, dry_run=args.dry_run), indent=2)
            )
        else:
            print(
                json.dumps(
                    publish(dry_run=args.dry_run, regenerate_card=args.regenerate_card),
                    indent=2,
                )
            )
    except ModelSetRefused as e:
        logger.error("MODEL SET REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
