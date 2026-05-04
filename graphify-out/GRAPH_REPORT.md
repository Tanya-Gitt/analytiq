# Graph Report - /Users/krishna/live_product_monitoring  (2026-04-24)

## Corpus Check
- Corpus is ~361 words - fits in a single context window. You may not need a graph.

## Summary
- 11 nodes · 13 edges · 3 communities detected
- Extraction: 77% EXTRACTED · 23% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Python Dependencies|Python Dependencies]]
- [[_COMMUNITY_ETL Pipeline Functions|ETL Pipeline Functions]]
- [[_COMMUNITY_Sample Data Generator|Sample Data Generator]]

## God Nodes (most connected - your core abstractions)
1. `Live Product Monitoring Project` - 5 edges
2. `main()` - 3 edges
3. `SQLAlchemy` - 3 edges
4. `clean_dataframe()` - 2 edges
5. `upsert_orders()` - 2 edges
6. `pandas` - 2 edges
7. `PyMySQL` - 2 edges
8. `requests` - 2 edges
9. `python-dotenv` - 2 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Hyperedges (group relationships)
- **Database Access Stack** — requirements_sqlalchemy, requirements_pymysql, requirements_pandas [INFERRED 0.85]
- **HTTP and Environment Configuration Stack** — requirements_requests, requirements_python_dotenv [INFERRED 0.75]

## Communities

### Community 0 - "Python Dependencies"
Cohesion: 0.53
Nodes (6): Live Product Monitoring Project, pandas, PyMySQL, python-dotenv, requests, SQLAlchemy

### Community 1 - "ETL Pipeline Functions"
Cohesion: 0.83
Nodes (3): clean_dataframe(), main(), upsert_orders()

### Community 2 - "Sample Data Generator"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **Thin community `Sample Data Generator`** (1 nodes): `generate_sample.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Are the 2 inferred relationships involving `SQLAlchemy` (e.g. with `PyMySQL` and `pandas`) actually correct?**
  _`SQLAlchemy` has 2 INFERRED edges - model-reasoned connections that need verification._