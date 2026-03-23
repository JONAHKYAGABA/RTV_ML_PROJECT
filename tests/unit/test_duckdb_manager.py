"""Unit tests for DuckDB manager."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.db.duckdb_manager import DuckDBManager


@pytest.fixture
def db_manager(tmp_path):
    """Create a DuckDBManager with a temporary database."""
    db_path = str(tmp_path / "test.duckdb")
    manager = DuckDBManager(db_path=db_path)
    yield manager
    manager.close()


class TestDuckDBManager:
    """Tests for database operations."""

    def test_connection(self, db_manager: DuckDBManager):
        """Test that connection is established lazily."""
        assert db_manager._conn is None
        conn = db_manager.conn
        assert conn is not None
        assert db_manager._conn is not None

    def test_close(self, db_manager: DuckDBManager):
        """Test connection cleanup."""
        _ = db_manager.conn
        db_manager.close()
        assert db_manager._conn is None

    def test_is_loaded_empty(self, db_manager: DuckDBManager):
        """Test is_loaded returns False on empty database."""
        assert db_manager.is_loaded() is False

    def test_execute_query_select(self, db_manager: DuckDBManager):
        """Test basic SELECT query execution."""
        db_manager.conn.execute("CREATE TABLE test (id INT, name VARCHAR)")
        db_manager.conn.execute("INSERT INTO test VALUES (1, 'alice'), (2, 'bob')")

        result = db_manager.execute_query("SELECT * FROM test ORDER BY id")
        assert result["success"] is True
        assert result["row_count"] == 2
        assert result["columns"] == ["id", "name"]
        assert result["rows"][0] == (1, "alice")

    def test_execute_query_blocks_writes(self, db_manager: DuckDBManager):
        """Test that write operations are blocked."""
        for stmt in ["DROP TABLE test", "DELETE FROM test", "UPDATE test SET x=1"]:
            result = db_manager.execute_query(stmt)
            assert result["success"] is False
            assert "not allowed" in result["error"].lower()

    def test_execute_query_handles_errors(self, db_manager: DuckDBManager):
        """Test that SQL errors are caught gracefully."""
        result = db_manager.execute_query("SELECT * FROM nonexistent_table")
        assert result["success"] is False
        assert result["error"] is not None

    def test_load_excel_data(self, db_manager: DuckDBManager):
        """Test loading Excel data (requires test data file)."""
        excel_path = Path(__file__).resolve().parents[2] / "Test Data 2026-03-17-12-43.xlsx"
        if not excel_path.exists():
            pytest.skip("Test data file not available")

        count = db_manager.load_excel_data(excel_path)
        assert count > 0
        assert db_manager.is_loaded() is True

    def test_get_schema_description(self, db_manager: DuckDBManager):
        """Test schema description generation."""
        excel_path = Path(__file__).resolve().parents[2] / "Test Data 2026-03-17-12-43.xlsx"
        if not excel_path.exists():
            pytest.skip("Test data file not available")

        db_manager.load_excel_data(excel_path)
        schema = db_manager.get_schema_description()
        assert "households" in schema
        assert "household_id" in schema
        assert "predicted_income" in schema
