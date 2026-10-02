-- Extensions SerpFlow needs. Runs once, on first container start.
--
-- pgvector backs the semantic cache layer (section 17). pg_trgm backs the
-- Catalog Explorer search box. Both are created here rather than in a
-- migration because CREATE EXTENSION needs superuser.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- app.current_org is set per transaction by the application
-- (SET LOCAL via set_config) and is what every RLS policy reads.
-- See app/db/session.py:set_tenant and docs/database/rls.md.
ALTER DATABASE serpflow SET "app.current_org" TO '';
