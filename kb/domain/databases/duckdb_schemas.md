# DuckDB Schemas for DAB Datasets

## Analytics Cube Dataset

### Table: sales_fact**

- sale_id (BIGINT, PK)
- customer_id (INTEGER)
- product_id (INTEGER)
- sale_date (DATE)
- amount (DECIMAL(10,2))
- quantity (INTEGER)

### Table: time_dimension**

- date_key (DATE, PK)
- year (INTEGER)
- quarter (INTEGER)
- month (INTEGER)
- fiscal_year (INTEGER)
- fiscal_quarter (INTEGER)

## Yelp Dataset — Rating Source Warning

**`business.stars` is a stale pre-computed aggregate**, updated weekly by a batch job.

For any query asking for "average rating", "review score", or rating-based filters on Yelp data:
- **Always recompute from `MongoDB reviews.stars`** grouped by `business_id`.
- **Do NOT use `business.stars`** as if it were a live per-review average.

```python
# Correct: recompute from live reviews
pipeline = [
    {"$group": {"_id": "$business_id", "avg_rating": {"$avg": "$stars"}}}
]

# Wrong: stale weekly aggregate
# SELECT stars FROM business WHERE ...
```

System prompt guard: "If query mentions 'rating' or 'review score' on Yelp data, ALWAYS join MongoDB reviews — do NOT use `business.stars`."

---

## Important for DAB

DuckDB is used for analytical queries that aggregate across large datasets.
Optimize for: GROUP BY, window functions, time-series analysis.

**Fiscal Calendar Note:** Telecom fiscal Q3 = Oct-Dec (not Jul-Sep)
Check kb/domain/domain_terms/business_glossary.md for dataset-specific calendars.

## DAB-Specific Query Examples

**Declining repeat purchase rate by segment (Q3):**

```sql
SELECT
    customer_segment,
    fiscal_quarter,
    COUNT(DISTINCT customer_id) AS customers,
    SUM(amount) AS revenue,
    revenue / LAG(revenue) OVER (PARTITION BY customer_segment ORDER BY fiscal_quarter) - 1 AS growth_rate
FROM sales_fact
JOIN time_dimension ON sales_fact.sale_date = time_dimension.date_key
WHERE time_dimension.fiscal_quarter = 3
  AND time_dimension.fiscal_year = 2025
GROUP BY customer_segment, fiscal_quarter;
```

**Ticket volume correlation (after conductor merges PG + Mongo):**

```sql
SELECT
    t.customer_id,
    t.revenue,
    m.ticket_count,
    CORR(t.revenue, m.ticket_count) OVER () AS revenue_ticket_correlation
FROM pg_transactions t
JOIN mongo_tickets m ON t.customer_id = m.customer_id;
```

**Window function for rolling 90-day active customers:**

```sql
SELECT
    customer_id,
    MAX(sale_date) AS last_purchase,
    CASE WHEN MAX(sale_date) >= CURRENT_DATE - INTERVAL '90 days' THEN 'active' ELSE 'inactive' END AS status
FROM sales_fact
GROUP BY customer_id;
```

## Injection Test

Q: What is DuckDB used for in DAB?
A: Analytical queries that aggregate across large datasets
