# EVH vector store hosting options

## Question

Can the vector database use a managed host and still sleep when idle?

## Short answer

Yes. If the vector store is hosted on a managed database service, the instance can be stopped when idle and restarted when needed. That is the closest match to the current MariaDB-side operating model.

## What that means

- The PDFs stay in S3.
- Postgres stores only the vector/search data.
- The database is not expected to run continuously if the workload is sparse.
- While stopped, compute charges stop, but storage and backup charges continue.

## Cost shape

For a managed database:

- running time costs money while the instance is up
- storage costs money while data exists
- backups/snapshots may still cost money while the instance is stopped
- first query after restart pays the warm-up/startup penalty

## Operational tradeoff

Stopping the database is cheaper than leaving it on all day, but it adds:

- startup latency
- operational scheduling overhead
- possible cold-cache slowdown after restart

## Recommendation

Use a managed Postgres host if we want the easiest sleep behavior. If the benchmark shows chunking is too slow on-demand, precompute only the hot PDFs and keep the rest cold in S3.
