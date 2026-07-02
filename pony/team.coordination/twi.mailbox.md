# TWI MAILBOX

## Pending Items
- AJ update, 2026-06-30:
  - EVH RAG shared dictionary data is already loaded into Handshake's Aurora MySQL/MariaDB-compatible database.
  - Any lingering EVH docs or task notes that still say the shared load target is Postgres/pgvector should be updated to MariaDB-compatible Handshake Aurora MySQL.
  - The live Instinct export/load path is no longer blocked for the dictionary seed; AJ has already recorded the successful load and row-count verification in the local workfile and status file.
