-- 0035: roles for the field service (field-service/, "Pulse").
--
-- Pulse keeps everything it owns in schema `field` and reads a few core tables.
-- Two roles, both created NOLOGIN; db.apply_migrations grants LOGIN from
-- PULSE_DB_PASSWORD / PULSE_CORE_RO_PASSWORD, so no password is in this file.
--
--   pulse_app      owns schema `field` (Pulse's own migrations create its
--                  tables there). No grant in `public`: it cannot read or
--                  change a core table.
--   pulse_core_ro  what CoreDbAdapter reads, and only that: the five app_user
--                  columns it selects (never password_hash, phone or email),
--                  and the geography and roll tables. Read-only by default.
--
-- The owner (postgres) is made a member of pulse_app so the nightly pg_dump
-- still reads the `field` schema.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pulse_app') THEN
        CREATE ROLE pulse_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pulse_core_ro') THEN
        CREATE ROLE pulse_core_ro NOLOGIN;
    END IF;
END
$$;

GRANT pulse_app TO CURRENT_USER;
-- Pulse's own runner issues CREATE SCHEMA IF NOT EXISTS field, which Postgres
-- checks against the database's CREATE privilege even when the schema exists.
-- That privilege lets pulse_app create schemas of its own, nothing in others.
DO $$
BEGIN
    EXECUTE format('GRANT CREATE ON DATABASE %I TO pulse_app', current_database());
END
$$;
CREATE SCHEMA IF NOT EXISTS field AUTHORIZATION pulse_app;
ALTER SCHEMA field OWNER TO pulse_app;
REVOKE ALL ON SCHEMA field FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM pulse_app;
ALTER ROLE pulse_app SET statement_timeout = '30s';
ALTER ROLE pulse_app SET idle_in_transaction_session_timeout = '60s';

GRANT USAGE ON SCHEMA public TO pulse_core_ro;
GRANT SELECT (user_id, name, role, block_id, is_active) ON app_user TO pulse_core_ro;
GRANT SELECT ON ac, block, area, booth, roll_snapshot, roll_revision TO pulse_core_ro;
ALTER ROLE pulse_core_ro SET default_transaction_read_only = on;
ALTER ROLE pulse_core_ro SET statement_timeout = '10s';
ALTER ROLE pulse_core_ro SET search_path = public;

-- 0026 put row-level security on every core table; without a policy this role
-- would see no rows. The grants above still decide what it may read.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['app_user', 'ac', 'block', 'area', 'booth', 'roll_snapshot', 'roll_revision']
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS pulse_core_ro_read ON public.%I', t);
        EXECUTE format('CREATE POLICY pulse_core_ro_read ON public.%I FOR SELECT TO pulse_core_ro USING (true)', t);
    END LOOP;
END
$$;
