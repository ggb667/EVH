# TWI MAILBOX

## Pending Items
- AJ update, 2026-06-30:
  - EVH RAG shared identity/load data is already loaded into Handshake's Aurora MySQL/MariaDB-compatible database.
  - The vector-data store should be PostgreSQL/pgvector, while the identity/load path stays on the MariaDB-compatible Handshake target.
  - The live Instinct export/load path is no longer blocked for the dictionary seed; AJ has already recorded the successful load and row-count verification in the local workfile and status file.
- AJ update, 2026-07-02:
  - Benchmark chunking latency and cost before deciding whether on-demand vectorization is acceptable.
  - Keep PDFs in S3 and use the benchmark to decide how much of the vector pipeline should be precomputed.
