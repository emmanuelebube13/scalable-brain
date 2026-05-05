"""
Signal Engine - Main orchestration for signal generation.

Coordinates the entire signal generation pipeline:
1. Load active strategies from database
2. Fetch price data for each asset/granularity
3. Calculate required indicators (lazy evaluation)
4. Evaluate signal rules
5. Persist results with audit metadata
"""

import logging
import time
import uuid
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import pandas as pd
import numpy as np

from signal_engine.config.settings import Settings
from signal_engine.config.database import DatabaseConnection
from signal_engine.indicators.calculator import IndicatorCalculator
from signal_engine.rules.evaluator import RuleEvaluator
from signal_engine.persistence.repository import SignalRepository
from signal_engine.persistence.processing_tracker import ProcessingTracker
from signal_engine.core.models import StrategyConfig, SignalResult, ProcessingSummary

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Main signal generation engine.
    
    Orchestrates the entire signal generation pipeline from configuration
    loading through persistence. Fully data-driven with no hardcoded strategies.
    
    Example:
        engine = SignalEngine()
        summary = engine.run(
            asset_ids=[5, 6, 7],
            granularities=['H1', 'H4']
        )
        print(f"Generated {summary.total_signals} signals")
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the signal engine.
        
        Args:
            settings: Optional settings (loads from env if not provided)
        """
        self.settings = settings or Settings.from_env()
        self.db = DatabaseConnection(self.settings)
        self.repository = SignalRepository(self.db, self.settings)
        self.tracker = ProcessingTracker(self.db, self.settings)
        
        logger.info("Initialized SignalEngine")
    
    def run(
        self,
        asset_ids: Optional[List[int]] = None,
        granularities: Optional[List[str]] = None,
        strategy_ids: Optional[List[int]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        dry_run: bool = False,
        incremental: bool = True,
        current_hour_only: bool = True
    ) -> ProcessingSummary:
        """
        Run the signal generation pipeline.
        
        Args:
            asset_ids: Optional list of asset IDs to process (all if None)
            granularities: Optional list of granularities (all if None)
            strategy_ids: Optional list of strategy IDs (all active if None)
            start_date: Optional start date filter (overrides incremental if provided)
            end_date: Optional end date filter
            dry_run: If True, don't persist to database
            incremental: If True, only process new data since last run
            current_hour_only: If True, only generate signals for current hour
            
        Returns:
            ProcessingSummary with results
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())[:8]
        
        logger.info("=" * 70)
        logger.info("LAYER 2: Signal Generation Pipeline")
        logger.info("=" * 70)
        logger.info(f"Batch ID: {batch_id}")
        logger.info(f"Dry run: {dry_run}")
        logger.info(f"Incremental: {incremental}")
        logger.info(f"Current hour only: {current_hour_only}")
        
        # Default to supported granularities
        if granularities is None:
            granularities = ['H1', 'H4']
        
        errors = []
        total_signals = 0
        processed_strategies = 0
        processed_assets = set()
        
        try:
            # Process each granularity
            for granularity in granularities:
                logger.info(f"\nProcessing granularity: {granularity}")
                
                # Get active strategies for this granularity
                strategies = self._load_strategies(
                    asset_ids=asset_ids,
                    granularity=granularity,
                    strategy_ids=strategy_ids
                )
                
                if not strategies:
                    available_grans = self._list_active_granularities(
                        asset_ids=asset_ids,
                        strategy_ids=strategy_ids,
                    )
                    if available_grans:
                        logger.warning(
                            "No active strategies for %s. Active granularities in DB: %s",
                            granularity,
                            ", ".join(available_grans),
                        )
                    else:
                        logger.warning(
                            "No active strategies found in DB for current filters. "
                            "Ensure Layer 0 SQL promotion scripts were applied in order."
                        )
                    continue
                
                logger.info(f"Found {len(strategies)} active strategy configurations")
                logger.debug(f"Strategy details: {[(s.strategy_id, s.asset_id, s.strategy_name) for s in strategies]}")
                
                # Group strategies by asset for efficient processing
                strategies_by_asset = self._group_by_asset(strategies)
                logger.debug(f"Grouped into {len(strategies_by_asset)} unique assets")
                
                # Track processing updates for batch commit
                processing_updates = []
                
                # Process each asset
                logger.debug(f"Starting asset processing loop with {len(strategies_by_asset)} assets")
                for asset_id, asset_strategies in strategies_by_asset.items():
                    symbol = self.settings.get_symbol(asset_id)
                    logger.info(f"\n  Processing {symbol} (Asset_ID: {asset_id}) with {len(asset_strategies)} strategies")
                    
                    # Calculate the start date for incremental processing
                    strategy_start_dates = {}
                    if incremental and start_date is None:
                        for strategy_config in asset_strategies:
                            calc_start = self.tracker.calculate_start_date(
                                asset_id=asset_id,
                                granularity=granularity,
                                strategy_id=strategy_config.strategy_id,
                                lookback_bars=5  # Look back 5 bars for indicator warmup
                            )
                            strategy_start_dates[strategy_config.strategy_id] = calc_start
                    
                    try:
                        # Fetch price data - use earliest start date across strategies
                        fetch_start_date = start_date
                        if incremental and not start_date and strategy_start_dates:
                            # Use the minimum (earliest) start date across all strategies
                            valid_starts = [s for s in strategy_start_dates.values() if s is not None]
                            if valid_starts:
                                fetch_start_date = min(valid_starts)
                        
                        df = self._fetch_price_data(
                            asset_id=asset_id,
                            granularity=granularity,
                            start_date=fetch_start_date,
                            end_date=end_date
                        )
                        
                        if df.empty:
                            logger.warning(f"    No price data for {symbol}")
                            continue
                        
                        logger.info(f"    Loaded {len(df)} price bars (from {fetch_start_date or 'beginning'})")
                        processed_assets.add(asset_id)
                        
                        # Process each strategy for this asset
                        for strategy_config in asset_strategies:
                            try:
                                result = self._process_strategy(
                                    df=df,
                                    asset_id=asset_id,
                                    strategy_config=strategy_config,
                                    current_hour_only=current_hour_only
                                )
                                
                                if result.rows_generated > 0 and not dry_run:
                                    # Persist signals with deduplication
                                    persisted = self.repository.save_signals(
                                        signals_df=result.signals_df,
                                        strategy_version=result.config_version,
                                        config_hash=result.config_hash,
                                        batch_id=batch_id,
                                        asset_id=asset_id,
                                        granularity=granularity,
                                        strategy_id=strategy_config.strategy_id,
                                        validate_current_hour_only=current_hour_only
                                    )
                                    logger.info(
                                        f"    Persisted {persisted} signals for "
                                        f"{strategy_config.strategy_name}"
                                    )
                                    
                                    # Track processing state for successful inserts
                                    if persisted > 0:
                                        # Get the latest timestamp from the signals
                                        max_timestamp = result.signals_df['Timestamp'].max()
                                        processing_updates.append({
                                            'asset_id': asset_id,
                                            'granularity': granularity,
                                            'strategy_id': strategy_config.strategy_id,
                                            'timestamp': max_timestamp,
                                            'records_processed': persisted
                                        })
                                
                                total_signals += result.rows_generated
                                processed_strategies += 1
                                
                            except Exception as e:
                                error_msg = (
                                    f"Failed to process strategy "
                                    f"{strategy_config.strategy_id}: {e}"
                                )
                                logger.error(error_msg)
                                errors.append(error_msg)
                    
                    except Exception as e:
                        error_msg = f"Failed to process {symbol}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                
                # Update processing log for all successful strategies
                if processing_updates and not dry_run:
                    self.tracker.update_batch(processing_updates, batch_id=batch_id)
                    logger.debug(f"Updated processing log for {len(processing_updates)} strategy runs")
        
        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
        
        execution_time = (time.time() - start_time) * 1000
        
        logger.info("\n" + "=" * 70)
        logger.info("Pipeline Complete")
        logger.info("=" * 70)
        logger.info(f"Strategies processed: {processed_strategies}")
        logger.info(f"Assets processed: {len(processed_assets)}")
        logger.info(f"Total signals: {total_signals}")
        logger.info(f"Execution time: {execution_time:.2f}ms")
        
        if errors:
            logger.warning(f"Errors: {len(errors)}")
            for err in errors:
                logger.warning(f"  - {err}")
        
        return ProcessingSummary(
            total_strategies=processed_strategies,
            total_assets=len(processed_assets),
            total_signals=total_signals,
            execution_time_ms=execution_time,
            errors=errors,
            batch_id=batch_id
        )
    
    def _load_strategies(
        self,
        asset_ids: Optional[List[int]] = None,
        granularity: str = 'H1',
        strategy_ids: Optional[List[int]] = None
    ) -> List[StrategyConfig]:
        """
        Load active strategy configurations from database.
        
        Args:
            asset_ids: Optional filter by asset IDs
            granularity: Time granularity
            strategy_ids: Optional filter by strategy IDs
            
        Returns:
            List of StrategyConfig objects
        """
        query = """
            SELECT 
                s.Strategy_ID,
                s.Strategy_Key,
                s.Strategy_Name,
                c.Config_ID,
                c.Config_Version,
                c.Config_Hash,
                c.Granularity,
                c.Indicator_Configs,
                c.Signal_Rules,
                c.Risk_Filters,
                m.Asset_ID
            FROM Dim_Strategy s
            INNER JOIN Dim_Strategy_Config c ON s.Strategy_ID = c.Strategy_ID
            INNER JOIN Dim_Strategy_Asset_Mapping m ON c.Config_ID = m.Config_ID
            WHERE s.Is_Active = 1
                AND c.Is_Active = 1
                AND m.Is_Active = 1
                AND c.Granularity = %s
                AND (c.Effective_To IS NULL OR c.Effective_To > NOW())
                AND (m.Effective_To IS NULL OR m.Effective_To > NOW())
        """
        
        params = [granularity]
        
        if asset_ids:
            placeholders = ','.join(['?' for _ in asset_ids])
            query += f" AND m.Asset_ID IN ({placeholders})"
            params.extend(asset_ids)
        
        if strategy_ids:
            placeholders = ','.join(['?' for _ in strategy_ids])
            query += f" AND s.Strategy_ID IN ({placeholders})"
            params.extend(strategy_ids)
        
        query += " ORDER BY m.Priority, s.Strategy_ID"
        
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        
        strategies = []
        for row in rows:
            try:
                config = StrategyConfig.from_db_row(row, columns)
                
                # Validate configuration
                validation_errors = config.validate()
                if validation_errors:
                    logger.warning(
                        f"Strategy {config.strategy_id} validation failed: "
                        f"{validation_errors}"
                    )
                    continue
                
                strategies.append(config)
            except Exception as e:
                logger.error(f"Failed to parse strategy config: {e}")
        
        return strategies

    def _list_active_granularities(
        self,
        asset_ids: Optional[List[int]] = None,
        strategy_ids: Optional[List[int]] = None,
    ) -> List[str]:
        """Return distinct active granularities available for current filters."""
        query = """
            SELECT DISTINCT c.Granularity
            FROM Dim_Strategy s
            INNER JOIN Dim_Strategy_Config c ON s.Strategy_ID = c.Strategy_ID
            INNER JOIN Dim_Strategy_Asset_Mapping m ON c.Config_ID = m.Config_ID
            WHERE s.Is_Active = 1
                AND c.Is_Active = 1
                AND m.Is_Active = 1
                AND (c.Effective_To IS NULL OR c.Effective_To > NOW())
                AND (m.Effective_To IS NULL OR m.Effective_To > NOW())
        """

        params: List[Any] = []

        if asset_ids:
            placeholders = ','.join(['?' for _ in asset_ids])
            query += f" AND m.Asset_ID IN ({placeholders})"
            params.extend(asset_ids)

        if strategy_ids:
            placeholders = ','.join(['?' for _ in strategy_ids])
            query += f" AND s.Strategy_ID IN ({placeholders})"
            params.extend(strategy_ids)

        query += " ORDER BY c.Granularity"

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [str(row[0]) for row in rows if row and row[0] is not None]
    
    def _fetch_price_data(
        self,
        asset_id: int,
        granularity: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch price data from database.
        
        Args:
            asset_id: Asset identifier
            granularity: Time granularity
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            DataFrame with OHLCV data
        """
        query = """
            SELECT Timestamp, [Open], High, Low, [Close], Volume
            FROM Fact_Market_Prices
            WHERE Asset_ID = ? AND Granularity = ?
        """
        params = [asset_id, granularity]
        
        if start_date:
            query += " AND Timestamp >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND Timestamp <= ?"
            params.append(end_date)
        
        query += " ORDER BY Timestamp"
        
        with self.db.connection() as conn:
            df = pd.read_sql(query, conn, params=params, parse_dates=['Timestamp'])
        
        return df
    
    def _group_by_asset(
        self,
        strategies: List[StrategyConfig]
    ) -> Dict[int, List[StrategyConfig]]:
        """
        Group strategies by asset ID.
        
        Args:
            strategies: List of strategy configs
            
        Returns:
            Dictionary mapping asset_id to list of strategies
        """
        grouped = {}
        for strategy in strategies:
            asset_id = strategy.asset_id
            if asset_id not in grouped:
                grouped[asset_id] = []
            grouped[asset_id].append(strategy)
        
        logger.debug(f"Grouped {len(strategies)} strategies into {len(grouped)} assets")
        for asset_id, strategies_list in grouped.items():
            logger.debug(f"  Asset {asset_id}: {len(strategies_list)} strategies")
        
        return grouped
    
    def _process_strategy(
        self,
        df: pd.DataFrame,
        asset_id: int,
        strategy_config: StrategyConfig,
        current_hour_only: bool = True
    ) -> SignalResult:
        """
        Process a single strategy against price data.
        
        Args:
            df: DataFrame with price data
            asset_id: Asset identifier
            strategy_config: Strategy configuration
            current_hour_only: If True, only generate signals for current hour
            
        Returns:
            SignalResult with generated signals
        """
        start_time = time.time()
        
        logger.debug(
            f"Processing strategy {strategy_config.strategy_name} "
            f"(v{strategy_config.config_version})"
        )
        
        # Step 1: Build indicator calculator with required indicators
        calculator = IndicatorCalculator()
        calculator.add_configs_from_json(strategy_config.indicator_configs)
        
        # Step 2: Calculate indicators
        indicator_results = calculator.calculate(df)
        
        # Step 3: Build DataFrame with indicators
        df_with_indicators = df.copy()
        for name, series in indicator_results.items():
            df_with_indicators[name] = series
        
        # Drop warmup rows (NaN values)
        warmup_period = calculator.get_warmup_period()
        df_with_indicators = df_with_indicators.iloc[warmup_period:].copy()
        
        if df_with_indicators.empty:
            logger.warning("No data after removing warmup period")
            return SignalResult(
                strategy_id=strategy_config.strategy_id,
                config_id=strategy_config.config_id,
                config_version=strategy_config.config_version,
                config_hash=strategy_config.config_hash,
                granularity=strategy_config.granularity,
                signals_df=pd.DataFrame(),
                rows_generated=0,
                execution_time_ms=0
            )
        
        # Step 4: Evaluate signal rules
        evaluator = RuleEvaluator()
        evaluator.add_rules_from_json(strategy_config.signal_rules)
        
        # Validate rules against DataFrame
        validation_errors = evaluator.validate_against_dataframe(df_with_indicators)
        if validation_errors:
            raise ValueError(f"Rule validation failed: {validation_errors}")
        
        # Get consolidated signals
        signals = evaluator.evaluate_consolidated(df_with_indicators)
        
        # Get triggered rules for each row
        triggered_rules = evaluator.get_triggered_rules(df_with_indicators)
        
        # Step 5: Filter to current hour only if enabled
        if current_hour_only:
            from datetime import datetime
            now = datetime.utcnow()
            current_hour_start = now.replace(minute=0, second=0, microsecond=0)
            
            # Filter df_with_indicators to current hour only
            df_with_indicators = df_with_indicators[
                df_with_indicators['Timestamp'] >= current_hour_start
            ].copy()
            
            if df_with_indicators.empty:
                logger.debug(
                    f"No data for current hour after filtering. "
                    f"Strategy {strategy_config.strategy_id} will generate no signals."
                )
                return SignalResult(
                    strategy_id=strategy_config.strategy_id,
                    config_id=strategy_config.config_id,
                    config_version=strategy_config.config_version,
                    config_hash=strategy_config.config_hash,
                    granularity=strategy_config.granularity,
                    signals_df=pd.DataFrame(),
                    rows_generated=0,
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            # Recalculate signals for filtered data
            signals = evaluator.evaluate_consolidated(df_with_indicators)
            triggered_rules = evaluator.get_triggered_rules(df_with_indicators)
        
        # Step 6: Build result DataFrame
        result_df = pd.DataFrame({
            'Timestamp': df_with_indicators['Timestamp'],
            'Asset_ID': asset_id,
            'Granularity': strategy_config.granularity,
            'Strategy_ID': strategy_config.strategy_id,
            'Signal_Value': signals.values
        })
        
        # Add signal reason and rule ID
        signal_reasons = []
        rule_ids = []
        
        for idx, row in df_with_indicators.iterrows():
            # Find which rule triggered
            triggered = triggered_rules.loc[idx]
            triggered_rule_ids = triggered[triggered].index.tolist()
            
            if triggered_rule_ids:
                rule = evaluator.get_rule(triggered_rule_ids[0])
                signal_reasons.append(rule.description if rule else "")
                rule_ids.append(triggered_rule_ids[0])
            else:
                signal_reasons.append("")
                rule_ids.append("")
        
        result_df['Signal_Reason'] = signal_reasons
        result_df['Rule_ID'] = rule_ids
        
        # Add indicator snapshot (key indicators only, as JSON)
        snapshots = []
        for idx in df_with_indicators.index:
            snapshot = {}
            for indicator_name in indicator_results.keys():
                if indicator_name in df_with_indicators.columns:
                    val = df_with_indicators.loc[idx, indicator_name]
                    if pd.notna(val):
                        snapshot[indicator_name] = round(float(val), 6)
            snapshots.append(json.dumps(snapshot) if snapshot else None)
        
        result_df['Indicator_Snapshot'] = snapshots
        
        execution_time = (time.time() - start_time) * 1000
        rows_generated = (result_df['Signal_Value'] != 0).sum()
        
        logger.debug(
            f"Strategy {strategy_config.strategy_id}: "
            f"{rows_generated} signals in {execution_time:.2f}ms"
        )
        
        return SignalResult(
            strategy_id=strategy_config.strategy_id,
            config_id=strategy_config.config_id,
            config_version=strategy_config.config_version,
            config_hash=strategy_config.config_hash,
            granularity=strategy_config.granularity,
            signals_df=result_df,
            rows_generated=int(rows_generated),
            execution_time_ms=execution_time
        )
