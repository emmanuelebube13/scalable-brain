"""
Layer 2 Signal Generation Engine
================================

A data-driven, modular, vectorized signal generation system for quantitative trading.

This package provides:
- Database-driven strategy configuration (no hardcoded strategies)
- Lazy indicator calculation with dependency tracking
- Vectorized signal generation using pandas and ta library
- Idempotent bulk persistence with MERGE pattern
- Comprehensive audit logging and traceability

Architecture:
-------------
    config/         - Configuration loading and validation
    indicators/     - Indicator calculation engine with dependency graph
    rules/          - Rule evaluation engine for signal generation
    persistence/    - Database persistence with bulk MERGE operations
    core/           - Main orchestration and pipeline execution

Usage:
------
    from signal_engine import SignalEngine
    
    engine = SignalEngine()
    engine.run(asset_ids=[5, 6, 7], granularities=['H1', 'H4'])
"""

__version__ = "2.0.0"
__author__ = "Quant Infrastructure Team"

from signal_engine.core.engine import SignalEngine
from signal_engine.config.settings import Settings
from signal_engine.indicators.calculator import IndicatorCalculator
from signal_engine.rules.evaluator import RuleEvaluator
from signal_engine.persistence.repository import SignalRepository

__all__ = [
    "SignalEngine",
    "Settings", 
    "IndicatorCalculator",
    "RuleEvaluator",
    "SignalRepository",
]
