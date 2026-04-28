-- Multi-conversation chat support.
-- Idempotent; safe to replay.
--
-- Adds:
--   * chat_conversations table — one row per named chat thread per user
--   * chat_history.conversation_id — nullable FK so legacy rows keep working
--
-- On first run this also backfills legacy chat_history rows into a single
-- "Chat history" conversation per user, so every existing message stays
-- visible under the new UI.

BEGIN;

CREATE TABLE IF NOT EXISTS public.chat_conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL
        REFERENCES public.app_users(id) ON DELETE CASCADE,
    title text NOT NULL DEFAULT 'new chat',
    channel varchar NOT NULL DEFAULT 'app',
    is_archived boolean NOT NULL DEFAULT false,
    last_message_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user
    ON public.chat_conversations(user_id, is_archived, last_message_at DESC);

COMMENT ON TABLE public.chat_conversations IS
    'Named chat threads per user. One row per conversation the mobile client can switch between.';
COMMENT ON COLUMN public.chat_conversations.title IS
    'Human-readable title. Auto-seeded from first user message; renamable.';
COMMENT ON COLUMN public.chat_conversations.last_message_at IS
    'Updated on every message insert so the list can sort by recency.';

ALTER TABLE public.chat_history
    ADD COLUMN IF NOT EXISTS conversation_id uuid
        REFERENCES public.chat_conversations(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_chat_history_conversation
    ON public.chat_history(conversation_id, created_at);

-- Backfill: give every existing user with chat_history one "Chat history"
-- conversation and attach their legacy rows to it. Runs once: subsequent
-- replays are no-ops because we only insert for users without a
-- conversation_id on ANY of their rows.
INSERT INTO public.chat_conversations (user_id, title, last_message_at)
SELECT
    ch.user_id,
    'Chat history',
    MAX(ch.created_at)
FROM public.chat_history ch
WHERE ch.conversation_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.chat_conversations cc
      WHERE cc.user_id = ch.user_id
  )
GROUP BY ch.user_id;

UPDATE public.chat_history ch
SET conversation_id = cc.id
FROM public.chat_conversations cc
WHERE ch.conversation_id IS NULL
  AND cc.user_id = ch.user_id
  AND cc.title = 'Chat history';

COMMIT;
