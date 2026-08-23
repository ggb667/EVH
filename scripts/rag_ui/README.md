# Pinkie RAG UI

This is the first EVH RAG picker shell.

## What it does

- Serves a static HTML page from a Lambda-style Python handler.
- Provides two combo boxes: client and pet.
- Filters only after 3 typed characters.
- Shows the top 10 matches in a scrollable list.
- Scopes pet search to the selected client.

## Local run

```bash
python3 -m scripts.rag_ui.lambda_app --host 127.0.0.1 --port 8080
```

Then open:

```text
http://127.0.0.1:8080/
```

## Data source

By default the service reads the Instinct bulk cache at:

```text
/home/ggb66/dev/EVH/scripts/instinct_bulk_cache.json
```

You can override that with `RAG_UI_DATA_PATH`.

To read from the DB-backed identity catalog instead, set `RAG_UI_DB_PATH`
to a SQLite database file containing the `instinct_accounts` and
`instinct_patients` tables.
