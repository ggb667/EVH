# SPIKE MAILBOX

## Pending Items
- AJ update, 2026-06-30:
  - EVH RAG is still the active DB track, but the target vector store should be a separate Postgres database.
  - Handshake is Aurora MySQL, so it is fine for the two identity tables but not the RAG vector layer.
  - Live Instinct export/load is currently blocked by the shell policy and restart state; the next run should resume from a shell with outbound access.
  - Keep documenting the RAG architecture, worker contracts, and MVP milestones around the Postgres/vector split.
- AJ update, 2026-07-01:
  - Document the TRI matching strategy for dictionary and PDF search.
  - Exact matches must be supported.
  - Prefix matches should cover 3- to 7-character fragments, with the first 3 characters used as the main ranking signal.
  - Tokenization should preserve letters, numbers, and symbols, including code-like fragments such as `AX-453`.
  - Non-character symbols should also act as secondary breaks so subfragments like `AX-` and `453` can be searchable.
  - Search must span multiple dictionary tables and return one ranked result set after client/patient identification.
  - Keep the storage model simple; the search layer can handle the ranking behavior.
- AJ TRI note, 2026-07-01:
  - The TRI matching strategy is documented at `docs/tri-matching-strategy.md`.
  - Use that file as the search/ranking reference for exact match, prefix match, and symbol-aware tokenization behavior.
- AJ update, 2026-07-02:
  - Managed Postgres `evh-vector-pg` is now available.
  - Document the vector DB loading step and the managed-host handoff so the RAG work stays visible in the architecture notes.
