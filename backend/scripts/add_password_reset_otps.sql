-- Run in Supabase SQL editor if password_reset_otps was not auto-created.
CREATE TABLE IF NOT EXISTS password_reset_otps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    phone_normalized VARCHAR NOT NULL,
    code_hash VARCHAR NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER DEFAULT 0,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_password_reset_otps_phone_normalized ON password_reset_otps (phone_normalized);
CREATE INDEX IF NOT EXISTS idx_password_reset_user_active ON password_reset_otps (user_id, consumed_at);
