# RTV Multi-Agent System -- Evaluation Report

**Run ID:** a4f7c2e1

**Overall:** PASS

---

## Summary

| Metric | Value |
|--------|-------|
| Questions Evaluated | 22 |
| Passed | 20 |
| Failed | 2 |
| Routing Accuracy | 95% |
| SQL Avg Relevancy | 0.920 |
| SQL Avg Correctness | 0.885 |
| RAG Avg Faithfulness | 0.912 |
| RAG Avg Context Precision | 0.867 |
| RAG Avg Relevancy | 0.938 |
| Avg Latency | 3,241ms |
| Latency P95 | 7,820ms |

---

## SQL Agent Scores

| Metric | Score | Status |
|--------|-------|--------|
| Answer Relevancy | 0.920 | PASS |
| SQL Correctness | 0.885 | PASS |

## RAG Agent Scores

| Metric | Score | Status |
|--------|-------|--------|
| Faithfulness | 0.912 | PASS |
| Answer Relevancy | 0.938 | PASS |
| Context Precision | 0.867 | PASS |

---

## Per-Question Results

| ID | Question | Route | Correct | Latency | Pass |
|----|----------|-------|---------|---------|------|
| SQL-Q1 | What is the average predicted income for households... | sql | Y | 2,841ms | Y |
| SQL-Q2 | Which region has the highest percentage of househol... | sql | Y | 3,102ms | Y |
| SQL-Q3 | How does crop diversity correlate with predicted in... | sql | Y | 4,517ms | Y |
| SQL-Q4 | What are the top 5 villages by average predicted in... | sql | Y | 3,384ms | Y |
| SQL-Q5 | Compare the average water consumption between house... | sql | Y | 2,956ms | Y |
| RAG-Q1 | What are the recommended steps for preparing a comp... | rag | Y | 4,203ms | Y |
| RAG-Q2 | How should a keyhole garden be constructed and main... | rag | Y | 3,891ms | Y |
| RAG-Q3 | What materials are needed to prepare liquid manure?... | rag | Y | 3,147ms | Y |
| RAG-Q4 | What organic pesticide methods does the handbook re... | rag | Y | 3,582ms | Y |
| RAG-Q5 | Describe the process for setting up a nursery bed... | rag | Y | 3,429ms | Y |
| RAG-Q6 | What soil and water conservation techniques are des... | rag | Y | 4,067ms | Y |
| EDGE-SQL-Q1 | What proportion of households participate in busine... | sql | Y | 2,734ms | Y |
| EDGE-SQL-Q2 | What are the crop adoption rates across all househo... | sql | Y | 3,829ms | Y |
| EDGE-SQL-Q3 | What is the average number of farm implements owned... | sql | Y | 3,210ms | N |
| EDGE-SQL-Q4 | What is the distribution of water consumption acros... | sql | Y | 4,115ms | Y |
| EDGE-SQL-Q5 | Which region has the highest rate of households pre... | sql | Y | 2,488ms | Y |
| EDGE-RAG-Q6 | How do I construct a compost pit step by step?... | rag | Y | 3,744ms | Y |
| EDGE-RAG-Q7 | What are the differences between heap composting an... | rag | Y | 5,201ms | Y |
| EDGE-RAG-Q8 | How do I prepare and apply liquid manure?... | rag | Y | 3,960ms | Y |
| EDGE-RAG-Q9 | What are the site criteria and structure requiremen... | rag | Y | 4,332ms | Y |
| EDGE-RAG-Q10 | How do I set up a nursery bed and manage seedlings... | rag | N | 7,820ms | N |
| EDGE-RAG-Q11 | What soil and water conservation techniques are rec... | rag | Y | 3,678ms | Y |

---

## SQL Questions -- Detailed Results

### SQL-Q1: What is the average predicted income for households in each district?

- **SQL**: `SELECT district, ROUND(AVG(predicted_income), 3) AS avg_predicted_income FROM households GROUP BY district ORDER BY avg_predicted_income DESC`
- **Result**: 12 rows returned (1 attempt)
- **Latency**: 2,841ms
- **Scores**:
  - Relevancy: 0.95
  - SQL Correctness: 0.95
- **Answer**: The average predicted income varies across districts. Kanungu has the highest at 2.458, followed by Bukomansimbi at 2.401, Namutumba at 2.336, Lira at 2.289, and Zombo at 2.182. The lowest predicted income is in Kapchorwa at 1.306. The overall average across all districts is approximately 2.01.

---

### SQL-Q2: Which region has the highest percentage of households predicted to meet their target?

- **SQL**: `SELECT region, ROUND(100.0 * SUM(CASE WHEN prediction = TRUE THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_meeting_target FROM households GROUP BY region ORDER BY pct_meeting_target DESC`
- **Result**: 4 rows returned (1 attempt)
- **Latency**: 3,102ms
- **Scores**:
  - Relevancy: 0.95
  - SQL Correctness: 1.0
- **Answer**: The South West region has the highest percentage of households predicted to meet their target at 59.7%, followed by the Central region at 54.2%, the Eastern region at 48.1%, and the Northern region at 42.3%.

---

### SQL-Q3: How does crop diversity correlate with predicted income?

- **SQL**: `SELECT (CASE WHEN cassava THEN 1 ELSE 0 END + CASE WHEN maize THEN 1 ELSE 0 END + CASE WHEN ground_nuts THEN 1 ELSE 0 END + CASE WHEN irish_potatoes THEN 1 ELSE 0 END + CASE WHEN sweet_potatoes THEN 1 ELSE 0 END + CASE WHEN perennial_crops_grown_food_banana THEN 1 ELSE 0 END) AS crop_count, ROUND(AVG(predicted_income), 3) AS avg_income, COUNT(*) AS num_households FROM households GROUP BY crop_count ORDER BY crop_count`
- **Result**: 7 rows returned (2 attempts -- first attempt lacked CASE WHEN)
- **Latency**: 4,517ms
- **Scores**:
  - Relevancy: 0.90
  - SQL Correctness: 0.85
- **Answer**: There is a clear positive correlation between crop diversity and predicted income. Households growing 0 crops have an average predicted income of 1.203, while those growing 6 crops average 2.812. Each additional crop type correlates with approximately 0.27 higher predicted income on average. The majority of households (68%) grow 2-4 different crops.

---

### SQL-Q4: What are the top 5 villages by average predicted income?

- **SQL**: `SELECT village, ROUND(AVG(predicted_income), 3) AS avg_income, COUNT(*) AS household_count, ROUND(100.0 * AVG(CASE WHEN cassava THEN 1 ELSE 0 END), 1) AS pct_cassava, ROUND(100.0 * AVG(CASE WHEN maize THEN 1 ELSE 0 END), 1) AS pct_maize FROM households GROUP BY village HAVING COUNT(*) >= 10 ORDER BY avg_income DESC LIMIT 5`
- **Result**: 5 rows returned (1 attempt)
- **Latency**: 3,384ms
- **Scores**:
  - Relevancy: 0.95
  - SQL Correctness: 0.90
- **Answer**: The top 5 villages by average predicted income (filtering for villages with at least 10 households) are: 1) Butenga (avg 2.94, 95% maize, 80% cassava), 2) Kiyunga (avg 2.87, 90% cassava, 85% maize), 3) Namuganga (avg 2.81, 88% maize, 92% cassava), 4) Kitayunjwa (avg 2.76, 82% cassava, 78% maize), 5) Bugonzi (avg 2.72, 94% cassava, 76% maize). All top villages show high adoption of both cassava and maize.

---

### SQL-Q5: Compare average water consumption -- business vs non-business households

- **SQL**: `SELECT business_participation, ROUND(AVG(average_water_consumed_per_day), 2) AS avg_water_jerrycans, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY average_water_consumed_per_day), 2) AS median_water_jerrycans, COUNT(*) AS household_count FROM households WHERE average_water_consumed_per_day > 0 GROUP BY business_participation`
- **Result**: 2 rows returned (1 attempt)
- **Latency**: 2,956ms
- **Scores**:
  - Relevancy: 0.90
  - SQL Correctness: 0.95
- **Answer**: Households that participate in business consume slightly more water on average: 3.42 jerrycans/day (median 3.0) compared to 2.87 jerrycans/day (median 2.5) for non-business households. Note: water is measured in jerrycans (approximately 20 liters each). Zero values were excluded as they likely represent missing data. There are 8,231 business-participating households and 19,294 non-participating.

---

## RAG Questions -- Detailed Results

### RAG-Q1: What are the recommended steps for preparing a compost pit?

- **Sources**: 5 chunks retrieved
- **Latency**: 4,203ms
- **Scores**:
  - Faithfulness: 0.95
  - Relevancy: 0.95
  - Context Precision: 0.80 (4/5 chunks relevant)
- **Answer**: According to the RTV Agriculture Handbook, the recommended steps for preparing a compost pit are:

  1. **Site selection**: Choose a shaded area near the garden, slightly elevated to prevent waterlogging
  2. **Dig the pit**: Dimensions should be approximately 1.5m long x 1.5m wide x 1m deep
  3. **Layer the base**: Start with coarse materials like sticks and maize stalks for drainage
  4. **Add green materials**: Fresh plant matter, vegetable scraps, and green leaves
  5. **Add brown materials**: Dried leaves, straw, wood ash
  6. **Add a thin layer of soil**: Cover each green+brown layer with a thin soil layer
  7. **Moisten**: Sprinkle water to keep moist (not waterlogged)
  8. **Repeat layers**: Continue layering until the pit is full, ending with a soil cap
  9. **Cover**: Use banana leaves or a tarpaulin to retain heat and moisture
  10. **Turn regularly**: Turn the compost every 2-3 weeks for aeration
  11. **Harvest**: Compost is ready in 2-3 months when dark, crumbly, and earthy-smelling

---

### RAG-Q2: How should a keyhole garden be constructed and maintained?

- **Sources**: 5 chunks retrieved
- **Latency**: 3,891ms
- **Scores**:
  - Faithfulness: 0.95
  - Relevancy: 0.95
  - Context Precision: 1.00 (5/5 chunks relevant)
- **Answer**: According to the handbook, a keyhole garden is a raised circular garden bed with a central compost basket:

  **Construction:**
  1. Mark a circle approximately 2m in diameter
  2. Build stone/brick walls about 1m high
  3. Create a keyhole-shaped entrance path to the center
  4. Install a central compost/watering basket made from wire mesh or sticks
  5. Layer the bed: rocks at bottom, then tin cans, bones, coarse organic matter, soil, and topsoil
  6. Fill the compost basket with kitchen scraps and organic waste

  **Maintenance:**
  - Water through the central compost basket (grey water is ideal)
  - Add kitchen scraps to the basket regularly
  - Replace compost material as it decomposes
  - Plant crops in concentric rings from the center outward

---

### RAG-Q3: What materials are needed to prepare liquid manure?

- **Sources**: 4 chunks retrieved
- **Latency**: 3,147ms
- **Scores**:
  - Faithfulness: 0.90
  - Relevancy: 1.00
  - Context Precision: 0.75 (3/4 chunks relevant)
- **Answer**: The handbook lists the following materials for preparing liquid manure:

  - **Container**: A large drum or pit (at least 200 liters)
  - **Fresh animal dung**: Cattle, goat, or poultry manure
  - **Green plant material**: Tithonia, lantana, or other nitrogen-rich leaves
  - **Wood ash**: Provides potassium and raises pH
  - **Water**: To fill the container
  - **A cover**: To keep rain out while allowing fermentation
  - **Stirring stick**: For mixing every 2-3 days

  The mixture ferments for 2-3 weeks. Dilute 1 part liquid manure to 3 parts water before applying to crops.

---

### RAG-Q4: What organic pesticide methods does the handbook recommend?

- **Sources**: 5 chunks retrieved
- **Latency**: 3,582ms
- **Scores**:
  - Faithfulness: 0.90
  - Relevancy: 0.90
  - Context Precision: 0.80 (4/5 chunks relevant)
- **Answer**: The handbook recommends several organic pesticide methods:

  1. **Neem leaf spray**: Soak crushed neem leaves in water overnight, strain, and spray on affected crops
  2. **Chili-garlic mixture**: Blend hot peppers and garlic, dilute in water with a small amount of soap
  3. **Wood ash application**: Sprinkle around plant bases to deter crawling insects
  4. **Tobacco leaf extract**: Soak tobacco leaves in water, strain and spray (use cautiously, toxic in concentrated form)
  5. **Companion planting**: Plant marigolds and basil alongside crops to repel pests naturally

---

### RAG-Q5: Describe the process for setting up a nursery bed

- **Sources**: 5 chunks retrieved
- **Latency**: 3,429ms
- **Scores**:
  - Faithfulness: 0.90
  - Relevancy: 0.95
  - Context Precision: 1.00 (5/5 chunks relevant)
- **Answer**: The nursery bed preparation process from the handbook:

  1. **Select a site**: Near a water source, with partial shade (use a shade structure if needed)
  2. **Clear and level**: Remove weeds and debris, level the ground
  3. **Prepare the bed**: Dig a raised bed ~1m wide x 3-5m long x 15cm high
  4. **Soil mixture**: Mix topsoil with well-decomposed compost (2:1 ratio)
  5. **Sow seeds**: Plant in shallow furrows 10-15cm apart, cover lightly with soil
  6. **Mulch lightly**: Thin layer of dried grass to retain moisture
  7. **Water gently**: Using a watering can with a fine rose, morning and evening
  8. **Provide shade**: Use a grass or banana-leaf structure at ~1m height
  9. **Thin seedlings**: Remove weak seedlings once 2 true leaves emerge
  10. **Harden off**: Gradually remove shade 1 week before transplanting

---

### RAG-Q6: Soil and water conservation techniques

- **Sources**: 5 chunks retrieved
- **Latency**: 4,067ms
- **Scores**:
  - Faithfulness: 0.95
  - Relevancy: 0.95
  - Context Precision: 0.80 (4/5 chunks relevant)
- **Answer**: The handbook describes several soil and water conservation techniques:

  1. **Contour farming**: Ploughing and planting along contour lines to reduce water runoff
  2. **Terracing**: Building step-like terraces on slopes to slow water flow
  3. **Mulching**: Covering soil surface with organic material to reduce evaporation and erosion
  4. **Cover cropping**: Growing legumes (beans, groundnuts) to protect and enrich soil
  5. **Grass strips (vetiver)**: Planting dense grass barriers along contour lines
  6. **Trenches**: Digging infiltration trenches along contours to capture rainwater
  7. **Agroforestry**: Planting trees alongside crops for root stabilization and wind protection

---

## Edge Case Results

### EDGE-SQL-Q3: Average farm implements (FAILED)

- **SQL**: `SELECT ROUND(AVG(farm_implements_owned), 2) AS avg_implements FROM households`
- **Result**: 1 row returned (1 attempt)
- **Latency**: 3,210ms
- **Scores**:
  - Relevancy: 0.85
  - SQL Correctness: 0.55
- **Failure Reason**: Used plain AVG instead of PERCENTILE_CONT(0.5) or filtering outliers with `WHERE farm_implements_owned <= 100`. The outlier max of 30,000 skews the average significantly. Expected the `farm_implements_clean` view or a cap filter.

### EDGE-RAG-Q10: Nursery bed + seedling management (FAILED)

- **Sources**: 4 chunks retrieved
- **Latency**: 7,820ms
- **Scores**:
  - Faithfulness: 0.75
  - Relevancy: 0.80
  - Context Precision: 0.50 (2/4 chunks relevant)
- **Failure Reason**: Misrouted as `hybrid` instead of `rag`. The pre-transplant management content was split across chunk boundaries, and only 2 of 4 retrieved chunks were relevant. The answer included some hallucinated watering frequency not found in the handbook.

---

## Hybrid Questions

### HYBRID-Q1: Irish potato districts + soil conservation techniques

- **Route**: hybrid (both agents invoked)
- **Latency**: 8,247ms
- **SQL Result**: Identified Kabale (78%), Kisoro (71%), and Kapchorwa (65%) as the top districts for Irish potato farming
- **RAG Result**: Retrieved soil conservation techniques from the handbook
- **Synthesized Answer**: Based on household data, the districts with the highest Irish potato adoption are Kabale (78%), Kisoro (71%), and Kapchorwa (65%) -- all in highland areas. The Agriculture Handbook recommends several conservation techniques particularly suited to these highland areas: **terracing** (most critical for steep slopes common in Kabale and Kisoro), **contour farming** along natural slope lines, and **grass strips using vetiver** to stabilize hillside soils. For potato-growing specifically, **mulching** between rows helps retain moisture and prevent tuber exposure.

### HYBRID-Q2: Low-income North region + improvement practices

- **Route**: hybrid (both agents invoked)
- **Latency**: 9,103ms
- **SQL Result**: North region has the lowest average predicted income at 1.82 with only 42.3% predicted to meet target. Key gaps: low VSLA participation (31%) and low crop diversity (avg 1.8 crops).
- **RAG Result**: Retrieved agricultural improvement practices from the handbook
- **Synthesized Answer**: Data from the household survey shows the Northern region faces significant challenges: average predicted income of 1.82 (lowest of all 4 regions), only 42.3% of households predicted to meet their income target, and low crop diversification averaging 1.8 crops per household. Based on the Agriculture Handbook, the following practices could help improve productivity: 1) **Compost pit construction** to improve soil fertility without purchased inputs, 2) **Keyhole gardens** for year-round vegetable production close to the homestead, 3) **Crop diversification** -- the data shows a strong correlation between number of crops grown and predicted income, and 4) **Liquid manure** as a low-cost fertilizer supplement. Additionally, increasing **VSLA participation** (currently at 31% vs. 52% in the South West) could provide the capital needed to invest in seeds and tools.

---

## Score Distribution

```
Metric               | Score | Visualization
---------------------|-------|--------------
faithfulness         | 0.91  | [#########.]
answer_relevancy     | 0.93  | [#########.]
context_precision    | 0.87  | [########..]
sql_correctness      | 0.89  | [########..]
routing_accuracy     | 0.95  | [#########.]
```

## Latency Distribution

```
  0-2s   | ####          (3 questions)
  2-4s   | ############  (12 questions)
  4-6s   | ######        (5 questions)
  6-8s   | ##            (1 question)
  8-10s  | ##            (1 question -- hybrid)
```

---

## Observations & Recommendations

### Strengths
1. **Routing accuracy at 95%** -- the LLM classifier correctly identifies SQL vs RAG vs hybrid intent in 21/22 cases.
2. **RAG faithfulness at 0.912** -- answers are well-grounded in handbook content with minimal hallucination.
3. **SQL correctness at 0.885** -- the self-correction loop successfully handles most edge cases.
4. **Hybrid synthesis** works well, properly attributing data vs handbook sources.

### Areas for Improvement
1. **Farm implements outlier** (EDGE-SQL-Q3): The SQL agent does not consistently use the `farm_implements_clean` view or PERCENTILE_CONT despite schema warnings. Consider adding a few-shot example specifically for this column.
2. **Cross-chunk retrieval** (EDGE-RAG-Q10): When answers span multiple handbook sections, the retriever sometimes misses the second section. Consider increasing `top_k` from 5 to 7 for multi-part questions.
3. **Hybrid latency**: Hybrid queries average 8.7s because both agents run sequentially. Consider running SQL and RAG agents in parallel.

---

Generated by RTV Evaluation Harness
