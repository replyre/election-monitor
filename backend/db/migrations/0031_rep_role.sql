-- 0031: a 'rep' role for field representatives (the field-service Telegram bot).
--
-- Every member of the field team (field-service, schema `field`) must be an
-- app_user, because field-service resolves users through this table. Most of
-- them are representatives who only use the Telegram bot and must never see
-- the analytics web app. 'rep' is that role:
--   * reps have no password_hash, so /login can never succeed for them;
--   * the API refuses a rep token outright (api/deps.py current_user), so a
--     rep is never treated as an unrestricted user by scoped_block_id;
--   * block_id is optional for a rep (the field team holds the area scope).
--
-- The check was declared inline in 0008, so it carries Postgres's default
-- name app_user_role_check.

ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;
ALTER TABLE app_user ADD CONSTRAINT app_user_role_check
    CHECK (role IN ('admin', 'strategist', 'block', 'rep'));

COMMENT ON COLUMN app_user.role IS
    'admin | strategist | block: web users. rep: field representative, Telegram bot only, never signs in to the web.';
