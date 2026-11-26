-- 0034: admins are an email allow-list managed in the app.
--
-- The site is public and read-only. Admins sign in through Cloudflare Access,
-- which proves an email address at the edge; /auth/access admits an email only
-- when an active app_user with role 'admin' holds it. Admins add and remove one
-- another (api/routers/admins.py), so the API role may create an admin row and
-- switch is_active, and nothing more on app_user. Password hashes, roles of
-- existing rows and every other user stay out of its reach.

CREATE UNIQUE INDEX IF NOT EXISTS app_user_email_lower_idx
    ON app_user (lower(email)) WHERE email IS NOT NULL;

GRANT INSERT (email, name, role, daily_token_budget) ON app_user TO giridih_app;
GRANT UPDATE (is_active, name) ON app_user TO giridih_app;
