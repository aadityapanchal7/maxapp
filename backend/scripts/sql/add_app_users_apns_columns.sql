-- APNs device token storage (run in Supabase SQL Editor or psql).
-- Table: app_users (matches backend/models/sqlalchemy_models.py)

ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS apns_device_token TEXT;

ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS apns_token_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN app_users.apns_device_token IS 'iOS APNs device token (hex), for direct server push';
COMMENT ON COLUMN app_users.apns_token_updated_at IS 'When the APNs token was last registered or updated';
