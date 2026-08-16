import pytest
import pandas as pd
from src.regime_aware.tests.test_equivalence import _synthetic_frame, _run, _trade_tuples

# Import Donchian
from src.layer0.strategies.strategieStaged.trend_donchian import TrendDonchian_H1_Only, TrendDonchian_H4_Only
from src.regime_aware.strategies.donchian_h1 import build_baseline as donchian_h1_baseline, BASELINE as donchian_h1_b
from src.regime_aware.strategies.donchian_h4 import build_baseline as donchian_h4_baseline, BASELINE as donchian_h4_b

# Import EMA ADX
from src.layer0.strategies.strategieStaged.trend_ema_adx import TrendEMAADX_H1_Only, TrendEMAADX_H4_Only, TrendEMAADX_MultiTF
from src.regime_aware.strategies.ema_adx_h1 import build_baseline as ema_h1_baseline, BASELINE as ema_h1_b
from src.regime_aware.strategies.ema_adx_h4 import build_baseline as ema_h4_baseline, BASELINE as ema_h4_b
from src.regime_aware.strategies.ema_adx_multitf import build_baseline as ema_mtf_baseline, BASELINE as ema_mtf_b

# Import Bollinger
from src.layer0.strategies.strategieStaged.range_bollinger import RangeBollinger_H1_Only, RangeBollinger_H4_Only, RangeBollinger_Aggressive
from src.regime_aware.strategies.bollinger_h1 import build_baseline as boll_h1_baseline, BASELINE as boll_h1_b
from src.regime_aware.strategies.bollinger_h4 import build_baseline as boll_h4_baseline, BASELINE as boll_h4_b
from src.regime_aware.strategies.bollinger_aggressive import build_baseline as boll_agg_baseline, BASELINE as boll_agg_b

@pytest.fixture(scope="module")
def frame():
    return _synthetic_frame()

def test_donchian_h1_equivalence(frame):
    prod = TrendDonchian_H1_Only()
    ported = donchian_h1_baseline()
    
    assert donchian_h1_b.channel_period == prod.channel_period
    assert donchian_h1_b.stop_loss_atr == prod.config.stop_loss_atr
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_donchian_h4_equivalence(frame):
    prod = TrendDonchian_H4_Only()
    ported = donchian_h4_baseline()
    
    assert donchian_h4_b.channel_period == prod.channel_period
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_ema_h1_equivalence(frame):
    prod = TrendEMAADX_H1_Only()
    ported = ema_h1_baseline()
    
    assert ema_h1_b.fast_ema == prod.fast_ema
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_ema_h4_equivalence(frame):
    prod = TrendEMAADX_H4_Only()
    ported = ema_h4_baseline()
    
    assert ema_h4_b.fast_ema == prod.fast_ema
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_ema_mtf_equivalence(frame):
    prod = TrendEMAADX_MultiTF()
    ported = ema_mtf_baseline()
    
    assert ema_mtf_b.fast_ema == prod.fast_ema
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_boll_h1_equivalence(frame):
    prod = RangeBollinger_H1_Only()
    ported = boll_h1_baseline()
    
    assert boll_h1_b.bb_period == prod.bb_period
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_boll_h4_equivalence(frame):
    prod = RangeBollinger_H4_Only()
    ported = boll_h4_baseline()
    
    assert boll_h4_b.bb_period == prod.bb_period
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)

def test_boll_agg_equivalence(frame):
    prod = RangeBollinger_Aggressive()
    ported = boll_agg_baseline()
    
    assert boll_agg_b.bb_period == prod.bb_period
    
    prod_run = _run(prod, frame.copy())
    port_run = _run(ported, frame.copy())
    assert len(prod_run.trades) > 0
    assert _trade_tuples(port_run.trades) == _trade_tuples(prod_run.trades)
