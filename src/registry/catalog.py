from dataclasses import dataclass
from typing import Any, List
from sqlalchemy import text
from src.common.db import get_engine


@dataclass(frozen=True)
class StrategyRecord:
    strategy_id: int
    strategy_key: str
    universe: str
    engine: str
    primary_granularity: str | None
    family: str | None


def all_strategies(include_inactive: bool = False) -> List[StrategyRecord]:
    """Registered strategies, ACTIVE ones by default (O-3, 2026-09-16).

    The registry carries retired rows — 9 ``*_RA`` ids whose ``src.regime_aware``
    module was deleted on purpose after the R3 trial, and the ``Range_Bollinger_*``
    trio absent from ``get_all_strategies()`` — which can never instantiate. Feeding
    them to the outcomes writer produced 12 ``failed_instantiate`` warnings per
    nightly run for rows that are history, not work. ``include_inactive=True`` is for
    audit replays that must reproduce a historical universe; ``by_id``/``by_key``
    stay unfiltered so old rows always resolve for provenance.
    """
    db_engine = get_engine()
    where = "" if include_inactive else "WHERE is_active = true "
    with db_engine.connect() as conn:
        result = (
            conn.execute(
                text(
                    "SELECT strategy_id, strategy_key, universe, engine, primary_granularity, family "
                    f"FROM dim_strategy {where}ORDER BY strategy_id"
                )
            )
            .mappings()
            .all()
        )

    return [StrategyRecord(**row) for row in result]


def by_id(strategy_id: int) -> StrategyRecord:
    db_engine = get_engine()
    with db_engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT strategy_id, strategy_key, universe, engine, primary_granularity, family FROM dim_strategy WHERE strategy_id = :id"
                ),
                {"id": strategy_id},
            )
            .mappings()
            .fetchone()
        )

    if not row:
        raise ValueError(f"No strategy found with id {strategy_id}")

    return StrategyRecord(**row)


def by_key(strategy_key: str) -> StrategyRecord:
    db_engine = get_engine()
    with db_engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT strategy_id, strategy_key, universe, engine, primary_granularity, family FROM dim_strategy WHERE strategy_key = :key"
                ),
                {"key": strategy_key},
            )
            .mappings()
            .fetchone()
        )

    if not row:
        raise ValueError(f"No strategy found with key '{strategy_key}'")

    return StrategyRecord(**row)


def instantiate(record: StrategyRecord) -> Any:
    if record.universe == "legacy":
        from src.layer0.qualification.qualify_strategies import get_all_strategies

        strats = get_all_strategies()
        for s in strats:
            if getattr(s, "config", None) and s.config.name == record.strategy_key:
                return s
        raise ValueError(
            f"Legacy strategy {record.strategy_key} not found in get_all_strategies()"
        )

    elif record.universe == "v2_research":
        from src.layer0.strategies.v2_harness import discover

        classes = discover()
        if record.strategy_key not in classes:
            raise ValueError(
                f"v2 strategy {record.strategy_key} not found in discover()"
            )
        obj = classes[record.strategy_key]
        return obj

    elif record.universe == "regime_aware_port":
        import importlib
        import pkgutil
        import src.regime_aware.strategies

        for _, name, _ in pkgutil.iter_modules(src.regime_aware.strategies.__path__):
            mod = importlib.import_module(f"src.regime_aware.strategies.{name}")
            if hasattr(mod, "build_regime_aware"):
                strat = mod.build_regime_aware()
                if (
                    getattr(strat, "config", None)
                    and strat.config.name == record.strategy_key
                ):
                    return strat
        raise ValueError(f"Regime aware port {record.strategy_key} not found")

    else:
        raise ValueError(f"Unknown universe {record.universe}")
