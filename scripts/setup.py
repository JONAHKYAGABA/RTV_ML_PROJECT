"""
Setup script - Initializes the RTV ML system for first-time use.

Usage:
    python scripts/setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    print("=" * 60)
    print("  RTV Multi-Agent ML System - Setup")
    print("=" * 60)

    # Check .env
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        print("\n[!] .env file not found.")
        print("    Copy .env.example to .env and add your API keys:")
        print("    cp .env.example .env")
        return

    # Initialize database
    print("\n[1/3] Loading household data into DuckDB...")
    from src.db.duckdb_manager import DuckDBManager
    db = DuckDBManager()
    row_count = db.ensure_loaded()
    print(f"       Loaded {row_count:,} rows")

    # Initialize RAG
    print("\n[2/3] Initializing RAG pipeline...")
    try:
        from src.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        chunk_count = pipeline.initialize()
        print(f"       Indexed {chunk_count} document chunks")
    except FileNotFoundError as e:
        print(f"       Warning: {e}")
        print("       RAG pipeline will be available once the handbook is added.")

    # Verify
    print("\n[3/3] Verifying setup...")
    schema = db.get_schema_description()
    print(f"       Database schema: {len(schema)} chars")
    print(f"       Sample query: ", end="")
    result = db.execute_query("SELECT COUNT(*) as n, region FROM households GROUP BY region ORDER BY n DESC LIMIT 3")
    if result["success"]:
        for row in result["rows"]:
            print(f"{row[1]}={row[0]:,}", end="  ")
        print()
    else:
        print(f"Error: {result['error']}")

    db.close()

    print("\n" + "=" * 60)
    print("  Setup complete! Start the API with:")
    print("    python -m uvicorn src.api.app:app --reload")
    print("=" * 60)


if __name__ == "__main__":
    main()
