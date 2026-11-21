-- 0032: a least-privilege role for the API, and the chat role switched off.
--
-- The API connected as the database owner, so any flaw in it was a flaw with
-- the owner's rights: DROP, TRUNCATE, ALTER, every table. giridih_app reads
-- everything the pages show and writes only what the API's own routes write:
--   app_user.last_login_at          POST /auth/login
--   review_queue (resolve)          POST /acs/{n}/admin/review-queue/{id}
--   booth_crosswalk (manual match)  POST /acs/{n}/admin/crosswalk
--   surname_dict (upsert)           POST /acs/{n}/admin/surnames
--   ground_report (insert)          POST /acs/{n}/ground-reports
-- The jobs keep the owner role: refreshing a materialized view needs ownership.
--
-- Created NOLOGIN. db.apply_migrations grants LOGIN with API_DB_PASSWORD from
-- the environment, so no password is ever in this file.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'giridih_app') THEN
        CREATE ROLE giridih_app NOLOGIN;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM giridih_app;
GRANT USAGE ON SCHEMA public TO giridih_app;

-- Tables, views and materialized views.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO giridih_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO giridih_app;

GRANT UPDATE (last_login_at) ON app_user TO giridih_app;
GRANT UPDATE (status, note, resolved_at, resolved_by) ON review_queue TO giridih_app;
GRANT INSERT, UPDATE ON booth_crosswalk TO giridih_app;
GRANT INSERT, UPDATE ON surname_dict TO giridih_app;
GRANT INSERT ON ground_report TO giridih_app;

-- 0026 enabled row-level security on every table (the guard against Supabase's
-- anon/authenticated roles), so a non-owner role sees no rows without a policy.
-- This policy filters nothing for giridih_app: what it may do is decided by
-- the GRANTs above, which RLS cannot widen.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS giridih_app_all ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY giridih_app_all ON public.%I TO giridih_app USING (true) WITH CHECK (true)', t);
    END LOOP;
END
$$;

-- Views recreated by a later migration lose their grants (0021 was written for
-- exactly that); default privileges cover objects the owner creates from now on.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO giridih_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO giridih_app;

ALTER ROLE giridih_app SET search_path = public;
ALTER ROLE giridih_app SET statement_timeout = '15s';
ALTER ROLE giridih_app SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE giridih_app SET lock_timeout = '5s';

-- The chat assistant that used giridih_ro is gone; nothing should sign in as it.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'giridih_ro') THEN
        ALTER ROLE giridih_ro NOLOGIN;
    END IF;
END
$$;
