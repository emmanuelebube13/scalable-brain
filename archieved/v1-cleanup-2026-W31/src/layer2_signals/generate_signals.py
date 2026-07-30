#!/usr/bin/env python3
"""
Layer 2 Signal Generation - Swing Trading Engine
================================================

🚀 SWING TRADING SYSTEM | Data-driven multi-timeframe swing trade signal generation

Data-driven, modular, vectorized signal generation engine for swing trading.
This script replaces legacy hardcoded signal generation with a fully
data-driven approach using database configuration for H1/H4 timeframes.

Usage:
    python generate_signals.py
    python generate_signals.py --assets 5 6 7 --granularities H1 H4
    python generate_signals.py --dry-run --log-level DEBUG

Environment:
    Requires .env file in repo root with:
        DB_SERVER=your_server
        DB_USER=your_user
        DB_PASS=your_password
        DB_NAME=ForexBrainDB
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from signal_engine import SignalEngine
from signal_engine.config.settings import Settings


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Configure logging with consistent formatting.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger
    """
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("psycopg2").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Layer 2 Signal Generation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run with defaults
  %(prog)s --assets 5 6                       # Process specific assets
  %(prog)s --granularities H1 H4              # Process multiple timeframes
  %(prog)s --dry-run                          # Preview without saving
  %(prog)s --log-level DEBUG                  # Verbose logging
        """,
    )

    parser.add_argument(
        "--assets",
        type=int,
        nargs="+",
        help="Asset IDs to process (default: all active)",
    )

    parser.add_argument(
        "--granularities",
        type=str,
        nargs="+",
        default=["H1", "H4"],
        help="Time granularities to process (default: H1 H4)",
    )

    parser.add_argument(
        "--strategies",
        type=int,
        nargs="+",
        help="Strategy IDs to process (default: all active)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Run without persisting to database"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--env-file", type=str, help="Path to .env file (default: auto-detect)"
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    # Setup logging
    logger = setup_logging(args.log_level)
    logger.info("=" * 70)
    logger.info("Layer 2 Signal Generation Engine v2.0")
    logger.info("=" * 70)

    try:
        # Load settings
        logger.info("Loading configuration...")
        settings = Settings.from_env(args.env_file)

        # Normalize and de-duplicate granularities while preserving order.
        granularities = list(dict.fromkeys(g.upper() for g in args.granularities))

        # Initialize engine
        engine = SignalEngine(settings)

        # Run pipeline
        summary = engine.run(
            asset_ids=args.assets,
            granularities=granularities,
            strategy_ids=args.strategies,
            dry_run=args.dry_run,
        )

        # Print summary
        logger.info("\n" + "=" * 70)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Batch ID:          {summary.batch_id}")
        logger.info(f"Strategies:        {summary.total_strategies}")
        logger.info(f"Assets:            {summary.total_assets}")
        logger.info(f"Signals Generated: {summary.total_signals}")
        logger.info(f"Execution Time:    {summary.execution_time_ms:.2f}ms")

        if summary.errors:
            logger.warning(f"Errors:            {len(summary.errors)}")
            for error in summary.errors:
                logger.warning(f"  - {error}")

        logger.info("=" * 70)

        return 0 if not summary.errors else 1

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
