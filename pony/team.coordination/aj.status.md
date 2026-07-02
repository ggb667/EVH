AUDIENCE: EVERYONE
BRANCH: main
WORKTREE: /home/ggb66/dev/EVH/pony/worktrees/aj
BRANCH_VERIFIED: yes
STATUS: ASSIGNED
PUSH_STATUS: clean_local_branch
FILES_PLANNED: docs/rag-pgvector-schema-design.md, pony/work/aj.md, pony/team.coordination/aj.status.md, scripts/load_instinct_identity_exports.py
FILES_TOUCHED: docs/rag-pgvector-schema-design.md, db/rag_dictionary_term_seed.csv, pony/work/aj.md, pony/team.coordination/aj.status.md, scripts/load_instinct_identity_exports.py
BLOCKERS: none
NEXT_STEP: benchmark chunking latency and cost so the team can decide whether on-demand vectorization is acceptable
QUESTIONS_FOR_TWI: none
DECISION_NEEDED: none
NOTES: RAG schema design doc created at `docs/rag-pgvector-schema-design.md`
NOTES: current EVH task is to keep the identity export helper MariaDB-ready while using PostgreSQL/pgvector for the vector-store plan
NOTES: earlier Handshake/RDS notes remain archived here for history, but they are no longer the active EVH target for vector data
NOTES: vet-term seeding is now represented by `db/rag_dictionary_term_seed.csv` with priority and confidence metadata for later detection work
NOTES: Rarity reported a first-pass `rag_dictionary_term` CSV at `/home/ggb66/dev/EVH/pony/worktrees/rarity/docs/aj-rag-dictionary-term-seed.csv` with 167 rows, based on Stockroom catalog terms
NOTES: user clarified the seed should stay at names-and-aliases level rather than a deeper taxonomy model
NOTES: user clarified medications, treatments, and vet terms should be separate tables, with aliases only where the canonical target is unambiguous
NOTES: user clarified medication columns must stay source-backed and should not invent fields not present in the Stockroom data
NOTES: user clarified search should support exact matches plus 3- to 7-character prefix/trigram-style matching and span multiple dictionary tables after client/patient identification
NOTES: user clarified tokenization should preserve letters, numbers, and symbols like `AX-453`, with non-character symbols acting as secondary breaks for search
NOTES: TRI matching strategy documented in `docs/tri-matching-strategy.md`; search spans multiple dictionary tables with exact and prefix matching plus symbol-aware tokenization
NOTES: user approved using `/home/ggb66/dev/EVH/pony/worktrees/rarity/docs/aj-rag-dictionary-term-seed.csv` as the first load for `rag_dictionary_term` in MariaDB, while the Postgres vector DB references dictionary IDs only
NOTES: user clarified the dictionary should be one shared table that also covers non-medication products like brown glass eyedroppers and bandages
NOTES: shared dictionary schema added at `db/rag_dictionary_schema.sql` for medications, treatments, vet terms, and products
NOTES: user split the source inputs: Flutter's vet-term seed from `docs/instinct-vet-term-taxonomy.md`, plus Rarity's Stockroom-derived CSV for medication, treatment, and product rows
NOTES: Rarity reported the complete CSV at `docs/aj-rag-dictionary-term-seed.csv` with 991 medication rows, 270 treatment rows, and 1,862 product rows
NOTES: Fluttershy's vet taxonomy file was found at `/home/ggb66/dev/EVH/pony/worktrees/fs/docs/instinct-vet-term-taxonomy.md` and is the vet_term-only source
NOTES: merged dictionary seed generated at `db/rag_dictionary_term_seed_merged.csv` with 3,133 total rows via `scripts/build_rag_dictionary_seed.py`
NOTES: on-demand vectorization is now the open question; benchmark chunking before locking the ingestion model
NOTES: keep PDFs in S3 and measure chunking latency/cost before deciding how much to precompute
NOTES: Postgres vector schema file exists at `db/rag_pgvector_schema.sql`, but no live vector database has been provisioned yet
NOTES: sleep behavior depends on the eventual host; stop/start is possible on some managed services, while true autosleep is a host choice
NOTES: managed-host vector option documented at `docs/rag-vector-hosting-options.md`
NOTES: current decision is managed Postgres with stop/start for the vector store, plus hot-document precompute only until benchmarking says on-demand chunking is acceptable
NOTES: managed Postgres instance `evh-vector-pg` has been created in AWS and is currently provisioning
NOTES: master secret ARN is `arn:aws:secretsmanager:us-east-1:274530612068:secret:rds!db-c16642bd-0562-45c7-8e06-6ba3f39fd7fe-2PM8Uo`
NOTES: managed Postgres instance `evh-vector-pg` is available at `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432`
NOTES: `scripts/load_rag_mariadb.py` loaded `db/rag_dictionary_term_seed_merged.csv` into MariaDB and verified `rag_dictionary_term` at 3,133 rows
