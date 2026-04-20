-- Supabase migration — Onairos personalization connections
-- Run once in production. Idempotent, safe to replay.
--
-- Stores each user's active Onairos SDK handoff:
--   * apiUrl + accessToken returned by the mobile SDK's onResolved callback
--   * approvedRequests (which data categories the user consented to)
--   * cached trait/sentiment snapshot so the coaching context builder
--     does not hit Onairos on every chat turn
--
-- Access tokens are 1-hour domain-scoped JWTs. Re-consent refreshes the row.
-- Disconnect sets revoked_at so the coaching pipeline ignores the snapshot.

BEGIN;

CREATE TABLE IF NOT EXISTS public.user_onairos_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL UNIQUE
        REFERENCES public.app_users(id) ON DELETE CASCADE,
    api_url text NOT NULL,
    access_token text NOT NULL,
    token_expires_at timestamptz,
    approved_requests jsonb NOT NULL DEFAULT '{}'::jsonb,
    user_basic jsonb,
    traits_cached jsonb,
    traits_cached_at timestamptz,
    connected_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_onairos_connections_user_id
    ON public.user_onairos_connections(user_id);

COMMENT ON TABLE public.user_onairos_connections IS
    'Per-user Onairos consent handoff + cached trait snapshot. One active row per user.';
COMMENT ON COLUMN public.user_onairos_connections.api_url IS
    'Inference endpoint returned by the SDK. Do NOT hardcode; always read from this column.';
COMMENT ON COLUMN public.user_onairos_connections.access_token IS
    'Short-lived (~1h) JWT from Onairos SDK handoff. Rotate on re-consent.';
COMMENT ON COLUMN public.user_onairos_connections.approved_requests IS
    'Which data categories the user consented to, e.g. {"personality_traits": true}.';
COMMENT ON COLUMN public.user_onairos_connections.traits_cached IS
    'Last inference response (Traits + optional InferenceResult). Used by coaching context builder.';
COMMENT ON COLUMN public.user_onairos_connections.revoked_at IS
    'Set when the user disconnects. Non-null rows are ignored by the coaching pipeline.';

COMMIT;
