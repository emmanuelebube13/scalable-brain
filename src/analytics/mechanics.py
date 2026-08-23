"""How each strategy enters and exits, plus a human-editable notes overlay.

Two sources, deliberately separated
-----------------------------------
**Derived** (this module, from source): entry mechanisms, exit legs, indicators. These are
read out of the strategy modules themselves, so they cannot drift from what the code
actually does — the failure mode a hand-maintained catalogue always eventually reaches.

**Curated** (``docs/strategy-notes.json``): why a strategy failed, what was tried, what to
do next. Judgement, not fact, and no amount of parsing produces it.

The overlay is a plain JSON file with no schema enforcement beyond "object keyed by
strategy name". Anyone may edit it — this repo, System 2, System 3, or a human — and it is
merged into the published catalogue on the next build. Unknown fields pass through
untouched, so the shape can grow without a code change here. That is the point: the
catalogue is *uploaded and editable*, not compiled in.

Derived fields always win a key collision. A note claiming a strategy exits on a trailing
stop cannot override the source saying otherwise.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("system1.analytics.mechanics")

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Human-editable overlay. Absent or malformed is fine — the catalogue is still built.
NOTES_PATH = os.path.join(REPO, "docs", "strategy-notes.json")

#: Where strategy modules live, in search order.
STRATEGY_DIRS = (
    os.path.join(REPO, "src", "layer0", "strategies", "qualified"),
    os.path.join(REPO, "src", "layer0", "strategies", "staged"),
    os.path.join(REPO, "src", "layer0", "strategies", "research"),
    os.path.join(REPO, "src", "layer0", "strategies", "strategieStaged"),
)

#: Contract-v2 exit kinds, rendered for a human reader rather than a parser.
EXIT_LABEL = {
    "take_profit": "fixed target",
    "trailing": "ATR trail",
    "time": "time exit",
}

#: Entry mechanisms a contract-v2 ``OrderIntent`` may declare.
_ENTRY_RE = re.compile(r'entry="(\w+)"')
_EXIT_RE = re.compile(r'kind="(\w+)"')

# ``required_indicators`` is a PROPERTY returning a list, never a tuple assignment:
#
#     @property
#     def required_indicators(self) -> List[str]:
#         return ["ema", "rsi"]
#
# The first version of this matched ``required_indicators = (...)``, which no strategy
# writes, so it silently returned [] for all 67 — including the 48 whose entries and exits
# resolved fine from the same file. The dashboard caught it: an extractor that never
# populates a list is indistinguishable, in the payload, from 67 strategies that use no
# indicators. Match the return statement inside the property instead.
_INDICATOR_RE = re.compile(
    r"def\s+required_indicators\s*\([^)]*\)[^:]*:\s*(?:#[^\n]*\n\s*)*return\s*\[([^\]]*)\]",
    re.S,
)

#: First prose line of a module docstring, used when the registry has no description.
_DOCSTRING_RE = re.compile(r'^\s*(?:#[^\n]*\n)*\s*"""(.*?)"""', re.S)


def _source_for(name: str) -> str:
    """Read a strategy module's source, or '' if it cannot be located."""
    for d in STRATEGY_DIRS:
        p = os.path.join(d, f"{name}.py")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    return fh.read()
            except Exception:
                return ""
    return ""


def derive_mechanics(name: str) -> Dict[str, Any]:
    """Entry/exit/indicator mechanics read out of the strategy's own source.

    Returns empty lists rather than raising when the module cannot be found — a legacy
    strategy with no v2 module is a normal case, not an error, and the catalogue must
    still list it.
    """
    source = _source_for(name)
    if not source:
        return {"entries": [], "exits": [], "indicators": [], "mechanics_source": None}

    indicators: List[str] = []
    m = _INDICATOR_RE.search(source)
    if m:
        indicators = sorted(set(re.findall(r'["\'](\w+)["\']', m.group(1))))

    return {
        "entries": sorted(set(_ENTRY_RE.findall(source))),
        "exits": sorted({EXIT_LABEL.get(k, k) for k in _EXIT_RE.findall(source)}),
        "indicators": indicators,
        "moves_to_breakeven": 'move_to_breakeven_on="' in source,
        "mechanics_source": "module",
        "module_summary": docstring_summary(name, source),
    }


def docstring_summary(name: str, source: str = "") -> Optional[str]:
    """First prose line of the module docstring, or None.

    The registry has a ``description`` for only 10 of 67 strategies, and the other 57 were
    being published as the literal string ``"None"`` — an absence rendered as an answer.
    Most modules open with a one-line summary of what the strategy does, which is a better
    description than nothing and comes from the same file as the mechanics.
    """
    source = source or _source_for(name)
    if not source:
        return None
    m = _DOCSTRING_RE.search(source)
    if not m:
        return None
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        # Skip the "name — SPEC-x.md (CSV row n)" title lines these modules often open with.
        if line and not line.startswith(("=", "-", "~")):
            return line[:400]
    return None


def load_notes(path: str = NOTES_PATH) -> Dict[str, Dict[str, Any]]:
    """Load the curated overlay. Never raises — a broken file must not break a publish."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        notes = data.get("strategies", data)
        if not isinstance(notes, dict):
            logger.warning(
                "%s is not an object keyed by strategy name — ignoring", path
            )
            return {}
        return {str(k): v for k, v in notes.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning("Could not read %s: %s — publishing without notes", path, e)
        return {}


def enrich(entry: Dict[str, Any], notes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Add derived mechanics and any curated note to one catalogue entry.

    Derived fields are applied last so source always beats prose on a collision.
    """
    name = str(entry.get("name", ""))
    note = dict(notes.get(name, {}))
    if note:
        note.setdefault("notes_source", "docs/strategy-notes.json")
    merged = {**entry, **note, **derive_mechanics(name)}

    # The registry describes only 10 of 67. Where it is silent, the module's own opening
    # line is a real description from the same file as the mechanics -- and a far better
    # answer than null. Recorded so a reader knows which they are looking at.
    if not merged.get("description") and merged.get("module_summary"):
        merged["description"] = merged["module_summary"]
        merged["description_source"] = "module_docstring"
    elif merged.get("description"):
        merged.setdefault("description_source", "registry")
    merged.pop("module_summary", None)
    return merged
