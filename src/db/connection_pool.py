"""
DuckDB connection pool for concurrent read access.

DuckDB supports a single writer but multiple concurrent readers.
This pool manages read-only connections for parallel query execution
with timeout enforcement and health monitoring.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from queue import Queue, Empty
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe DuckDB connection pool.

    Args:
        db_path: Path to the DuckDB database file.
        pool_size: Maximum number of connections in the pool.
        query_timeout: Default query timeout in seconds.
    """

    def __init__(
        self,
        db_path: str,
        pool_size: int = 5,
        query_timeout: int = 5,
    ) -> None:
        self._db_path = db_path
        self._pool_size = pool_size
        self._query_timeout = query_timeout
        self._pool: Queue[duckdb.DuckDBPyConnection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created = 0

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a new DuckDB connection."""
        conn = duckdb.connect(self._db_path, read_only=True)
        self._created += 1
        logger.debug(
            "Created DuckDB connection #%d (pool_size=%d)",
            self._created,
            self._pool_size,
        )
        return conn

    def acquire(self, timeout: float = 5.0) -> duckdb.DuckDBPyConnection:
        """Acquire a connection from the pool.

        Creates a new connection if the pool is empty and under capacity.
        Blocks up to ``timeout`` seconds waiting for an available connection.
        """
        try:
            return self._pool.get_nowait()
        except Empty:
            pass

        with self._lock:
            if self._created < self._pool_size:
                return self._create_connection()

        try:
            return self._pool.get(timeout=timeout)
        except Empty:
            raise TimeoutError(
                f"Could not acquire DuckDB connection within {timeout}s "
                f"(pool exhausted, size={self._pool_size})"
            )

    def release(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Return a connection to the pool."""
        try:
            self._pool.put_nowait(conn)
        except Exception:
            # Pool is full -- close the extra connection
            try:
                conn.close()
            except Exception:
                pass

    def execute_query(
        self,
        sql: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute a read-only query using a pooled connection.

        Returns a dict with columns, rows, row_count, success, error.
        """
        timeout = timeout or self._query_timeout
        conn = self.acquire()
        start = time.time()

        try:
            result = conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            elapsed_ms = int((time.time() - start) * 1000)

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_ms": elapsed_ms,
                "success": True,
                "error": None,
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.error("Query failed after %dms: %s\nSQL: %s", elapsed_ms, e, sql)
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_ms": elapsed_ms,
                "success": False,
                "error": str(e),
            }
        finally:
            self.release(conn)

    def health_check(self) -> dict[str, Any]:
        """Check pool health and connectivity."""
        try:
            conn = self.acquire(timeout=2.0)
            try:
                result = conn.execute("SELECT 1").fetchone()
                return {
                    "healthy": True,
                    "pool_size": self._pool_size,
                    "connections_created": self._created,
                    "available": self._pool.qsize(),
                }
            finally:
                self.release(conn)
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "pool_size": self._pool_size,
                "connections_created": self._created,
            }

    def close_all(self) -> None:
        """Close all connections in the pool."""
        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                closed += 1
            except Empty:
                break
            except Exception:
                pass
        logger.info("Closed %d pooled connections", closed)
