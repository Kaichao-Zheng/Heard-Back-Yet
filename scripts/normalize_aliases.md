This is a manual checkpoint between `run_data_pipeline.py` and `load_postgres.py`.

- `etl.append_aliases` discovers raw company and position aliases, but it does not choose canonical names.

  It leaves the `normalized` column empty for manual normalization before PostgreSQL loading.