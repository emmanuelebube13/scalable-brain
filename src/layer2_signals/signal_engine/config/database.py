"""
Database connection management with connection pooling and error handling.
"""

import logging
import pyodbc
from contextlib import contextmanager
from typing import Optional, Generator

from signal_engine.config.settings import Settings

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Manages SQL Server database connections with proper resource handling.
    
    Uses context managers to ensure connections are always closed properly,
    even in the event of exceptions.
    
    Example:
        db = DatabaseConnection(settings)
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM Dim_Strategy")
            results = cursor.fetchall()
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize database connection manager.
        
        Args:
            settings: Application settings with database credentials
        """
        self.settings = settings
        self._connection_string = settings.get_connection_string()
        self._connection: Optional[pyodbc.Connection] = None
    
    def connect(self) -> pyodbc.Connection:
        """
        Establish database connection.
        
        Returns:
            Active database connection
            
        Raises:
            pyodbc.Error: If connection fails
        """
        try:
            conn = pyodbc.connect(self._connection_string, timeout=30)
            logger.debug("Database connection established")
            return conn
        except pyodbc.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    @contextmanager
    def cursor(self, fast_executemany: bool = True) -> Generator[pyodbc.Cursor, None, None]:
        """
        Get a database cursor with automatic cleanup.
        
        Args:
            fast_executemany: Enable fast_executemany for bulk operations
            
        Yields:
            Database cursor
        """
        conn = None
        cursor = None
        
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            if fast_executemany:
                cursor.fast_executemany = True
            
            yield cursor
            conn.commit()
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                logger.debug("Database connection closed")
    
    @contextmanager
    def connection(self) -> Generator[pyodbc.Connection, None, None]:
        """
        Get a raw database connection with automatic cleanup.
        
        Yields:
            Database connection
        """
        conn = None
        
        try:
            conn = self.connect()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def test_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            with self.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            params: Optional query parameters
            
        Returns:
            List of result rows
        """
        with self.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
    
    def execute_many(self, query: str, params_list: list) -> int:
        """
        Execute a query multiple times with different parameters.
        
        Args:
            query: SQL query string with placeholders
            params_list: List of parameter tuples
            
        Returns:
            Number of rows affected
        """
        with self.cursor(fast_executemany=True) as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount
