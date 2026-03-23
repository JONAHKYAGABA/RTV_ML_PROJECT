"""
DuckDB database manager for loading and querying household data.

Handles:
  - Excel data ingestion into DuckDB
  - Schema introspection for the SQL agent
  - Query execution with parameterized safety
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from config.settings import get_settings

logger = logging.getLogger(__name__)

EXCEL_PATH = Path(__file__).resolve().parents[2] / "Test Data 2026-03-17-12-43.xlsx"
TABLE_NAME = "households"


class DuckDBManager:
    """Manages DuckDB connection lifecycle and query execution."""

    def __init__(self, db_path: str | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or str(settings.duckdb_abs_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            logger.info("Connected to DuckDB at %s", self._db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Data Ingestion
    # ------------------------------------------------------------------

    def load_excel_data(self, excel_path: str | Path | None = None) -> int:
        """Load the RTV household Excel dataset into DuckDB.

        Returns the number of rows loaded.
        """
        path = Path(excel_path) if excel_path else EXCEL_PATH
        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        logger.info("Loading data from %s ...", path)
        df = pd.read_excel(path, sheet_name="Test Data")

        # Normalize column names for SQL compatibility
        df.columns = [c.strip().lower() for c in df.columns]

        # Ensure boolean columns are proper booleans
        bool_cols = [
            "cassava", "maize", "ground_nuts", "irish_potatoes",
            "sweet_potatoes", "perennial_crops_grown_food_banana",
            "business_participation", "vsla_participation", "prediction",
        ]
        for col in bool_cols:
            if col in df.columns:
                df[col] = df[col].astype(bool)

        # Convert created_at to string (it comes as mixed format)
        if "created_at" in df.columns:
            df["created_at"] = df["created_at"].astype(str)

        # Drop existing table and recreate
        self.conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        self.conn.register("_tmp_df", df)
        self.conn.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM _tmp_df")
        self.conn.unregister("_tmp_df")

        row_count = self.conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        logger.info("Loaded %d rows into '%s'", row_count, TABLE_NAME)
        return row_count

    def is_loaded(self) -> bool:
        """Check if household data is already in the database."""
        try:
            result = self.conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_name = '{TABLE_NAME}'"
            ).fetchone()
            return result is not None and result[0] > 0
        except Exception:
            return False

    def ensure_loaded(self) -> int:
        """Load data if not already present. Returns row count."""
        if not self.is_loaded():
            return self.load_excel_data()
        return self.conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    # ------------------------------------------------------------------
    # Schema Introspection
    # ------------------------------------------------------------------

    def get_schema_description(self) -> str:
        """Return a human-readable schema description for the SQL agent."""
        if not self.is_loaded():
            return "No data loaded. Call ensure_loaded() first."

        cols = self.conn.execute(
            f"DESCRIBE {TABLE_NAME}"
        ).fetchdf()

        sample = self.conn.execute(
            f"SELECT * FROM {TABLE_NAME} LIMIT 3"
        ).fetchdf()

        stats = self.conn.execute(f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT household_id) as unique_households,
                COUNT(DISTINCT district) as unique_districts,
                COUNT(DISTINCT region) as unique_regions,
                COUNT(DISTINCT village) as unique_villages,
                COUNT(DISTINCT cluster) as unique_clusters,
                MIN(date) as min_date,
                MAX(date) as max_date
            FROM {TABLE_NAME}
        """).fetchdf()

        schema_text = f"""
DATABASE: DuckDB (OLAP-optimized)
TABLE: {TABLE_NAME}
TOTAL ROWS: {stats['total_rows'].iloc[0]:,}
UNIQUE HOUSEHOLDS: {stats['unique_households'].iloc[0]:,}

COLUMNS:
"""
        for _, row in cols.iterrows():
            schema_text += f"  - {row['column_name']:45s} {row['column_type']}\n"

        schema_text += f"""
COLUMN DESCRIPTIONS:
  - id: Auto-increment primary key
  - household_id: Structured string (e.g., 'RUB-NTA-EZE-M-153334-7') - NOT numeric
  - district: Administrative district name (22 unique)
  - village: Village name (1,040 unique)
  - cluster: Cluster of neighboring villages (146 unique)
  - region: Geographic region (5 unique: South West, Mid West, North, Central, East)
  - cohort: Launch year of the cluster group (2023, 2024, 2025)
  - cycle: Activity period ('A' or 'B')
  - evaluation_month: Months since program start when evaluation occurred (6, 9, 12, 18, 23)
  - cassava/maize/ground_nuts/irish_potatoes/sweet_potatoes: BOOLEAN - if household grows this crop
  - perennial_crops_grown_food_banana: BOOLEAN - if household grows food banana
  - tot_hhmembers: Total household members (integer, 0-20)
  - business_participation: BOOLEAN - if any member participates in business
  - land_size_for_crop_agriculture_acres: Land size in acres (integer, 0-99, NOTE: max=99 likely 'unknown')
  - farm_implements_owned: Count of farm tools (integer, 0-30000, WARNING: extreme outliers, use PERCENTILE_CONT)
  - vsla_participation: BOOLEAN - Village Savings and Loan Association participation
  - average_water_consumed_per_day: Water consumption in JERRYCANS per day (NOT liters, ~20L/jerrycan)
  - prediction: BOOLEAN - if household is predicted to hit income target
  - predicted_income: Float - predicted income + production value for household
  - date: Date of data collection (DATE type)
  - created_at: Timestamp of database entry (VARCHAR)

DATA QUALITY NOTES:
  - farm_implements_owned has extreme outliers (max=30,000, IQR=[3,5])
    Always filter with WHERE farm_implements_owned < 100 or use PERCENTILE_CONT
  - land_size max=99 may encode 'unknown' - consider filtering > 50
  - Water consumption is in JERRYCANS (1 jerrycan ~ 20 liters)
  - Some household_ids appear multiple times (multi-cycle evaluations)

DATE RANGE: {stats['min_date'].iloc[0]} to {stats['max_date'].iloc[0]}
REGIONS: South West ({stats['unique_districts'].iloc[0]} districts), Mid West, North, Central, East

SAMPLE ROWS:
{sample.head(3).to_string(index=False)}
"""
        return schema_text.strip()

    # ------------------------------------------------------------------
    # Query Execution
    # ------------------------------------------------------------------

    def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute a SQL query and return results as a dictionary.

        Returns:
            {
                "columns": list of column names,
                "rows": list of row tuples,
                "row_count": number of rows returned,
                "success": True/False,
                "error": error message if failed,
            }
        """
        # Basic SQL injection prevention
        sql_upper = sql.upper().strip()
        dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]
        for keyword in dangerous:
            if sql_upper.startswith(keyword):
                return {
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "success": False,
                    "error": f"Write operations are not allowed. Received: {keyword}",
                }

        try:
            result = self.conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "success": True,
                "error": None,
            }
        except Exception as e:
            logger.error("SQL execution error: %s\nQuery: %s", e, sql)
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "success": False,
                "error": str(e),
            }

    def query_to_dataframe(self, sql: str) -> pd.DataFrame:
        """Execute a query and return results as a pandas DataFrame."""
        return self.conn.execute(sql).fetchdf()
