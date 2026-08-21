import logging
from sqlalchemy import text
from src.common.db import get_engine

logger = logging.getLogger(__name__)

VALID_UNIVERSES = {"legacy", "v2_research", "regime_aware_port"}
VALID_ENGINES = {"backtest_engine_v1", "position_engine_v2"}


def ensure_strategy_id(
    strategy_key: str,
    *,
    universe: str,
    engine: str,
    primary_granularity: str,
    family: str | None,
) -> int:
    """
    Returns the strategy_id for a given strategy_key.
    If it does not exist, allocates max(strategy_id) + 1 atomically.
    """
    if universe not in VALID_UNIVERSES:
        raise ValueError(
            f"Unknown universe '{universe}'. Valid choices: {VALID_UNIVERSES}"
        )

    if engine not in VALID_ENGINES:
        raise ValueError(f"Unknown engine '{engine}'. Valid choices: {VALID_ENGINES}")

    db_engine = get_engine()

    with db_engine.begin() as conn:
        # First check if it already exists
        sel_sql = text("SELECT strategy_id FROM dim_strategy WHERE strategy_key = :key")
        result = conn.execute(sel_sql, {"key": strategy_key}).fetchone()

        if result is not None:
            return int(result[0])

        # Lock the table to prevent concurrent allocation of the same ID
        conn.execute(text("LOCK TABLE dim_strategy IN EXCLUSIVE MODE"))

        # Check again under lock just in case it was created concurrently
        result = conn.execute(sel_sql, {"key": strategy_key}).fetchone()
        if result is not None:
            return int(result[0])

        # Get next id
        max_id_sql = text("SELECT COALESCE(MAX(strategy_id), 0) FROM dim_strategy")
        next_id = conn.execute(max_id_sql).scalar() + 1

        # Insert
        ins_sql = text("""
            INSERT INTO dim_strategy (
                strategy_id, strategy_key, strategy_name, universe, 
                engine, primary_granularity, family, registered_at_utc,
                is_active
            ) VALUES (
                :id, :key, :name, :universe, :engine, :gran, :family, CURRENT_TIMESTAMP, true
            )
        """)
        conn.execute(
            ins_sql,
            {
                "id": next_id,
                "key": strategy_key,
                "name": strategy_key,  # For legacy reasons, populate strategy_name too
                "universe": universe,
                "engine": engine,
                "gran": primary_granularity,
                "family": family,
            },
        )

        # We must also ensure it exists in dim_strategy_registry due to FK constraints on outcomes
        ins_reg_sql = text("""
            INSERT INTO dim_strategy_registry (strategy_id, strategy_name)
            VALUES (:id, :name)
            ON CONFLICT (strategy_id) DO NOTHING
        """)
        conn.execute(ins_reg_sql, {"id": next_id, "name": strategy_key})

        logger.info(
            f"Allocated strategy_id {next_id} for strategy_key '{strategy_key}'"
        )
        return int(next_id)


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Allocate strategy IDs for all universes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be allocated without saving",
    )
    args = parser.parse_args()

    # 1. legacy
    from src.layer0.qualification.qualify_strategies import get_all_strategies

    legacy_strats = get_all_strategies()

    # 2. v2
    from src.layer0.strategies.v2_harness import discover

    v2_classes = discover()

    # 3. ports
    import importlib, pkgutil
    import src.regime_aware.strategies

    port_strats = []
    for _, name, _ in pkgutil.iter_modules(src.regime_aware.strategies.__path__):
        mod = importlib.import_module(f"src.regime_aware.strategies.{name}")
        if hasattr(mod, "build_regime_aware"):
            strat = mod.build_regime_aware()
            port_strats.append((strat.config.name, name))

    print(f"{'KEY':<40} | {'ID':<4} | {'UNIVERSE':<20} | {'ENGINE':<20}")
    print("-" * 90)

    count = 0

    def process_strat(key, universe, engine, gran, family):
        global count
        if args.dry_run:
            print(f"{key:<40} | {'--':<4} | {universe:<20} | {engine:<20}")
        else:
            sid = ensure_strategy_id(
                key,
                universe=universe,
                engine=engine,
                primary_granularity=gran,
                family=family,
            )
            print(f"{key:<40} | {sid:<4} | {universe:<20} | {engine:<20}")
        count += 1

    for s in legacy_strats:
        process_strat(
            s.config.name,
            "legacy",
            "backtest_engine_v1",
            getattr(s.config, "granularity", "H1"),
            None,
        )

    for k in v2_classes.keys():
        process_strat(k, "v2_research", "position_engine_v2", "H4", None)

    for name, family in port_strats:
        process_strat(name, "regime_aware_port", "backtest_engine_v1", "H4", family)

    print("-" * 90)
    print(f"Total strategies: {count}")
