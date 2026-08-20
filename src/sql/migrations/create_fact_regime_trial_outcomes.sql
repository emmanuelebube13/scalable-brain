CREATE TABLE IF NOT EXISTS fact_regime_trial_outcomes (
    "timestamp" timestamp with time zone NOT NULL,
    asset_id integer NOT NULL,
    granularity varchar NOT NULL,
    trade_horizon varchar,
    is_winner integer,
    r_multiple double precision,
    holding_bars integer,
    atr_sl_multiplier double precision,
    atr_tp_multiplier double precision,
    entry_signal_type varchar,
    exit_reason varchar,
    created_at timestamp with time zone DEFAULT now(),
    is_oos boolean,
    fold_id integer,
    
    arm varchar NOT NULL CHECK (arm IN ('blind', 'aware')),
    regime_at_entry varchar NOT NULL,
    -- 'structural' added 2026-08-16: a rule-based four-state label (ADX for trend
    -- strength, rolling Z-score of ATR% for volatility). It exists because 'd1_trend'
    -- emits only Trending-Up/Down/UNKNOWN and therefore cannot express a four-state
    -- family mask at all — under it the gate was a no-op in every cell.
    regime_source varchar NOT NULL
        CHECK (regime_source IN ('d1_trend', 'hmm_causal', 'structural')),
    run_id varchar NOT NULL,
    strategy_key varchar NOT NULL,
    mask_applied jsonb,
    engine varchar NOT NULL CHECK (engine IN ('position_engine_v2', 'backtest_engine_v1')),
    
    leg_index integer NOT NULL DEFAULT 0,
    is_terminal_leg boolean NOT NULL DEFAULT true,

    -- regime_source is part of the key: the same trade is evaluated under BOTH label
    -- sources, so without it the d1_trend and hmm_causal rows for one trade collide and
    -- the second source silently cannot be stored. leg_index is here so the scale-out
    -- legs the columns already allow for do not need a key change later.
    PRIMARY KEY (run_id, strategy_key, asset_id, granularity, "timestamp", arm,
                 regime_source, leg_index)
);
