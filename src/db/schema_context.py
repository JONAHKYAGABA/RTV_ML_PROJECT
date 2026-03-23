"""
Schema Context Registry -- The most critical non-agent component.

Contains the full DDL, column descriptions sourced from the Descriptions sheet,
known data quality issues, unit annotations, and 10 few-shot SQL examples.

This is the difference between an agent that occasionally produces wrong answers
and one that reliably produces correct ones.
"""

from __future__ import annotations

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS households (
    id                               BIGINT PRIMARY KEY,
    household_id                     VARCHAR NOT NULL,       -- RUB-NTA-EZE-M-153334-7
    district                         VARCHAR NOT NULL,
    village                          VARCHAR NOT NULL,
    cluster                          VARCHAR NOT NULL,
    region                           VARCHAR NOT NULL,       -- 5 values
    cohort                           INTEGER NOT NULL,
    cycle                            VARCHAR NOT NULL,
    evaluation_month                 INTEGER NOT NULL,
    -- Crop adoption (boolean)
    cassava                          BOOLEAN NOT NULL,
    maize                            BOOLEAN NOT NULL,
    ground_nuts                      BOOLEAN NOT NULL,
    irish_potatoes                   BOOLEAN NOT NULL,
    sweet_potatoes                   BOOLEAN NOT NULL,
    perennial_crops_grown_food_banana BOOLEAN NOT NULL,      -- food banana
    -- Household characteristics
    tot_hhmembers                    INTEGER NOT NULL,
    business_participation           BOOLEAN NOT NULL,
    land_size_for_crop_agriculture_acres INTEGER NOT NULL,   -- renamed snake_case
    farm_implements_owned            INTEGER NOT NULL,       -- OUTLIER: max=30000
    vsla_participation               BOOLEAN NOT NULL,
    -- Outcomes
    average_water_consumed_per_day   INTEGER NOT NULL,       -- unit: JERRYCANS
    prediction                       BOOLEAN NOT NULL,       -- hit target = TRUE
    predicted_income                 DOUBLE NOT NULL,
    date                             DATE NOT NULL,
    created_at                       VARCHAR
);
"""

COLUMN_DESCRIPTIONS = {
    "id": "Auto-increment primary key",
    "household_id": "Structured string (e.g., 'RUB-NTA-EZE-M-153334-7') encoding "
                    "district-village-name-gender-id-members. NEVER cast to integer.",
    "district": "Administrative district name (22 unique)",
    "village": "Village name (1,040 unique)",
    "cluster": "Group of neighboring villages sharing resources and infrastructure "
               "(146 unique)",
    "region": "5 regions: South West (51.5%), Mid West (24.1%), North (10.2%), "
              "Central (8.7%), East (5.5%)",
    "cohort": "Launch year of the cluster group (2023, 2024, 2025)",
    "cycle": "Activity period ('A' or 'B')",
    "evaluation_month": "Months since program start when evaluation occurred "
                        "(6, 9, 12, 18, 23)",
    "cassava": "BOOLEAN - if household grows cassava",
    "maize": "BOOLEAN - if household grows maize (most common crop: 51.9%)",
    "ground_nuts": "BOOLEAN - if household grows ground nuts (least common: 14.9%)",
    "irish_potatoes": "BOOLEAN - if household grows irish potatoes (35.9%)",
    "sweet_potatoes": "BOOLEAN - if household grows sweet potatoes (22.8%)",
    "perennial_crops_grown_food_banana": "BOOLEAN - if household grows food banana (28.3%)",
    "tot_hhmembers": "Total household members (integer, 0-20, mean=5.25)",
    "business_participation": "BOOLEAN - if any household member participates in business (41.9%)",
    "land_size_for_crop_agriculture_acres": "Land size in acres (integer, 0-99). "
                                            "WARNING: max=99 likely encodes 'unknown'.",
    "farm_implements_owned": "CRITICAL: extreme outliers (max=30,000, IQR=[3,5], std=183). "
                            "NEVER use AVG() directly. Use PERCENTILE_CONT(0.5) or "
                            "filter WHERE farm_implements_owned < 100.",
    "vsla_participation": "BOOLEAN - Village Savings and Loan Association participation "
                         "(near-universal: 93.1%)",
    "average_water_consumed_per_day": "Units are JERRYCANS (NOT liters). "
                                     "1 jerrycan ~ 20 liters. Mean=3.56, max=20. "
                                     "Zero values may indicate missing data.",
    "prediction": "BOOLEAN - TRUE = household predicted to HIT income target. "
                  "Overall: 54.4% True, 45.6% False.",
    "predicted_income": "Combined income + production value (DOUBLE). "
                       "Range: 0.52-5.39, mean=1.96, median=1.83.",
    "date": "Date of data collection (3 dates: 2024-11, 2025-01, 2025-06)",
    "created_at": "Timestamp of database entry (VARCHAR)",
}

DATA_QUALITY_WARNINGS = [
    "farm_implements_owned has extreme outliers (max=30,000, IQR=[3,5], std=183). "
    "Never use AVG() directly. Use PERCENTILE_CONT(0.5) or filtered mean "
    "WHERE farm_implements_owned <= 100.",

    "average_water_consumed_per_day=0 may indicate missing data, not zero consumption. "
    "Always note units as JERRYCANS in explanations.",

    "household_id is a structured string (region-district-village-gender-id-cycle). "
    "Never cast to integer or use as a numeric join key.",

    "land_size_for_crop_agriculture_acres max=99 may encode 'unknown'. "
    "Consider filtering > 50 for analyses.",
]

FEW_SHOT_EXAMPLES = [
    {
        "question": "What proportion participate in business by region?",
        "sql": """
            SELECT region,
                   COUNT(*) AS total,
                   SUM(CASE WHEN business_participation THEN 1 ELSE 0 END) AS participants,
                   ROUND(100.0 * SUM(CASE WHEN business_participation THEN 1 ELSE 0 END)
                         / COUNT(*), 2) AS participation_pct
            FROM households
            GROUP BY region
            ORDER BY participation_pct DESC
        """,
    },
    {
        "question": "Average farm implements -- outlier safe",
        "sql": """
            SELECT
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY farm_implements_owned)
                    AS median_implements,
                ROUND(AVG(CASE WHEN farm_implements_owned <= 100
                          THEN farm_implements_owned END), 2) AS mean_excl_outliers,
                COUNT(CASE WHEN farm_implements_owned > 100 THEN 1 END) AS outlier_count
            FROM households
        """,
    },
    {
        "question": "Water consumption distribution with buckets",
        "sql": """
            SELECT
                CASE
                    WHEN average_water_consumed_per_day = 0 THEN '0 (no data)'
                    WHEN average_water_consumed_per_day <= 2 THEN '1-2 jerrycans'
                    WHEN average_water_consumed_per_day <= 4 THEN '3-4 jerrycans'
                    WHEN average_water_consumed_per_day <= 7 THEN '5-7 jerrycans'
                    ELSE '8+ jerrycans (high)'
                END AS bucket,
                COUNT(*) AS households,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
            FROM households
            GROUP BY bucket
            ORDER BY MIN(average_water_consumed_per_day)
        """,
    },
    {
        "question": "Average predicted income by district, ordered descending",
        "sql": """
            SELECT district,
                   ROUND(AVG(predicted_income), 3) AS avg_income,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY predicted_income), 3) AS median_income,
                   COUNT(*) AS households
            FROM households
            GROUP BY district
            ORDER BY avg_income DESC
        """,
    },
    {
        "question": "Which region has the highest prediction success rate?",
        "sql": """
            SELECT region,
                   COUNT(*) AS total,
                   SUM(CASE WHEN prediction THEN 1 ELSE 0 END) AS predicted_hit,
                   ROUND(100.0 * SUM(CASE WHEN prediction THEN 1 ELSE 0 END)
                         / COUNT(*), 2) AS success_pct
            FROM households
            GROUP BY region
            ORDER BY success_pct DESC
        """,
    },
    {
        "question": "Crop diversity count per household and its relation to income",
        "sql": """
            SELECT
                (CASE WHEN cassava THEN 1 ELSE 0 END +
                 CASE WHEN maize THEN 1 ELSE 0 END +
                 CASE WHEN ground_nuts THEN 1 ELSE 0 END +
                 CASE WHEN irish_potatoes THEN 1 ELSE 0 END +
                 CASE WHEN sweet_potatoes THEN 1 ELSE 0 END +
                 CASE WHEN perennial_crops_grown_food_banana THEN 1 ELSE 0 END
                ) AS crop_count,
                COUNT(*) AS households,
                ROUND(AVG(predicted_income), 3) AS avg_income,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY predicted_income), 3) AS median_income
            FROM households
            GROUP BY crop_count
            ORDER BY crop_count
        """,
    },
    {
        "question": "Top 5 villages by average predicted income with crop info",
        "sql": """
            SELECT village,
                   district,
                   COUNT(*) AS households,
                   ROUND(AVG(predicted_income), 3) AS avg_income,
                   ROUND(100.0 * SUM(CASE WHEN maize THEN 1 ELSE 0 END) / COUNT(*), 1) AS maize_pct,
                   ROUND(100.0 * SUM(CASE WHEN irish_potatoes THEN 1 ELSE 0 END) / COUNT(*), 1) AS potato_pct,
                   ROUND(100.0 * SUM(CASE WHEN cassava THEN 1 ELSE 0 END) / COUNT(*), 1) AS cassava_pct
            FROM households
            GROUP BY village, district
            HAVING COUNT(*) >= 10
            ORDER BY avg_income DESC
            LIMIT 5
        """,
    },
    {
        "question": "Compare water consumption: business vs non-business households",
        "sql": """
            SELECT
                CASE WHEN business_participation THEN 'Business' ELSE 'No Business' END AS group_name,
                COUNT(*) AS households,
                ROUND(AVG(average_water_consumed_per_day), 2) AS avg_jerrycans_per_day,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
                      (ORDER BY average_water_consumed_per_day), 2) AS median_jerrycans
            FROM households
            GROUP BY business_participation
        """,
    },
    {
        "question": "Household size distribution by region",
        "sql": """
            SELECT region,
                   ROUND(AVG(tot_hhmembers), 2) AS avg_members,
                   MIN(tot_hhmembers) AS min_members,
                   MAX(tot_hhmembers) AS max_members,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tot_hhmembers), 1) AS median_members
            FROM households
            GROUP BY region
            ORDER BY avg_members DESC
        """,
    },
    {
        "question": "VSLA participation rate by district",
        "sql": """
            SELECT district,
                   COUNT(*) AS total,
                   ROUND(100.0 * SUM(CASE WHEN vsla_participation THEN 1 ELSE 0 END)
                         / COUNT(*), 1) AS vsla_pct
            FROM households
            GROUP BY district
            ORDER BY vsla_pct DESC
        """,
    },
]
