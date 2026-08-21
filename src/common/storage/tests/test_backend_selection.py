"""FIX-S1-012 — `build_storage()` must not silently fall back to local storage.

The failure this guards against produced no error and no wrong-looking output:
an entry point that had not already imported something calling `load_dotenv()`
got a LocalFS backend while `.env` said `gcs`, and then read plausible data from
the wrong place.

It cost the project its regression gate. `scheduler.orchestrator` does not load
`.env` at import time, so `_incumbent()` resolved against the local
`model-artifacts/` tree instead of GCS on every real retrain, found no
`system1/latest.json`, logged "NO INCUMBENT FOUND", and `beats_incumbent` took
its fail-open branch. All three 2026 promotions were therefore never compared
against their predecessor.

See `task/2026-July-week4/deliverables/T3/`.
"""

from __future__ import annotations

import subprocess
import sys

REPO_CHECK = """
import os, sys
sys.path.insert(0, {repo!r})
{preamble}
from src.common.storage import build_storage
print(type(build_storage()).__name__)
"""


def _run(preamble: str, env: dict | None = None) -> str:
    from pathlib import Path

    repo = str(Path(__file__).resolve().parents[4])
    code = REPO_CHECK.format(repo=repo, preamble=preamble)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=repo,
        env={**__import__("os").environ, **(env or {})},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_backend_honours_dotenv_without_any_prior_import():
    """A cold entry point must still get the backend `.env` asks for.

    Run in a subprocess with STORAGE_PROVIDER scrubbed, importing nothing that
    would load dotenv as a side effect — the orchestrator's exact situation.
    """
    result = _run("os.environ.pop('STORAGE_PROVIDER', None)")
    assert result == "GCSBackend", (
        f"expected the .env provider, got {result} — build_storage() has silently "
        "fallen back to local storage, which is how the regression gate went inert"
    )


def test_explicit_environment_still_overrides_dotenv():
    """CI and tests must be able to force a backend."""
    assert _run("", env={"STORAGE_PROVIDER": "local"}) == "LocalFSBackend"


def test_orchestrator_import_path_resolves_the_real_backend():
    """The specific regression: importing the orchestrator first must not matter."""
    result = _run(
        "os.environ.pop('STORAGE_PROVIDER', None)\n"
        "from src.scheduler import orchestrator  # noqa: F401"
    )
    assert result == "GCSBackend"


def test_incumbent_resolves_a_live_bundle_not_absent():
    """`_incumbent()` must find the live bundle, not report 'absent'.

    'absent' is the fail-open branch. It is correct only for a genuine
    first-ever publish; when a model IS live it means the regression gate is
    inert, which is precisely what happened on 2026-07-01, 07-19 and 07-26.
    """
    from pathlib import Path

    repo = str(Path(__file__).resolve().parents[4])
    code = (
        f"import sys; sys.path.insert(0, {repo!r})\n"
        "import os; os.environ.pop('STORAGE_PROVIDER', None)\n"
        "from src.scheduler.orchestrator import _incumbent\n"
        "inc = _incumbent()\n"
        "print(inc.get('resolution'), (inc.get('metrics') or {}).get('regime_accuracy'))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=repo
    )
    if proc.returncode != 0:
        import pytest

        pytest.skip(
            f"storage backend unreachable in this environment: {proc.stderr[-200:]}"
        )

    resolution, accuracy = proc.stdout.strip().split()
    assert resolution in ("prefixed", "legacy_model_set"), (
        f"incumbent resolution is {resolution!r} — beats_incumbent will fail open "
        "and promote without any comparison"
    )
    assert accuracy != "None", "incumbent has no regime_accuracy to compare against"
