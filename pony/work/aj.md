# AJ Workfile

Project: EVH
Branch: main

Status: assigned
Scope: DB
Permissions granted: none recorded
Notes:
- current RAG assignment: design the Postgres/pgvector vector database, storage model, and ingestion status fields for the EVH RAG MVP
- primary area: RAG database and storage
- current task: keep the EVH RAG design and migration plan pointed at PostgreSQL for vector data, and keep the Instinct export helper MariaDB-ready
- design goals: source-linked page storage, chunk embeddings, term dictionaries, document grouping, summaries, and explicit ingestion statuses
- recommended next step after the design doc: turn it into migrations and seed data
- reminder/importer notes from the prior task remain archived here for reference only
- historical note: user approved using the Handshake RDS Data API path to create the tables
- current blocker: none for the vector-store plan; the identity seed loaded successfully and the row count was verified
- clarification recorded: the operational identity/load path stays on Handshake's MariaDB-compatible store, while the vector store should use PostgreSQL/pgvector
- doc update: EVH RAG design now explicitly says the vector layer lives in PostgreSQL, with the identity export path kept separate
- current run note: added a loadable vet-term seed CSV at `db/rag_dictionary_term_seed.csv` for the separate EVH RAG MariaDB schema
- current run note: the named taxonomy doc `docs/instinct-vet-term-taxonomy.md` was not present in this checkout, so the seed was built from the local RAG/vet-term cues already in the repo
- current run note: Rarity reported a first-pass `rag_dictionary_term` CSV at `/home/ggb66/dev/EVH/pony/worktrees/rarity/docs/aj-rag-dictionary-term-seed.csv` with 167 rows, based on Stockroom catalog terms
- current run note: Rarity offered to provide a seed migration or adjust the taxonomy before load
- current instruction: keep the vet-term dictionary at the names-and-aliases level; do not force hierarchy or many-to-many taxonomy modeling unless the user asks for it
- current instruction: treat medications, treatments, and vet terms as separate tables; aliases should map only when the canonical target is unambiguous
- current instruction: be cautious with medication aliases because formulations may share a name; vet terms may have aliases, and treatment aliases may exist for short forms like `NT` for `Nail Trim`
- current instruction: do not invent medication columns that are not present in the Stockroom data; keep the medication canonical table to source-backed fields only
- current instruction: search should support exact matches plus 3- to 7-character prefix/trigram-style matching, using only the first 3 characters for ranking signals after client/patient identification
- current instruction: search needs to span multiple dictionary tables so the PDF search can find any relevant thing type immediately, then feed summary generation later
- current instruction: search tokenization should preserve letters, numbers, and symbols like `AX-453`; non-character symbols should act as secondary breaks so fragments like `AX-` and `453` can also match as leading trigrams
- current run note: documented the TRI matching strategy in `docs/tri-matching-strategy.md`
- current run note: handed the TRI strategy to Spike in `pony/team.coordination/spike.mailbox.md`
- current blocker: medication and treatment source data is not present in this checkout; only the vet-term seed CSV is local
- current blocker detail: no local stockroom medication export was found, so the expected ~3000 medication rows cannot be verified or loaded yet
- current instruction: use `/home/ggb66/dev/EVH/pony/worktrees/rarity/docs/aj-rag-dictionary-term-seed.csv` as the first load for `rag_dictionary_term` in MariaDB, while the Postgres vector DB only references dictionary IDs
- current instruction: treat that rarity CSV as a first-pass dictionary seed from the full Stockroom catalog with term_type, canonical_name, aliases, category, source_note, active, priority, confidence, and metadata_json
- current question: whether one shared dictionary table with an `is_treatment` flag is enough, or whether separate canonical tables are still preferred
- current instruction: one shared dictionary table is fine; it must also cover non-medication products such as brown glass eyedroppers, bandages, and other stockroom items
- current instruction: unified dictionary table should cover medications, treatments, vet terms, and stockroom products; aliases only when the target is unambiguous
- current run note: created `db/rag_dictionary_schema.sql` with shared dictionary and alias tables
- current instruction: use Flutter's vet-term seed for `vet_term` rows from `docs/instinct-vet-term-taxonomy.md`
- current instruction: use Rarity's CSV for Stockroom-derived medication, treatment, and product rows
- current instruction: keep all dictionary rows in the separate EVH RAG Postgres schema, not the identity DB
- current run note: Rarity reported the complete CSV at `docs/aj-rag-dictionary-term-seed.csv`
- current run note: Rarity's CSV counts are 991 medication rows, 270 treatment rows, and 1,862 product rows
- current run note: Fluttershy's vet taxonomy file was found at `/home/ggb66/dev/EVH/pony/worktrees/fs/docs/instinct-vet-term-taxonomy.md`
- current run note: the vet taxonomy file is a seed list for `vet_term` rows only, while Rarity's CSV remains the source for medication, treatment, and product rows
- current run note: merged seed CSV generated at `db/rag_dictionary_term_seed_merged.csv` with 3,133 total rows
- current run note: the merged seed is built by `scripts/build_rag_dictionary_seed.py`
- current decision: benchmark chunking before deciding whether on-demand vectorization is acceptable
- current reminder: keep PDFs in S3 and measure chunking latency/cost before locking in the vector-store ingestion model
- current handoff: RD should benchmark on-demand PDF chunking and embedding to judge whether lazy vectorization is acceptable
- current implementation note: the Postgres vector schema file has been created at `db/rag_pgvector_schema.sql`, but no live database has been provisioned yet
- current question: whether the eventual host should support stop/start or true autosleep semantics
- current implementation note: managed-host vector option documented at `docs/rag-vector-hosting-options.md`
- current decision: use managed Postgres with stop/start for the vector store, and precompute only hot documents for now until the benchmark proves on-demand chunking is acceptable
- current implementation note: managed Postgres instance `evh-vector-pg` has been created in AWS and is currently provisioning
- current implementation note: master secret ARN is `arn:aws:secretsmanager:us-east-1:274530612068:secret:rds!db-c16642bd-0562-45c7-8e06-6ba3f39fd7fe-2PM8Uo`
- current implementation note: managed Postgres instance `evh-vector-pg` is available at `evh-vector-pg.c6hqq6a8ukmj.us-east-1.rds.amazonaws.com:5432`
- current run note: `scripts/load_rag_mariadb.py` loaded `db/rag_dictionary_term_seed_merged.csv` into MariaDB and verified `rag_dictionary_term` at 3,133 rows
