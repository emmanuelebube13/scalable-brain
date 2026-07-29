"""T6 — the strategy registry: one source of truth for what exists, at what stage.

Discovers contract-compliant strategies from the three stage packages and
answers `list(stage=...)` / `get(id)`.

Two guarantees the registry enforces in code:

* **Duplicate `strategy_id` is a hard error.** FIX-S1-004 was a weight collision
  caused by two entries sharing an id; the weights silently merged instead of
  failing. The registry raises rather than picking a winner.
* **Stage is derived from location, never self-declared.** A strategy's
  ``metadata.stage`` is informational; the registry overrides it with the package
  it was found in. A file cannot promote itself by editing a field — promotion is
  a `git mv` plus a report artifact (see ``promote.py``).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .contract import Stage, Strategy, StrategyMetadata

STAGE_PACKAGES = {
    Stage.RESEARCH: "src.layer0.strategies.research",
    Stage.STAGED: "src.layer0.strategies.staged",
    Stage.QUALIFIED: "src.layer0.strategies.qualified",
}

_STRATEGIES_DIR = Path(__file__).resolve().parent


class DuplicateStrategyId(ValueError):
    """Two strategies claim the same id.

    Never resolved by preferring one — that is how FIX-S1-004 lost a strategy's
    weight silently.
    """


class StrategyNotFound(KeyError):
    pass


@dataclass(frozen=True)
class RegisteredStrategy:
    strategy_id: str
    stage: Stage
    metadata: StrategyMetadata
    module: str
    cls_name: str

    def instantiate(self) -> Strategy:
        mod = importlib.import_module(self.module)
        return getattr(mod, self.cls_name)()


def _iter_stage_classes(stage: Stage) -> Iterator[tuple[str, str, type]]:
    """Yield (module_name, class_name, cls) for Strategy subclasses in a stage."""
    pkg_name = STAGE_PACKAGES[stage]
    try:
        pkg = importlib.import_module(pkg_name)
    except ModuleNotFoundError:
        return
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod_name = f"{pkg_name}.{info.name}"
        module = importlib.import_module(mod_name)
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, Strategy)
                and cls is not Strategy
                and not inspect.isabstract(cls)
                and cls.__module__ == mod_name  # skip imported symbols
            ):
                yield mod_name, cls_name, cls


class StrategyRegistry:
    """Discovers and indexes contract-compliant strategies."""

    def __init__(self) -> None:
        self._by_id: Dict[str, RegisteredStrategy] = {}
        self.refresh()

    def refresh(self) -> None:
        found: Dict[str, RegisteredStrategy] = {}
        for stage in Stage:
            for mod_name, cls_name, cls in _iter_stage_classes(stage):
                instance = cls()
                meta = instance.metadata
                # Stage comes from WHERE the file lives, not what it claims.
                meta = replace(meta, stage=stage)
                sid = meta.strategy_id
                if sid in found:
                    prior = found[sid]
                    raise DuplicateStrategyId(
                        f"strategy_id {sid!r} declared twice: "
                        f"{prior.module}.{prior.cls_name} ({prior.stage.value}) and "
                        f"{mod_name}.{cls_name} ({stage.value}). "
                        "Ids must be unique across ALL stages — a duplicate silently "
                        "collapsed strategy weights in FIX-S1-004."
                    )
                found[sid] = RegisteredStrategy(sid, stage, meta, mod_name, cls_name)
        self._by_id = found

    def list(self, stage: Optional[Stage] = None) -> List[RegisteredStrategy]:
        items = list(self._by_id.values())
        if stage is not None:
            items = [i for i in items if i.stage is stage]
        return sorted(items, key=lambda r: (r.stage.rank, r.strategy_id))

    def get(self, strategy_id: str) -> RegisteredStrategy:
        try:
            return self._by_id[strategy_id]
        except KeyError:
            raise StrategyNotFound(
                f"no strategy {strategy_id!r}; known: {sorted(self._by_id)}"
            ) from None

    def qualified(self) -> List[RegisteredStrategy]:
        """The ONLY view the live vetting path is permitted to consume.

        `vet.py` reads from here. Research and staged strategies are structurally
        invisible to it — see `test_no_side_door.py`.
        """
        return self.list(Stage.QUALIFIED)

    def stage_dir(self, stage: Stage) -> Path:
        return _STRATEGIES_DIR / stage.value

    def __len__(self) -> int:
        return len(self._by_id)


_registry: Optional[StrategyRegistry] = None


def get_registry(*, refresh: bool = False) -> StrategyRegistry:
    """Process-wide registry singleton."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    elif refresh:
        _registry.refresh()
    return _registry
