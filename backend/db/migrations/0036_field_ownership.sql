-- 0036: everything in schema `field` belongs to pulse_app.
--
-- The field service's migrations had been run against this database as the
-- owner role before 0035 created pulse_app, so its tables, sequences and
-- functions belonged to postgres and pulse_app (now the schema's owner) could
-- not read them. Ownership moves object by object, inside `field` only: rows
-- are untouched and nothing outside the schema changes. A no-op where Pulse
-- created the schema itself as pulse_app.

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.relname, c.relkind
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'field' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
          AND pg_get_userbyid(c.relowner) <> 'pulse_app'
          -- a sequence owned by a table column moves with its table
          AND NOT (c.relkind = 'S' AND EXISTS (
              SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i')))
    LOOP
        EXECUTE format('ALTER %s field.%I OWNER TO pulse_app',
                       CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                                      WHEN 'S' THEN 'SEQUENCE' WHEN 'f' THEN 'FOREIGN TABLE'
                                      ELSE 'TABLE' END,
                       r.relname);
    END LOOP;
    FOR r IN
        SELECT p.oid::regprocedure AS sig, p.prokind
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'field' AND pg_get_userbyid(p.proowner) <> 'pulse_app'
    LOOP
        EXECUTE format('ALTER %s %s OWNER TO pulse_app',
                       CASE r.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END, r.sig);
    END LOOP;
    FOR r IN
        SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'field' AND t.typtype IN ('e', 'd', 'c')
          AND NOT EXISTS (SELECT 1 FROM pg_class c WHERE c.reltype = t.oid)
          AND pg_get_userbyid(t.typowner) <> 'pulse_app'
    LOOP
        EXECUTE format('ALTER TYPE field.%I OWNER TO pulse_app', r.typname);
    END LOOP;
END
$$;
