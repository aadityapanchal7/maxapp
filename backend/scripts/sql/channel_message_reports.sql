-- Optional manual run (Supabase SQL Editor) if init_db / create_all did not run.
-- Normally the table is created on API startup via SQLAlchemy Base.metadata.create_all.

CREATE TABLE IF NOT EXISTS channel_message_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_message_id UUID NOT NULL,
    channel_id UUID NOT NULL,
    reporter_user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    reported_user_id UUID NOT NULL,
    reason TEXT DEFAULT '' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_message_report_reporter
    ON channel_message_reports (channel_message_id, reporter_user_id);

CREATE INDEX IF NOT EXISTS ix_channel_message_reports_channel_message_id
    ON channel_message_reports (channel_message_id);

CREATE INDEX IF NOT EXISTS ix_channel_message_reports_channel_id
    ON channel_message_reports (channel_id);

CREATE INDEX IF NOT EXISTS ix_channel_message_reports_reporter_user_id
    ON channel_message_reports (reporter_user_id);
