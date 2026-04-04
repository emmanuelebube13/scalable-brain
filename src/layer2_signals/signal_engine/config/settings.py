"""
Configuration settings management for the signal engine.

Loads environment variables from .env file and provides typed access
to all configuration parameters with sensible defaults.
"""

import os
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """
    Application settings loaded from environment variables.
    
    Attributes:
        db_server: SQL Server hostname
        db_name: Database name
        db_user: Database username
        db_password: Database password
        db_driver: ODBC driver name
        batch_size: Bulk insert batch size
        log_level: Logging level
        asset_symbols: Mapping of Asset_ID to symbol names
    """
    
    # Database connection
    db_server: str
    db_user: str
    db_password: str
    db_name: str = "ForexBrainDB"
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_encrypt: str = "yes"
    db_trust_server_certificate: str = "yes"
    
    # Processing settings
    batch_size: int = 5000
    max_warmup_period: int = 250  # Maximum indicator warmup period to fetch
    
    # Logging
    log_level: str = "INFO"
    
    # Asset symbols for display
    asset_symbols: dict = field(default_factory=lambda: {
        1: "EUR_USD",
        2: "GBP_USD", 
        3: "USD_JPY",
        4: "AUD_USD",
        5: "USD_CAD"
    })
    
    # Supported granularities
    supported_granularities: List[str] = field(default_factory=lambda: [
        "M1", "M5", "M15", "M30", "H1", "H2", "H4", "H8", "D1", "W1"
    ])
    
    @classmethod
    def from_env(cls, env_path: Optional[str] = None) -> "Settings":
        """
        Load settings from environment variables.
        
        Args:
            env_path: Optional path to .env file. If None, searches from
                     current directory up to repo root.
        
        Returns:
            Settings instance with loaded configuration
            
        Raises:
            FileNotFoundError: If .env file cannot be found
            ValueError: If required environment variables are missing
        """
        # Find and load .env file
        if env_path is None:
            env_path = cls._find_env_file()
        
        if env_path and Path(env_path).exists():
            load_dotenv(env_path, override=True)
            logger.info(f"Loaded environment from: {env_path}")
        else:
            logger.warning("No .env file found, using existing environment variables")
        
        # Required variables
        required_vars = ["DB_SERVER", "DB_USER", "DB_PASS"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        
        settings = cls(
            db_server=os.getenv("DB_SERVER"),
            db_name=os.getenv("DB_NAME", "ForexBrainDB"),
            db_user=os.getenv("DB_USER"),
            db_password=os.getenv("DB_PASS"),
            db_driver=os.getenv("DB_DRIVER") or cls._detect_odbc_driver(),
            db_encrypt=os.getenv("DB_ENCRYPT", "yes"),
            db_trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes"),
            batch_size=int(os.getenv("BATCH_SIZE", "5000")),
            max_warmup_period=int(os.getenv("MAX_WARMUP_PERIOD", "250")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
        
        logger.info(f"Settings loaded: DB_SERVER={settings.db_server}, DB_NAME={settings.db_name}")
        return settings
    
    @staticmethod
    def _find_env_file() -> Optional[str]:
        """
        Search for .env file from current directory up to repo root.
        
        Returns:
            Path to .env file if found, None otherwise
        """
        current = Path.cwd()
        
        # Search up to 8 levels up (enough to reach repo root from nested src folders)
        for _ in range(8):
            env_file = current / ".env"
            if env_file.exists():
                return str(env_file)

            # Stop at filesystem root
            if current.parent == current:
                break

            current = current.parent
        
        return None

    @staticmethod
    def _detect_odbc_driver() -> str:
        """Detect an installed SQL Server ODBC driver, with safe defaults."""
        preferred = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "FreeTDS",
        ]

        try:
            output = subprocess.check_output(["odbcinst", "-q", "-d"], text=True)
            installed = {line.strip().strip("[]") for line in output.splitlines() if line.strip()}
            for name in preferred:
                if name in installed:
                    return name
        except Exception:
            pass

        return "ODBC Driver 18 for SQL Server"
    
    def get_connection_string(self) -> str:
        """
        Build SQL Server connection string.
        
        Returns:
            ODBC connection string
        """
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_server};"
            f"DATABASE={self.db_name};"
            f"UID={self.db_user};"
            f"PWD={self.db_password};"
            f"Encrypt={self.db_encrypt};"
            f"TrustServerCertificate={self.db_trust_server_certificate}"
        )
    
    def get_symbol(self, asset_id: int) -> str:
        """Get symbol name for asset ID."""
        return self.asset_symbols.get(asset_id, f"Asset_{asset_id}")
