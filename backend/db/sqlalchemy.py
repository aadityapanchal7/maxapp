"""
SQLAlchemy Database Connection Manager
Async PostgreSQL via Supabase (user-specific data)
"""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator
from config import settings


def _clean_asyncpg_url(raw_url: str) -> str:
    """Strip query params that asyncpg doesn't understand (e.g. ?pgbouncer=true)."""
    parsed = urlparse(raw_url)
    if not parsed.query:
        return raw_url
    known = {"ssl", "sslmode", "sslcert", "sslkey", "sslrootcert", "sslpassword"}
    qs = parse_qs(parsed.query)
    filtered = {k: v for k, v in qs.items() if k.lower() in known}
    clean = parsed._replace(query=urlencode(filtered, doseq=True) if filtered else "")
    return urlunparse(clean)


def _connection_mode() -> str:
    """Resolve the ACTUAL Supabase connection mode from host + port.

    This is the crux of the MaxClientsInSessionMode (EMAXCONNSESSION) error.
    Supabase exposes three endpoints and only one scales:
      - direct  `db.<ref>.supabase.co:5432`            — no pooler, ~60 conn cap
      - session `aws-0-<region>.pooler.supabase.com:5432` — Supavisor SESSION mode,
                 each client holds a dedicated backend, GLOBAL cap ~15 clients
      - txn     `aws-0-<region>.pooler.supabase.com:6543` — Supavisor TRANSACTION
                 mode, multiplexes thousands of clients onto a few backends

    Transaction mode requires BOTH the pooler host AND port 6543 (and a tenant
    username `postgres.<ref>`). Setting only the port to 6543 while the host is
    still the direct/session endpoint does NOT give transaction mode — so we key
    the pool sizing off this resolved mode, never off the port alone. Otherwise a
    half-config would size the pool UP (to 20) while the connection stays in
    session mode (cap 15) — which is exactly what makes EMAXCONNSESSION worse.
    """
    port = getattr(settings, "supabase_db_port", 5432)
    host = (getattr(settings, "supabase_db_host", "") or "").lower()
    is_pooler = "pooler.supabase" in host
    if is_pooler and port == 6543:
        return "transaction"
    if is_pooler:
        return "session"
    return "direct"


def _supabase_connect_args() -> dict:
    """asyncpg connect args. Statement cache MUST be disabled through any
    Supabase pooler host (PgBouncer/Supavisor) or prepared statements break."""
    host = (getattr(settings, "supabase_db_host", "") or "").lower()
    port = getattr(settings, "supabase_db_port", 5432)
    through_pooler = "pooler.supabase" in host or port == 6543

    server_settings = {"application_name": "maxapp_backend"}
    # CRITICAL: Supabase's Supavisor pooler only permits a whitelist of startup
    # parameters. Sending `search_path` in the asyncpg startup packet makes the
    # pooler CLOSE the connection immediately — surfacing as
    # "connection was closed in the middle of operation" on the FIRST query, which
    # silently breaks every DB call (login/signup included) in production.
    # The DB role already defaults search_path to `public, extensions` (so pgvector's
    # `vector` type still resolves unqualified), so we only set it as a startup param
    # on a DIRECT connection — never through Supavisor.
    if not through_pooler:
        server_settings["search_path"] = "public,extensions"

    # A local Postgres (localhost dev / CI) usually isn't configured for TLS, so
    # requiring SSL there fails the connection. Supabase always needs it.
    is_local = host in {"", "localhost", "127.0.0.1", "::1"}
    args: dict = {
        "timeout": 10,
        "command_timeout": 15,
        "ssl": False if is_local else "require",
        "server_settings": server_settings,
    }
    if through_pooler:
        args["statement_cache_size"] = 0
    return args


def _pool_params() -> dict:
    """Size the connection pool to the RESOLVED connection mode (not the port).

    Session mode shares a GLOBAL ~15-client cap across every worker, instance
    AND the scheduler — so the per-process pool must stay tiny or several
    workers collectively blow the cap. Transaction mode has no such cap, so a
    larger pool is safe and needed for real concurrency. Env values win when set.
    Recommended production: pooler host + SUPABASE_DB_PORT=6543 + user
    `postgres.<project-ref>`.
    """
    mode = _connection_mode()
    env_size = getattr(settings, "supabase_db_pool_size", None)
    env_overflow = getattr(settings, "supabase_db_max_overflow", None)
    if mode == "transaction":
        size = env_size or 10
        overflow = env_overflow or 10
        recycle = 900
    elif mode == "direct":
        size = env_size or 5
        overflow = env_overflow or 5
        recycle = 300
    else:
        # Session mode: stay well under the ~15 GLOBAL client cap. Per process.
        size = env_size or 2
        overflow = env_overflow or 1
        recycle = 180
    return {"pool_size": int(size), "max_overflow": int(overflow), "pool_recycle": recycle}


def _log_db_config() -> None:
    """Print the resolved DB connection mode + pool at boot so misconfig is
    visible in Render logs at a glance (the EMAXCONNSESSION fix is usually an
    env change, and this tells you immediately whether it took effect)."""
    mode = _connection_mode()
    host = (getattr(settings, "supabase_db_host", "") or "")
    port = getattr(settings, "supabase_db_port", 5432)
    user = (getattr(settings, "supabase_db_user", "") or "")
    pp = _pool_params()
    print(f"[DB] mode={mode} host={host} port={port} "
          f"pool_size={pp['pool_size']} max_overflow={pp['max_overflow']}")
    if mode == "session":
        print("[DB][WARN] SESSION mode — global ~15-client cap (EMAXCONNSESSION risk). "
              "For scale set the POOLER host (aws-0-<region>.pooler.supabase.com) + "
              "SUPABASE_DB_PORT=6543 (Transaction mode).")
    if mode != "direct" and "." not in user:
        print(f"[DB][WARN] Pooler host but user='{user}' has no project ref. Supavisor "
              "usually needs SUPABASE_DB_USER=postgres.<project-ref> — without it the "
              "pooler can reject/fallback and you stay session-capped.")
    if port == 6543 and "pooler.supabase" not in host.lower():
        print("[DB][WARN] PORT=6543 but host is not a pooler host — transaction mode "
              "needs the aws-0-<region>.pooler.supabase.com host. This will not connect "
              "in transaction mode.")


_log_db_config()

engine = create_async_engine(
    _clean_asyncpg_url(settings.supabase_db_url),
    echo=getattr(settings, "sql_echo", False),
    pool_timeout=5,
    pool_pre_ping=True,
    connect_args=_supabase_connect_args(),
    **_pool_params(),
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def release_conn(db: AsyncSession) -> None:
    """Hand this session's pooled connection back before a LONG external await
    (LLM/vision call, third-party HTTP).

    A SQLAlchemy session keeps its connection checked out for the life of its
    transaction, and this process only has pool_size + max_overflow connections
    total. Awaiting a 30-120s model call mid-transaction therefore pins one of
    those few slots for the whole call, so a handful of concurrent requests can
    exhaust the pool and make EVERY endpoint (including boot) fail on
    pool_timeout — an app-wide outage, not merely a slow feature.

    Ending the transaction returns the connection; the session transparently
    checks out a new one on its next query, and expire_on_commit=False keeps
    already-loaded objects usable in between. Call this only where pending work
    is safe to persist (it commits).
    """
    try:
        await db.commit()
    except Exception as e:  # never let connection hygiene break the request
        logger.warning("release_conn failed (non-fatal): %s", e)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for database sessions
    Usage: db: AsyncSession = Depends(get_db)

    Use a plain `yield` inside `async with` only. Extra try/finally + session.close()
    duplicates the context manager exit and can break FastAPI's generator cleanup
    (RuntimeError: generator didn't stop after athrow()).
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database tables"""
    try:
        await _terminate_stale_connections()

        from models.sqlalchemy_models import Base
        tables_to_create = list(Base.metadata.sorted_tables)
        # create_all runs one statement batch — a single failing table (e.g.
        # rag_documents needs pgvector, absent on local Postgres) used to abort
        # the WHOLE init, silently skipping every column migration below. Fall
        # back to per-table creation so one bad table can't starve the rest.
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET search_path TO public, extensions"))
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create)
                )
            print("[OK] Supabase tables created/verified")
        except Exception as batch_err:
            print(f"[WARNING] Batch create_all failed ({batch_err}); retrying per-table")
            for table in tables_to_create:
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text("SET search_path TO public, extensions"))
                        await conn.run_sync(
                            lambda sync_conn, t=table: Base.metadata.create_all(sync_conn, tables=[t])
                        )
                except Exception as te:
                    print(f"[WARNING] Could not create table {table.name}: {te}")
            print("[OK] Supabase tables created/verified (per-table fallback)")

        # app_users alters in their own transaction so a lock failure on other tables
        # cannot roll back critical columns (e.g. last_username_change).
        await _run_app_users_column_migrations()
        await _run_chat_history_column_migrations()
        await _run_column_migrations()
    except Exception as e:
        print(f"[WARNING] Could not initialize Supabase database: {e}")
        print("[INFO] Ensure Supabase is accessible from deployment environment.")


async def _terminate_stale_connections():
    """Kill leftover connections from a previous server instance that may hold locks."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE application_name = 'maxapp_backend' "
                "AND pid <> pg_backend_pid() "
                "AND state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')"
            ))
            terminated = result.rowcount
            if terminated:
                print(f"[OK] Terminated {terminated} stale backend connection(s)")
    except Exception as e:
        print(f"[INFO] Could not clean stale connections: {e}")


async def _run_app_users_column_migrations():
    """Add app_users columns in a dedicated transaction (commits even if other migrations fail)."""
    statements = [
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS last_username_change TIMESTAMPTZ",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_context TEXT DEFAULT ''",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS ai_summaries JSONB DEFAULT '[]'",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS apns_device_token TEXT",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS apns_token_updated_at TIMESTAMPTZ",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS coaching_tone VARCHAR DEFAULT 'default'",
        # Google Sign-In (identity): the verified Google subject id (stable per
        # account) and which method created the account. password_hash stays a
        # random unusable value for OAuth-only users.
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS google_sub VARCHAR",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR DEFAULT 'password'",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_app_users_google_sub ON app_users (google_sub) WHERE google_sub IS NOT NULL",
        # Sign in with Apple (identity): the verified Apple subject id (stable
        # per account). Required for App Store guideline 4.8 (equivalent login).
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS apple_sub VARCHAR",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_app_users_apple_sub ON app_users (apple_sub) WHERE apple_sub IS NOT NULL",
        # subscription_id was unique but Apple reuses originalTransactionId across renewals
        "ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_subscription_id_key",
        # Billing provider ('apple' | 'stripe' | 'referral_comp' | ...). This is
        # SELECTed on every user load (User.billing_provider); a migration for it
        # was accidentally dropped in an unrelated commit, so freshly-provisioned
        # or restored app_users tables 500 the whole app without it. Re-added.
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS billing_provider VARCHAR",
        # Referral attribution — mapped on the User model but never previously
        # added by any migration, so any DB predating these columns 500s on every
        # request that loads a user (login, /me, chat, scans — the whole app).
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS referred_by_code_id UUID",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS referral_source VARCHAR",
        # Creator platform: gates the Creator Studio. SELECTed on every user load
        # via _user_dict, so a missing column would 500 the whole app — always
        # ship the ALTER when adding a User column (schema-drift rule).
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS is_creator BOOLEAN DEFAULT FALSE",
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            for sql in statements:
                await conn.execute(text(sql))
        print("[OK] app_users column migrations applied")
    except Exception as e:
        print(f"[WARNING] app_users column migrations: {e}")


async def _run_chat_history_column_migrations():
    """Add chat_history columns + multi-conversation wiring.

    Each migration runs in its OWN transaction so a failure in one can't roll
    back the others. Previously the conversation_id FK + backfill block was
    grouped with the basic-column adds in a single transaction — if Supabase
    perms or `chat_conversations` not-yet-existing made the FK ALTER fail,
    `retrieved_chunk_ids` and `conversation_id` itself both rolled back too.
    Production hit exactly this and queries that selected `conversation_id`
    started 500ing.

    retrieved_chunk_ids: the RAG refactor changed the column type from
    BIGINT[] to JSONB. We only drop+re-add it when the existing type is
    not already JSONB so the audit trail isn't wiped on every boot.
    """
    # ---- 1. Basic columns. These must succeed independently of any other
    # table's existence. -----------------------------------------------------
    basic_statements = [
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS channel VARCHAR DEFAULT 'app'",
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chat_history'
                  AND column_name = 'retrieved_chunk_ids'
                  AND data_type <> 'jsonb'
            ) THEN
                ALTER TABLE chat_history DROP COLUMN retrieved_chunk_ids;
            END IF;
        END $$;
        """,
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS retrieved_chunk_ids JSONB",
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS partner_rule_ids BIGINT[]",
        # iMessage-style reply-to reference. Self-FK with SET NULL so
        # deleting the original message orphans replies instead of
        # cascading. Nullable — most messages don't reply to anything.
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS reply_to_id uuid REFERENCES chat_history(id) ON DELETE SET NULL",
    ]
    for sql in basic_statements:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET lock_timeout = '30s'"))
                await conn.execute(text(sql))
        except Exception as e:
            print(f"[WARNING] chat_history basic migration failed: {e}")

    # ---- 2. Ensure chat_conversations table exists. create_all() should
    # have done this from the ORM model, but if Supabase RLS or a transient
    # error blocked it, we recreate it here from the canonical SQL so the
    # subsequent FK + index + backfill don't fail with "relation does not
    # exist". ----------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.chat_conversations (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id uuid NOT NULL,
                    title varchar(120) NOT NULL DEFAULT 'new chat',
                    channel varchar NOT NULL DEFAULT 'app',
                    is_archived boolean NOT NULL DEFAULT false,
                    last_message_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            # channel is mapped on ChatConversation and FILTERED in queries
            # (resolve_active_conversation), so any pre-existing table without it
            # 500s all chat. Add it as its own idempotent ALTER for existing DBs.
            await conn.execute(text(
                "ALTER TABLE public.chat_conversations "
                "ADD COLUMN IF NOT EXISTS channel varchar NOT NULL DEFAULT 'app'"
            ))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chat_conversations_user
                    ON public.chat_conversations(user_id, is_archived, last_message_at DESC)
            """))
    except Exception as e:
        print(f"[WARNING] chat_conversations bootstrap failed: {e}")

    # ---- 3. Add conversation_id column WITHOUT the FK constraint first.
    # The column is what the ORM SELECTs reference — it must exist even if
    # the FK can't be installed (e.g. permission lockouts, lock contention).
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text(
                "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS conversation_id uuid"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_chat_history_conversation "
                "ON chat_history(conversation_id, created_at)"
            ))
        print("[OK] chat_history.conversation_id column ensured")
    except Exception as e:
        print(f"[WARNING] chat_history.conversation_id column add failed: {e}")

    # ---- 4. Best-effort: install FK constraint pointing at chat_conversations.
    # If this fails (e.g. orphan rows, permissions), we keep the column
    # without referential integrity rather than blowing up the whole boot.
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'chat_history'
                          AND constraint_name = 'chat_history_conversation_id_fkey'
                    ) AND EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'chat_conversations'
                    ) THEN
                        ALTER TABLE chat_history
                            ADD CONSTRAINT chat_history_conversation_id_fkey
                            FOREIGN KEY (conversation_id)
                            REFERENCES chat_conversations(id)
                            ON DELETE CASCADE;
                    END IF;
                END $$;
            """))
    except Exception as e:
        print(f"[WARNING] chat_history.conversation_id FK install skipped: {e}")

    # ---- 5. One-time backfill so legacy rows have a thread to live in.
    # Each runs idempotently — the WHERE clauses guard on conversation_id
    # IS NULL, so re-running is a no-op once everything is migrated.
    # -----------------------------------------------------------------------
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '30s'"))
            await conn.execute(text("""
                INSERT INTO chat_conversations (user_id, title, last_message_at)
                SELECT ch.user_id, 'Chat history', MAX(ch.created_at)
                FROM chat_history ch
                WHERE ch.conversation_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM chat_conversations cc
                      WHERE cc.user_id = ch.user_id
                  )
                GROUP BY ch.user_id
            """))
            await conn.execute(text("""
                UPDATE chat_history ch
                SET conversation_id = cc.id
                FROM chat_conversations cc
                WHERE ch.conversation_id IS NULL
                  AND cc.user_id = ch.user_id
                  AND cc.title = 'Chat history'
            """))
        print("[OK] chat_history conversation_id backfill complete")
    except Exception as e:
        print(f"[WARNING] chat_history conversation_id backfill skipped: {e}")


async def _run_column_migrations():
    """Add missing columns to existing tables (safe to run repeatedly).

    Each migration runs in its own transaction so a lock timeout or failure on
    one table (e.g. user_schedules held by another session) does not abort the
    others.
    """
    migrations = [
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'app'",
        "ALTER TABLE user_progress_photos ADD COLUMN IF NOT EXISTS face_rating DOUBLE PRECISION",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_type VARCHAR DEFAULT 'course'",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS maxx_id VARCHAR",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS schedule_context JSONB DEFAULT '{}'",
        "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS is_scan_user BOOLEAN DEFAULT FALSE",
        "ALTER TABLE user_schedules ALTER COLUMN course_id DROP NOT NULL",
        "ALTER TABLE user_schedules ALTER COLUMN module_number DROP NOT NULL",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS reflow_state JSONB DEFAULT '{}'",
        "ALTER TABLE user_schedules ADD COLUMN IF NOT EXISTS jitai_state JSONB DEFAULT '{}'",
        "ALTER TABLE calendar_connections ADD COLUMN IF NOT EXISTS tokens JSONB DEFAULT '{}'",
        # tokens_encrypted (BYTEA) holds the Fernet-encrypted OAuth tokens. The model
        # (CalendarConnection.tokens_decrypted) SELECTs it, so a missing column 500s
        # /google/status — which the Connect Google Calendar button reads.
        "ALTER TABLE calendar_connections ADD COLUMN IF NOT EXISTS tokens_encrypted BYTEA",
        "ALTER TABLE user_places ADD COLUMN IF NOT EXISTS address VARCHAR",
        # creator_applications.social_stats added after the table shipped — the
        # column won't exist on a DB created from the first version of the table.
        "ALTER TABLE creator_applications ADD COLUMN IF NOT EXISTS social_stats JSONB DEFAULT '{}'",
        # creator_social_connections — OAuth-verified IG/TikTok for creator apply.
        """
        CREATE TABLE IF NOT EXISTS creator_social_connections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            platform varchar(16) NOT NULL,
            platform_user_id varchar(128),
            handle varchar(128),
            profile jsonb DEFAULT '{}',
            access_token_encrypted bytea,
            refresh_token_encrypted bytea,
            token_expires_at timestamptz,
            connected_at timestamptz,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_creator_social_user ON creator_social_connections (user_id, platform)",
        "ALTER TABLE creator_applications ADD COLUMN IF NOT EXISTS max_differentiator TEXT",
        "ALTER TABLE creator_applications ADD COLUMN IF NOT EXISTS brand_fit TEXT",
        "ALTER TABLE creator_applications ADD COLUMN IF NOT EXISTS course_docs JSONB DEFAULT '[]'",
        """
        CREATE TABLE IF NOT EXISTS user_inbox_messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            title varchar(120) NOT NULL,
            body text NOT NULL,
            sender_id uuid REFERENCES app_users(id) ON DELETE SET NULL,
            read_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_inbox_user_created ON user_inbox_messages (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_inbox_unread ON user_inbox_messages (user_id, read_at)",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS onboarding_step INTEGER DEFAULT 0",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS knowledge_docs JSONB DEFAULT '[]'",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS intro_video_url VARCHAR",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS welcome_message TEXT DEFAULT ''",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS onboarding_meta JSONB DEFAULT '{}'",
        "ALTER TABLE creator_habits ADD COLUMN IF NOT EXISTS targeting_conditions JSONB DEFAULT '[]'",
        "ALTER TABLE creator_habits ADD COLUMN IF NOT EXISTS sample_questions JSONB DEFAULT '[]'",
        """
        CREATE TABLE IF NOT EXISTS creator_voice_samples (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            creator_id uuid NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            question text NOT NULL,
            creator_answer text,
            draft_answer text,
            approved boolean,
            status varchar(24) NOT NULL DEFAULT 'pending',
            sort integer DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_creator_voice_creator ON creator_voice_samples (creator_id, sort)",
        # Creator maxxes as first-class maxxes: lesson paywall fields, module
        # titles, marketplace art, habit versioning, price snapshot, and push
        # deep-link params. (creator_habits is a NEW table — create_all makes it.)
        "ALTER TABLE creator_course_lessons ADD COLUMN IF NOT EXISTS is_free_preview BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE creator_course_lessons ADD COLUMN IF NOT EXISTS duration_minutes INTEGER",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS course_modules JSON DEFAULT '{}'",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS art_url VARCHAR",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS art_status VARCHAR DEFAULT 'none'",
        "ALTER TABLE creators ADD COLUMN IF NOT EXISTS habits_version INTEGER DEFAULT 1",
        "ALTER TABLE creator_subscriptions ADD COLUMN IF NOT EXISTS price_cents_at_purchase INTEGER",
        "ALTER TABLE scheduled_notifications ADD COLUMN IF NOT EXISTS deep_link_params JSON",
        # Weekly-reset idempotency marker (see scheduler_job.send_weekly_resets).
        "ALTER TABLE user_coaching_state ADD COLUMN IF NOT EXISTS last_weekly_reset_iso_week VARCHAR",
        # Composite indexes — create_all() never retro-adds indexes to existing
        # tables, so add them here. These cover the achievement counts on the hot
        # /schedules/active/full endpoint + active-schedule reads.
        "CREATE INDEX IF NOT EXISTS idx_scans_user_status ON scans (user_id, processing_status)",
        "CREATE INDEX IF NOT EXISTS idx_user_memories_user_status ON user_memories (user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_user_schedules_user_active ON user_schedules (user_id, is_active, created_at DESC)",
        # Single-plan pivot (2026-07): Chad Lite is retired — every paying Lite
        # subscriber is grandfathered INTO Chad (they keep their old Apple price;
        # apple_iap_service.tier_for_product_id maps the basic SKU to premium so
        # renewals never downgrade them back). The one-time upgrade also flags
        # profile.chad_upgrade_notice, which the app shows as a thank-you popup
        # and clears via POST /users/ack-chad-upgrade. Idempotent: after the
        # first run no rows match.
        """
        UPDATE app_users
        SET subscription_tier = 'premium',
            profile = (COALESCE(profile, '{}'::json)::jsonb || '{"chad_upgrade_notice": true}'::jsonb)::json,
            updated_at = NOW()
        WHERE is_paid IS TRUE AND lower(COALESCE(subscription_tier, '')) = 'basic'
        """,
    ]
    applied = 0
    for sql in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SET lock_timeout = '5s'"))
                await conn.execute(text(sql))
            applied += 1
        except Exception as e:
            print(f"[INFO] Column migration skipped ({sql[:80]}...): {e}")
    print(f"[OK] Column migrations applied ({applied}/{len(migrations)})")

    # rag_documents.embedding → nullable so content can be added/edited without vectors
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            await conn.execute(text(
                "ALTER TABLE rag_documents ALTER COLUMN embedding DROP NOT NULL"
            ))
        print("[OK] rag_documents.embedding made nullable")
    except Exception as e:
        print(f"[INFO] rag_documents embedding migration note: {e}")

    # Ensure rag_documents.id auto-generates UUIDs for ingest inserts that omit id.
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await conn.execute(text(
                "ALTER TABLE rag_documents ALTER COLUMN id SET DEFAULT gen_random_uuid()"
            ))
        print("[OK] rag_documents.id default UUID ensured")
    except Exception as e:
        print(f"[INFO] rag_documents id default migration note: {e}")

    # Prevent DUPLICATE active maxx schedules (double-tap / network retry on
    # "add a max"). First collapse any existing duplicates to the newest row per
    # (user_id, maxx_id), then enforce it with a partial unique index. The index
    # only covers active maxx rows — course schedules (maxx_id NULL) and
    # deactivated history are unaffected.
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            await conn.execute(text("""
                UPDATE user_schedules s
                SET is_active = FALSE, updated_at = NOW()
                WHERE s.is_active = TRUE
                  AND s.maxx_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM user_schedules s2
                      WHERE s2.user_id = s.user_id
                        AND s2.maxx_id = s.maxx_id
                        AND s2.is_active = TRUE
                        AND (s2.created_at > s.created_at
                             OR (s2.created_at = s.created_at AND s2.id > s.id))
                  )
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_schedules_active_maxx
                ON user_schedules (user_id, maxx_id)
                WHERE is_active = TRUE AND maxx_id IS NOT NULL
            """))
        print("[OK] user_schedules active-maxx uniqueness enforced")
    except Exception as e:
        print(f"[INFO] user_schedules uniqueness migration note: {e}")

async def close_db():
    """Close database connections"""
    try:
        await engine.dispose()
        print("[OK] Supabase connection closed")
    except Exception:
        pass
