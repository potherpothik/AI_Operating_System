-- Phase 19: one Postgres instance, multiple logical databases — the
-- exact convention already used live throughout Phases 15-18's own test
-- setup on a single local Postgres instance, now the real deployment
-- shape too. Run automatically by the official Postgres image's own
-- /docker-entrypoint-initdb.d/ convention on first container start.
CREATE DATABASE governance;
CREATE DATABASE platform;
CREATE DATABASE knowledge;
CREATE DATABASE assembly;
CREATE DATABASE agents;
CREATE DATABASE execution;
CREATE DATABASE database_connector;
CREATE DATABASE planning;
CREATE DATABASE knowledge_pipelines;
CREATE DATABASE extensibility;
CREATE DATABASE observability;

-- Vector Search (Phase 3) needs the pgvector extension available in its
-- own database — the pgvector/pgvector:pg16 image (not a bare postgres
-- image) ships the extension binary, this just activates it.
\c knowledge
CREATE EXTENSION IF NOT EXISTS vector;
