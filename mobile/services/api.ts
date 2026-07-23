/**
 * API Service - Backend communication
 */

import axios, { AxiosInstance } from 'axios';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { getItemAsync, setItemAsync, deleteItemAsync } from './storage';

export interface PersonalMemory {
    id: string;
    dimension: string;
    key?: string | null;
    text: string;
    value?: any;
    source: string;
    confidence?: number | null;
    created_at?: string | null;
    updated_at?: string | null;
}

export interface PersonalizationProfile {
    profile: Record<string, Record<string, any>>;
    completeness: Record<string, number>;
    brief?: string | null;
    sources: string[];
    dimensions: string[];
    memories: PersonalMemory[];
    memories_by_dimension: Record<string, PersonalMemory[]>;
}

export type AchievementTier = 'bronze' | 'silver' | 'gold';

export interface AchievementItem {
    code: string;
    title: string;
    description: string;
    tier: AchievementTier;
    category: string;
    icon: string;
    earned: boolean;
    seen: boolean;
    progress?: { current: number; target: number } | null;
}

export interface AchievementsResponse {
    achievements: AchievementItem[];
    earned_count: number;
    total: number;
    categories: string[];
}

export interface EarnedAchievement {
    code: string;
    title: string;
    description: string;
    tier: AchievementTier;
    icon: string;
    category?: string;
}

/** A structured visual emitted by the assistant (rendered natively in chat). */
export interface VisualBlock {
    type: 'table' | 'comparison' | 'timeline' | 'flowchart' | 'stat_cards' | 'checklist';
    title?: string | null;
    data: Record<string, any>;
}

/** How confident the assistant is in a specific method it proposed. */
export interface MethodConfidence {
    title: string;
    confidence: number; // 0-100
    rationale?: string | null;
    sources?: string[] | null;
}

/** XP + rank block served by /schedules/active/full. */
export interface Gamification {
    current_xp: number;
    current_level: number;
    rank: string;
    xp_earned_today: number;
    xp_into_level: number;
    xp_for_next_level: number;
    next_level_at: number;
    is_max_level: boolean;
    /** Active streak multiplier on task XP (1.0 / 1.1 / 1.25 / 1.5). */
    streak_multiplier?: number;
}

export interface MarketplaceItem {
    type: 'maxx' | 'course';
    id: string;
    title: string;
    tagline: string;
    icon: string;
    color: string;
    price_cents: number;
    price_model: 'weekly' | 'flat' | 'monthly' | 'included';
    price_label: string;
    weeks?: number | null;
    creator: { name: string; handle: string; verified: boolean; avatar?: string | null };
    native: boolean;
    entered: boolean;
    category?: string | null;
    rating?: number | null;
    participants?: number;
    completion_rate?: number | null;
    image_url?: string | null;
    detail?: MarketplaceItemDetail;
    // ── Creator-maxx card fields (first-class creator programs) ──
    /** True when this card is a live creator maxx (id = the creator's maxx_id). */
    creator_maxx?: boolean;
    art_status?: string;
    apple_product_id?: string;
    price_tier?: string;
    published_lesson_count?: number;
    habit_count?: number;
}

/** Card-shape discriminator: is this marketplace item a first-class creator maxx? */
export function isCreatorMaxx(item: { creator_maxx?: boolean } | null | undefined): boolean {
    return !!item?.creator_maxx;
}

/** One habit row of a creator maxx's daily program (marketplace detail). */
export interface CreatorHabit {
    title: string;
    description?: string;
    duration_minutes?: number;
    frequency?: { type: 'daily' | 'n_per_week'; n?: number };
    window?: 'morning' | 'evening' | 'any' | string;
    icon?: string;
}

/** Studio habit row (GET /creators/me/habits) — identity + ordering included. */
export interface CreatorHabitRow {
    id: string;
    slug: string;
    title: string;
    description: string;
    duration_minutes: number;
    frequency: { type: 'daily' | 'n_per_week'; n?: number };
    window: 'morning' | 'evening' | 'any';
    icon?: string | null;
    sort: number;
}

/** PUT /creators/me/habits input row — id omitted for new habits (server mints
 *  slugs); rows omitted from the list are archived server-side. */
export interface CreatorHabitInput {
    id?: string;
    title: string;
    description?: string;
    duration_minutes: number;
    frequency: { type: 'daily' | 'n_per_week'; n?: number };
    window: 'morning' | 'evening' | 'any';
    icon?: string;
}

export interface MarketplaceItemDetail {
    long_description?: string;
    outcomes?: string[];
    for_you_if?: string[];
    curriculum?: { title: string; lessons: string[] }[];
    bio?: string;
    credentials?: string[];
    reviews?: { name: string; avatar?: string; rating: number; text: string }[];
    faqs?: { q: string; a: string }[];
    guarantee?: string;
    gallery?: string[];
    video_url?: string;
    inside_video?: string;
    // ── Creator-maxx detail (GET /marketplace/item/{maxx_id}) ──
    /** The creator's daily program rows ("THE DAILY PROGRAM" card). */
    habits?: CreatorHabit[];
    socials?: Record<string, any>;
    subscription?: {
        price_cents: number;
        price_label: string;
        apple_product_id?: string;
        price_tier?: string;
    };
}

export interface SocialProfile {
    platform: 'instagram' | 'tiktok';
    handle: string;
    url: string | null;
    followers: number | null;
    avatar_url: string | null;
    full_name: string | null;
    verified: boolean;
    found: boolean;
    oauth_verified?: boolean;
}

export interface CreatorSocialConnection {
    platform: 'instagram' | 'tiktok';
    handle: string | null;
    platform_user_id: string | null;
    full_name: string | null;
    avatar_url: string | null;
    followers: number | null;
    verified: boolean;
    mock?: boolean;
    connected_at: string | null;
}

export interface CreatorSocialStatus {
    providers: Record<'instagram' | 'tiktok', { available: boolean }>;
    connections: Record<'instagram' | 'tiktok', CreatorSocialConnection | null>;
}

export interface InboxMessage {
    id: string;
    title: string;
    body: string;
    read_at: string | null;
    created_at: string | null;
}

export interface CreatorHabitTemplate {
    id: string;
    title: string;
    description?: string;
    duration_minutes?: number;
    frequency_type?: string;
    frequency_n?: number;
    window?: string;
    tags?: string[];
    conditions?: string[];
    sample_questions?: string[];
    enabled?: boolean;
}

export interface TestDriveState {
    step_index: number;
    total_steps: number;
    current: {
        id: string;
        question: string;
        options: string[];
        index: number;
        total: number;
    } | null;
    answers: Record<string, string>;
    schedule: {
        day: string;
        focus: string;
        tasks: { title: string; duration_min: number; window: string }[];
    }[];
    complete: boolean;
}

export interface CreatorOnboardingState {
    step: number;
    complete: boolean;
    max_name: string;
    display_name: string;
    knowledge_docs: { filename: string; url: string; source?: string }[];
    protocols_pct: number;
    voice_pct: number;
    voice_phase: number;
    voice_samples_total: number;
    voice_samples_answered: number;
    current_voice_sample: {
        id: string;
        question: string;
        draft_answer: string | null;
        status: string;
        sort?: number;
        sample_phase?: number;
        index?: number;
    } | null;
    habit_library: CreatorHabitTemplate[];
    targeting_presets?: string[];
    price_tier: string;
    price_cents: number;
    price_tiers: Record<string, number>;
    intro_video_url: string | null;
    welcome_message: string;
    test_chat: { role: string; text: string }[];
    test_drive?: TestDriveState;
    status: string;
}

export interface ReferralValidateResult {
    valid: boolean;
    kind?: 'free_comp' | 'discount' | 'referral';
    free?: boolean;
    discount?: { kind?: string; value?: number | null; label?: string } | null;
    message: string;
    reason?: string | null;
}

export interface ReferralRedeemResult {
    result: 'comped' | 'discount_applied' | 'attributed';
    kind: string;
    free: boolean;
    discount?: { kind?: string; value?: number | null; label?: string } | null;
    redemption_id: string;
    idempotent: boolean;
    message: string;
    discount_status?: 'coming_soon' | 'apple_offer' | 'stripe';
    apple_offer_code?: string | null;
    apple_offer_id?: string | null;
    stripe_promotion_code?: string | null;
}

function envTargetsLoopback(url: string): boolean {
    return /localhost|127\.0\.0\.1|\[::1\]/i.test(url);
}

/** RFC1918 IPv4 — page opened as http://192.168.x.x:8081 (e.g. phone browser on LAN). */
function isPrivateLanIPv4(hostname: string): boolean {
    if (!/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname)) return false;
    const parts = hostname.split('.').map((p) => parseInt(p, 10));
    if (parts.some((n) => Number.isNaN(n) || n > 255)) return false;
    const [a, b] = parts;
    if (a === 10) return true;
    if (a === 192 && b === 168) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    return false;
}

function replaceUrlHostname(url: string, hostname: string): string {
    try {
        const u = new URL(url);
        u.hostname = hostname;
        let out = u.toString();
        if (url.endsWith('/') && !out.endsWith('/')) out += '/';
        return out;
    } catch {
        return url;
    }
}

/**
 * Expo Go / dev client report the machine IP in debuggerHost (e.g. 192.168.1.5:8081).
 * Physical devices must call the API on that host, not 127.0.0.1.
 */
function ipv4HostFromDevUri(raw: string | undefined | null): string | null {
    if (!raw) return null;
    const host = raw.split(':')[0]?.trim();
    if (!host || host === 'localhost') return null;
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return null;
    return host;
}

function getExpoDevBundlerHost(): string | null {
    if (!__DEV__) return null;
    const raw: string | undefined =
        Constants.expoGoConfig?.debuggerHost ??
        Constants.expoConfig?.hostUri ??
        (Constants.manifest2 as { debuggerHost?: string } | undefined)?.debuggerHost ??
        (Constants.manifest as { debuggerHost?: string } | undefined)?.debuggerHost;
    return ipv4HostFromDevUri(raw);
}

/**
 * - Web localhost: match page hostname (localhost vs 127.0.0.1) for PNA / cookies.
 * - Web on LAN IP: point API at same host as the page (phone browser → Mac).
 * - Native dev: if .env is still loopback, use Metro's dev-machine IP (physical iPhone).
 *   If Metro host detection fails on a real device, fall back to the production URL so
 *   the app is never silently dead (SDK 54 dev client doesn't expose debuggerHost outside
 *   Expo Go when npx expo start is run without --lan).
 */
function resolveApiBaseUrl(): string {
    const envValue = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
    // Fail fast in production builds: shipping with EXPO_PUBLIC_API_BASE_URL unset
    // would silently point the app at localhost and every request would fail.
    if (!envValue && !__DEV__) {
        throw new Error(
            'EXPO_PUBLIC_API_BASE_URL is not set for this production build. ' +
            'Configure it in the EAS build profile before shipping.'
        );
    }
    const fromEnv = envValue || 'http://localhost:8000/api/';

    if (__DEV__ && Platform.OS !== 'web' && envTargetsLoopback(fromEnv)) {
        const devHost = getExpoDevBundlerHost();
        // Real device: Metro is reached over the LAN, so devHost is the Mac's LAN
        // IP. Swap the loopback host to it so the phone can reach the dev backend.
        if (devHost && isPrivateLanIPv4(devHost)) {
            const next = replaceUrlHostname(fromEnv, devHost);
            console.log(`[Max] API → ${next} (LAN swap; Metro host detected)`);
            return next;
        }
        // Simulator / localhost dev: loopback reaches the Mac directly and never
        // drifts with the network. Use the env URL verbatim. (Previously this fell
        // back to prod, which broke the local DEV drawer on the simulator whenever
        // the Wi-Fi/hotspot IP changed.)
        console.log(`[Max] API → ${fromEnv} (loopback verbatim; simulator/localhost dev)`);
        return fromEnv;
    }

    if (Platform.OS === 'web' && typeof window !== 'undefined' && __DEV__) {
        const host = window.location.hostname;
        const loopbackPage =
            host === 'localhost' ||
            host === '127.0.0.1' ||
            host === '[::1]' ||
            host === '::1';
        if (loopbackPage && envTargetsLoopback(fromEnv)) {
            const apiHost = host === '[::1]' || host === '::1' ? '127.0.0.1' : host;
            return replaceUrlHostname(fromEnv, apiHost);
        }
        if (isPrivateLanIPv4(host) && envTargetsLoopback(fromEnv)) {
            return replaceUrlHostname(fromEnv, host);
        }
    }

    return fromEnv;
}

const API_BASE_URL = resolveApiBaseUrl();

/** Longer timeouts for web cold starts + DB on first auth request */
const WEB_AUTH_TIMEOUT_MS = 45_000;

/**
 * Auth-lost pub/sub: fired when the refresh token is rejected (user deleted,
 * signing key rotated, refresh token expired). AuthContext subscribes to tear
 * down the authenticated navigation stack so React Query hooks unmount and
 * stop hammering the server with re-auth attempts.
 */
type AuthLostListener = () => void;
const authLostListeners = new Set<AuthLostListener>();
export function subscribeAuthLost(listener: AuthLostListener): () => void {
    authLostListeners.add(listener);
    return () => {
        authLostListeners.delete(listener);
    };
}
function emitAuthLost(): void {
    for (const l of Array.from(authLostListeners)) {
        try {
            l();
        } catch {
            /* listener errors must not crash the interceptor */
        }
    }
}

class ApiService {
    private client: AxiosInstance;
    private accessToken: string | null = null;
    /** In-flight refresh promise so concurrent 401s don't stampede /auth/refresh. */
    private refreshInFlight: Promise<void> | null = null;
    /** Short cooldown after a failed refresh — block further refresh attempts so
     * a screen full of useQuery hooks can't trigger dozens of refreshes per second
     * while the UI tears down. */
    private refreshFailedUntil = 0;

    constructor() {
        this.client = axios.create({
            baseURL: API_BASE_URL,
            headers: { 'Content-Type': 'application/json' },
            /**
             * 12s default: fast-fail so retry interceptor can kick in before the user
             * gives up. Auth boot still has a finite deadline. Long-running endpoints
             * (AI chat, scans) override this per-request.
             */
            timeout: 12_000,
        });

        // Request interceptor for auth
        this.client.interceptors.request.use(async (config) => {
            const token = await this.getToken();
            if (token) {
                config.headers.Authorization = `Bearer ${token}`;
            }
            // RN FormData often fails `instanceof FormData` — detect append + name
            const d = config.data;
            const looksMultipart =
                (typeof FormData !== 'undefined' && d instanceof FormData) ||
                (!!d &&
                    typeof (d as any).append === 'function' &&
                    String((d as any).constructor?.name || '').toLowerCase().includes('formdata'));
            if (looksMultipart) {
                const h = config.headers as any;
                if (h?.delete) h.delete('Content-Type');
                else if (h) delete h['Content-Type'];
            }
            return config;
        });

        // Response interceptor: token refresh on 401, plus network-retry for idempotent GETs
        // so a single transient drop (subway, elevator) doesn't surface as "connection lost".
        this.client.interceptors.response.use(
            (response) => response,
            async (error) => {
                const cfg = error.config as
                    | ({ _retry?: boolean; _netRetries?: number } & typeof error.config)
                    | undefined;
                if (error.response?.status === 401 && cfg && !cfg._retry) {
                    cfg._retry = true;
                    // If a previous refresh just failed, skip straight to reject so
                    // React Query / screens can unmount without piling on more requests.
                    if (Date.now() < this.refreshFailedUntil) {
                        return Promise.reject(error);
                    }
                    try {
                        await this.refreshToken();
                        return this.client.request(cfg);
                    } catch {
                        return Promise.reject(error);
                    }
                }
                // Network error (no response = DNS fail / timeout / dropped connection).
                // Retry once with short backoff — catches subway/elevator/weak-signal
                // hiccups without making long-timeout calls hang for multiple minutes.
                // Callers can opt out via `_skipNetRetry: true` (e.g. chat AI where
                // the user is watching a spinner).
                const isNetErr = !error.response;
                const skip = (cfg as any)?._skipNetRetry === true;
                // ONLY idempotent GETs replay: a timeout can fire AFTER the
                // server processed the request, and replaying a POST would
                // double-create checkout sessions, calendar events, analytics.
                const method = String(cfg?.method || 'get').toLowerCase();
                if (isNetErr && cfg && !skip && method === 'get') {
                    cfg._netRetries = (cfg._netRetries ?? 0) + 1;
                    if (cfg._netRetries <= 1) {
                        await new Promise((r) => setTimeout(r, 500));
                        return this.client.request(cfg);
                    }
                }
                return Promise.reject(error);
            }
        );
    }

    getBaseUrl() {
        return API_BASE_URL;
    }

    /**
     * FastAPI exposes GET /health on the server root (not under /api).
     * Confirms the app can reach the same host as EXPO_PUBLIC_API_BASE_URL.
     */
    async checkBackendHealth(opts?: { timeoutMs?: number }): Promise<boolean> {
        try {
            const root = API_BASE_URL.replace(/\/?api\/?$/i, '').replace(/\/+$/, '');
            if (!root.startsWith('http')) return false;
            const timeout = opts?.timeoutMs ?? (Platform.OS === 'web' ? 12_000 : 5_000);
            const { data } = await axios.get<{ status?: string }>(`${root}/health`, {
                timeout,
            });
            return data?.status === 'healthy';
        } catch {
            return false;
        }
    }

    resolveAttachmentUrl(url?: string) {
        if (!url) return undefined;
        if (url.startsWith('http')) return url;
        // Construct base URL from API_BASE_URL (removing /api/)
        const baseUrl = API_BASE_URL.replace('/api/', '');
        return `${baseUrl}${url.startsWith('/') ? url : `/${url}`}`;
    }

    /**
     * WebSocket URL for forum channel realtime (access token in query).
     * Uses wss when API base is https.
     */
    async getForumChannelWebSocketUrl(channelId: string): Promise<string | null> {
        const token = await this.getToken();
        if (!token) return null;
        const base = API_BASE_URL.replace(/\/$/, '');
        const wsRoot = base.replace(/^https:\/\//i, 'wss://').replace(/^http:\/\//i, 'ws://');
        return `${wsRoot}/forums/ws/channel/${encodeURIComponent(channelId)}?token=${encodeURIComponent(token)}`;
    }

    private async getToken(): Promise<string | null> {
        if (this.accessToken) return this.accessToken;
        try {
            const t = await getItemAsync('access_token');
            // Cache in memory so a later secure-store hiccup can't drop the header.
            if (t) this.accessToken = t;
            return t;
        } catch {
            // NEVER let a secure-store read failure throw here: getToken() runs in
            // the request interceptor, so a throw would fail EVERY request (boot
            // getMe → Landing, "Get started" → error). Fall back to no token.
            return null;
        }
    }

    private async refreshToken(): Promise<void> {
        // Dedupe concurrent refreshes — a screen with N useQuery hooks would
        // otherwise fire N parallel POST /auth/refresh calls, each racing the
        // refresh-token rotation.
        if (this.refreshInFlight) {
            return this.refreshInFlight;
        }
        this.refreshInFlight = (async () => {
            try {
                const refreshToken = await getItemAsync('refresh_token');
                if (!refreshToken) throw new Error('No refresh token');

                const response = await axios.post(
                    `${API_BASE_URL}auth/refresh`,
                    { refresh_token: refreshToken },
                    // 45s, not 15s: a cold backend wake regularly outlives 15s, and a
                    // timed-out refresh at boot used to read as "session dead" — the
                    // #1 way mid-funnel users got dumped back to Landing.
                    { timeout: 45_000 },
                );
                await this.setTokens(response.data.access_token, response.data.refresh_token);
            } catch (e: any) {
                // Permanent auth failure: user deleted, key rotated, or token expired.
                // Clear everything and notify the app so the authenticated stack unmounts —
                // otherwise React Query retries keep hammering /auth/refresh forever.
                const status = e?.response?.status;
                const isAuthFail = status === 401 || status === 403 || e?.message === 'No refresh token';
                if (isAuthFail) {
                    this.refreshFailedUntil = Date.now() + 60_000;
                    await this.clearTokens().catch(() => undefined);
                    emitAuthLost();
                }
                throw e;
            } finally {
                this.refreshInFlight = null;
            }
        })();
        return this.refreshInFlight;
    }

    async setTokens(accessToken: string, refreshToken: string): Promise<void> {
        // In-memory FIRST so the current session works even if the secure-store
        // write fails — otherwise a keychain hiccup would turn sign-in / "Get
        // started" into a hard error (setTokens throwing → the caller throws).
        // The durable write is then best-effort (storage.ts already retries once);
        // worst case the session is memory-only and re-persists on the next call.
        this.accessToken = accessToken;
        // Fresh tokens — lift any post-failure cooldown so new sessions work immediately.
        this.refreshFailedUntil = 0;
        try {
            await setItemAsync('access_token', accessToken);
            await setItemAsync('refresh_token', refreshToken);
        } catch {
            /* keep the in-memory session; durability is best-effort */
        }
    }

    async clearTokens(): Promise<void> {
        this.accessToken = null;
        // A fresh logged-out state must NOT carry a stale refresh cooldown, or the
        // next session's first 401 would be short-circuited instead of refreshing.
        this.refreshFailedUntil = 0;
        try {
            await deleteItemAsync('access_token');
            await deleteItemAsync('refresh_token');
        } catch {
            /* best-effort */
        }
    }

    // Auth
    async signup(email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) {
        const body: Record<string, string> = {
            email,
            password,
            first_name,
            last_name,
            username,
        };
        if (phone_number && String(phone_number).replace(/\D/g, '').length >= 7) {
            body.phone_number = phone_number;
        }
        const response = await this.client.post('auth/signup', body, {
            timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined,
        });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    async fauxSignup() {
        // Defense-in-depth: dev-only. The calling UI (DevDrawer) is already
        // __DEV__-gated and the backend 404s these in prod, but guard here too so
        // the bypass can never run in a production build even if invoked.
        if (!__DEV__) throw new Error('faux-signup is unavailable in production builds.');
        const response = await this.client.post(
            'auth/faux-signup',
            {},
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    async fauxSkipSignup() {
        if (!__DEV__) throw new Error('faux-signup-skip is unavailable in production builds.');
        const response = await this.client.post(
            'auth/faux-signup-skip',
            {},
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /**
     * DEV ONLY: flip the CURRENT account's is_admin on the server so the app
     * swaps into (or out of) the admin view as the SAME user you're testing
     * with — no separate admin login. Returns the new is_admin value; the caller
     * re-fetches getMe() to update AuthContext and re-render the navigator.
     */
    async devToggleAdmin(): Promise<{ is_admin: boolean }> {
        if (!__DEV__) throw new Error('dev toggle-admin is unavailable in production builds.');
        const response = await this.client.post('auth/dev/toggle-admin', {});
        return response.data;
    }

    /**
     * DEV ONLY: mint a throwaway account with EMPTY onboarding so the
     * client lands on the very first onboarding question. Lets devs
     * replay the full onboarding flow without retyping signup form.
     */
    async fauxFreshSignup() {
        if (!__DEV__) throw new Error('faux-signup-fresh is unavailable in production builds.');
        const response = await this.client.post(
            'auth/faux-signup-fresh',
            {},
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /**
     * Mint a credential-less FREE-tier account ("Get started") so the funnel can
     * run before sign-up. PROD-SAFE (unlike the faux-signup endpoints) — the user
     * later claims it (sets email + password) via claimAccount().
     */
    async anonSignup() {
        const response = await this.client.post(
            'auth/anon',
            {},
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /**
     * Claim the current anonymous account: set its real email + password + name.
     * Server only allows this on an unclaimed account. Returns fresh tokens.
     */
    async claimAccount(email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) {
        const body: Record<string, string> = { email, password, first_name, last_name, username };
        if (phone_number && String(phone_number).replace(/\D/g, '').length >= 7) {
            body.phone_number = phone_number;
        }
        const response = await this.client.post('auth/claim', body, {
            timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined,
        });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /** What the client needs to start Google Sign-In (public). */
    async getGoogleAuthConfig(): Promise<{
        available: boolean;
        web_client_id: string;
        ios_client_id: string;
    }> {
        const response = await this.client.get('auth/google/config', {
            timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined,
        });
        return response.data;
    }

    /** Remote feature-flag overrides (public). Returns {} on any issue so the
     *  client falls back to its built-in defaults. */
    async getFeatureFlags(): Promise<Record<string, boolean>> {
        const response = await this.client.get('config/flags');
        return (response.data && typeof response.data === 'object') ? response.data : {};
    }

    /** True when a JWT is expired (or expires within `bufferS`). Unparseable → treated as expiring, so callers err toward refreshing. */
    private static jwtExpiresSoon(token: string, bufferS = 60): boolean {
        try {
            const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
            const { exp } = JSON.parse(globalThis.atob(payload));
            return typeof exp !== 'number' || exp * 1000 < Date.now() + bufferS * 1000;
        } catch {
            return true;
        }
    }

    /** Sign in / up with a verified Google ID token. */
    async googleSignIn(idToken: string) {
        // Account-after-scan: /auth/google CLAIMS the caller's anon funnel account
        // (keeping its onboarding + scan) only when the Authorization header holds
        // a VALID access token — the server silently ignores an expired one and
        // mints a fresh empty account, losing the results the user is saving.
        // Refresh proactively so the claim can't be lost to token expiry.
        try {
            const access = await this.getToken();
            if (access && ApiService.jwtExpiresSoon(access) && (await getItemAsync('refresh_token'))) {
                await this.refreshToken();
            }
        } catch {
            /* no session or refresh failed — proceed as a plain sign-in */
        }
        const response = await this.client.post(
            'auth/google',
            { id_token: idToken },
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /**
     * Sign in with Apple. `identityToken` comes from AppleAuthentication; the
     * name/email are only present on the FIRST sign-in (Apple provides them
     * once), so we forward whatever we got. Same anon-claim behavior as Google.
     */
    async appleSignIn(identityToken: string, opts?: { givenName?: string; familyName?: string; email?: string }) {
        try {
            const access = await this.getToken();
            if (access && ApiService.jwtExpiresSoon(access) && (await getItemAsync('refresh_token'))) {
                await this.refreshToken();
            }
        } catch {
            /* no session or refresh failed — proceed as a plain sign-in */
        }
        const response = await this.client.post(
            'auth/apple',
            {
                identity_token: identityToken,
                given_name: opts?.givenName,
                family_name: opts?.familyName,
                email: opts?.email,
            },
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /** DEV-ONLY: exercise the Google identity path without a real token. */
    async googleSignInDev(email: string, name?: string) {
        const response = await this.client.post(
            'auth/google/dev',
            { email, name },
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /** `identifier` = email, username, or phone (matches account on file). */
    async login(identifier: string, password: string) {
        const response = await this.client.post(
            'auth/login/json',
            { identifier, password },
            { timeout: Platform.OS === 'web' ? WEB_AUTH_TIMEOUT_MS : undefined },
        );
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    async requestPasswordResetSms(phone_number: string) {
        const response = await this.client.post('auth/forgot-password/sms', { phone_number });
        return response.data as { message: string };
    }

    async confirmPasswordResetSms(phone_number: string, code: string, new_password: string) {
        const response = await this.client.post('auth/forgot-password/sms/confirm', {
            phone_number,
            code,
            new_password,
        });
        return response.data as { message: string };
    }

    async getMe(opts?: { timeout?: number }) {
        // Boot restore passes a generous timeout: a cold Render backend can take
        // >12s (the default) to wake, and without this the boot getMe throws a
        // transient error and — even though tokens are now preserved — leaves the
        // user on Landing until the next launch instead of resuming the session.
        const response = await this.client.get('users/me', opts?.timeout ? { timeout: opts.timeout } : undefined);
        return response.data;
    }

    /** A proactive coaching nudge to open the chat with (or null). */
    async getChatNudge(): Promise<{ id: string; text: string; kind?: string; choices?: string[] } | null> {
        try {
            const response = await this.client.get('chat/nudge');
            return response.data?.nudge ?? null;
        } catch {
            return null; // best-effort — a missing nudge never blocks chat
        }
    }
    /** Mark a proactive nudge shown so it doesn't re-surface. */
    async markChatNudgeSeen(insightId: string): Promise<void> {
        try { await this.client.post(`chat/nudge/${encodeURIComponent(insightId)}/seen`); } catch { /* best-effort */ }
    }

    /** Record that the native App Store review sheet was requested (throttle). */
    async markReviewOpened(): Promise<{ review_request_count: number; last_review_request_date: string } | null> {
        try {
            const response = await this.client.post('users/me/review-opened', {});
            return response.data;
        } catch {
            return null; // best-effort
        }
    }

    async uploadAvatar(imageUri: string) {
        const formData = new FormData();
        if (Platform.OS === 'web') {
            const blob = await fetch(imageUri).then((res) => res.blob());
            formData.append('file', blob, 'avatar.jpg');
        } else {
            // @ts-ignore - React Native FormData accepts { uri, name, type }
            formData.append('file', {
                uri: imageUri,
                name: 'avatar.jpg',
                type: 'image/jpeg',
            });
        }

        const response = await this.client.post('users/me/avatar', formData, {
            transformRequest: [(data: unknown, headers?: Record<string, string>) => {
                if (headers) delete headers['Content-Type'];
                return data;
            }],
        });
        return response.data;
    }

    async uploadProgressPhoto(imageUri: string, opts?: { faceRating?: number | null }) {
        const formData = new FormData();
        if (Platform.OS === 'web') {
            const blob = await fetch(imageUri).then((r) => r.blob());
            formData.append('file', blob, 'progress.jpg');
        } else {
            // @ts-ignore - React Native FormData accepts { uri, name, type }
            formData.append('file', {
                uri: imageUri,
                name: 'progress.jpg',
                type: 'image/jpeg',
            });
        }
        const fr = opts?.faceRating;
        if (fr != null && Number.isFinite(fr)) {
            formData.append('face_rating', String(fr));
        }
        const response = await this.client.post('users/me/progress-photo', formData, {
            transformRequest: [(data: unknown, headers?: Record<string, string>) => {
                if (headers) delete headers['Content-Type'];
                return data;
            }],
        });
        return response.data;
    }

    async uploadProgressPhotoBase64(imageBase64: string) {
        const response = await this.client.post('users/me/progress-photo/base64', {
            image_base64: imageBase64,
        });
        return response.data;
    }

    async getProgressPhotos() {
        const response = await this.client.get('users/me/progress-photos');
        return response.data;
    }

    async deleteProgressPhoto(photoId: string) {
        const response = await this.client.delete(`users/me/progress-photos/${photoId}`);
        return response.data;
    }

    async updateProfile(data: any) {
        const response = await this.client.put('users/profile', data);
        return response.data;
    }

    // --- Onairos personalization ---
    // Runtime config so the SDK key isn't baked into the app bundle.
    async getOnairosConfig() {
        const response = await this.client.get('onairos/config');
        return response.data as { enabled: boolean; api_key: string };
    }

    async connectOnairos(payload: {
        apiUrl: string;
        accessToken: string;
        approvedRequests?: Record<string, any>;
        userData?: { basic?: { name?: string; email?: string } } | null;
    }) {
        const response = await this.client.post('onairos/connect', payload);
        return response.data as { ok: boolean; initial_traits?: any };
    }

    async refreshOnairosTraits() {
        const response = await this.client.post('onairos/refresh-traits');
        return response.data as { ok: boolean; traits?: any };
    }

    async getOnairosStatus() {
        const response = await this.client.get('onairos/status');
        return response.data as {
            connected: boolean;
            connected_at?: string | null;
            token_expires_at?: string | null;
            traits_cached_at?: string | null;
            approved_requests?: Record<string, any>;
            traits?: any;
        };
    }

    async disconnectOnairos() {
        const response = await this.client.delete('onairos/disconnect');
        return response.data as { ok: boolean; removed: boolean };
    }

    // --- Hyper-personalization profile ("What Max knows about you") ---
    async getPersonalizationProfile() {
        const response = await this.client.get('personalization/profile');
        return response.data as PersonalizationProfile;
    }

    async rememberFact(body: { dimension: string; text: string; key?: string | null; value?: any }) {
        const response = await this.client.post('personalization/remember', body);
        return response.data as { ok: boolean; memory: PersonalMemory; brief?: string | null };
    }

    async forgetMemory(memoryId: string) {
        const response = await this.client.delete(`personalization/memory/${memoryId}`);
        return response.data as { ok: boolean; removed: string };
    }

    async refreshPersonalization() {
        const response = await this.client.post('personalization/refresh');
        return response.data as { ok: boolean; profile?: any; brief?: string | null };
    }

    // --- Achievements / badges ---
    async getAchievements() {
        const response = await this.client.get('achievements');
        return response.data as AchievementsResponse;
    }

    async markAchievementsSeen(codes: string[]) {
        const response = await this.client.post('achievements/seen', { codes });
        return response.data as { ok: boolean; updated: number };
    }

    async deleteAccount(password?: string) {
        // Password is omitted for Google/OAuth accounts (they have none); the
        // backend authorizes those via the session JWT.
        const response = await this.client.delete('users/me', { data: { password: password ?? null } });
        return response.data;
    }

    async getBlockedUserIds() {
        const response = await this.client.get('users/me/blocks');
        return response.data as { blocked_user_ids: string[] };
    }

    async blockUser(userId: string) {
        const response = await this.client.post('users/me/blocks', { blocked_user_id: userId });
        return response.data as { blocked_user_ids: string[] };
    }

    async unblockUser(userId: string) {
        const response = await this.client.delete(`users/me/blocks/${userId}`);
        return response.data as { blocked_user_ids: string[] };
    }

    async reportChannelMessage(channelId: string, messageId: string, reason?: string) {
        const response = await this.client.post(`forums/${channelId}/messages/${messageId}/report`, {
            reason: reason || '',
        });
        return response.data as { status: string; message?: string };
    }

    async updateAccount(data: { first_name?: string; last_name?: string; username?: string; phone_number?: string | null }) {
        const response = await this.client.put('users/account', data);
        return response.data;
    }

    // Onboarding
    async saveOnboarding(data: {
        goals: string[];
        experience_level: string;
        gender?: string;
        age?: number;
        height?: number;
        weight?: number;
        height_cm?: number;
        weight_kg?: number;
        activity_level?: string;
        equipment?: string[];
        skin_type?: string;
        unit_system?: string;
        timezone?: string;
        completed?: boolean;
        priority_ranking?: string[];
        // chill | standard | sweatmode — scales daily load + week-1 ramp.
        intensity_preference?: string;
        wake_time?: string;
        sleep_time?: string;
        work_schedule?: 'fixed' | 'flexible' | null;
        work_start?: string | null;
        work_end?: string | null;
        get_ready_time?: string | null;
        get_ready_minutes?: number | null;
        preferred_workout_time?: string | null;
        // Meal anchors — HH:MM, or null when the user skips that meal. Each
        // honored meal becomes a protected window the scheduler keeps clear.
        breakfast_time?: string | null;
        lunch_time?: string | null;
        dinner_time?: string | null;
        meals_skipped?: string[];
        // `days` is the recurrence: 'all' | 'weekdays' | 'weekends' | a list of
        // weekday names. Typed loosely here (string | string[]) since this is the
        // JSON serialization boundary — the canonical shape lives in plannerModel
        // (DayRecurrence) and the backend re-normalises via _norm_days.
        obligations?: Array<{ label: string; start: string; end: string; days?: string | string[] }> | null;
        weekly_timings?: Record<string, any> | null;
    }) {
        // 12s default was timing out on Edit Lifestyle saves when the
        // server cold-starts (Render free tier wakes ~5-8s) or when the
        // post-save schedule regenerator runs synchronously. 30s gives
        // headroom without making a stuck request feel infinite.
        const response = await this.client.post('users/onboarding', data, { timeout: 30_000 });
        return response.data;
    }

    /**
     * Planner chatbot — send a natural-language change ("sleep in on weekends",
     * "add gym 6-7pm on Mon Wed Fri") and the server translates it into the
     * structured weekly plan, persists it (regenerating live schedules), and
     * returns the new default + per-weekday timings to re-hydrate the editor.
     */
    async plannerChat(instruction: string) {
        const response = await this.client.post(
            'users/planner/chat',
            { instruction },
            { timeout: 45_000 },
        );
        return response.data as {
            message: string;
            summary: string;
            defaults?: Record<string, any> | null;
            weekly_timings?: Record<string, any> | null;
            changed: boolean;
        };
    }

    async saveOnboardingAnonymous(data: {
        goals: string[];
        experience_level: string;
        gender?: string;
        age?: number;
        height?: number;
        weight?: number;
        activity_level?: string;
        equipment?: string[];
        skin_type?: string;
        unit_system?: string;
        timezone?: string;
        completed?: boolean;
    }) {
        const response = await this.client.post('users/onboarding/anonymous', data, {
            // explicitly avoid auth retry loops if token is missing
            headers: { 'Content-Type': 'application/json' },
        });
        return response.data;
    }

    /** Base URL without trailing slash, for fetch() (avoids RN axios + multipart 422). */
    private scansTripleUploadUrl() {
        return `${API_BASE_URL.replace(/\/?$/, '')}/scans/upload-triple`;
    }

    /**
     * Three-photo scan — uses fetch() so React Native sets multipart boundary correctly.
     * Axios + default JSON Content-Type often yields FastAPI 422 even with interceptors.
     */
    async uploadScanTriple(frontUri: string, leftUri: string, rightUri: string) {
        const url = this.scansTripleUploadUrl();
        const buildForm = async (): Promise<FormData> => {
            const formData = new FormData();
            if (Platform.OS === 'web') {
                const fd = new FormData();
                fd.append('front', await fetch(frontUri).then((r) => r.blob()), 'front.jpg');
                fd.append('left', await fetch(leftUri).then((r) => r.blob()), 'left.jpg');
                fd.append('right', await fetch(rightUri).then((r) => r.blob()), 'right.jpg');
                return fd;
            }
            // @ts-ignore RN file shape
            formData.append('front', { uri: frontUri, type: 'image/jpeg', name: 'front.jpg' });
            // @ts-ignore
            formData.append('left', { uri: leftUri, type: 'image/jpeg', name: 'left.jpg' });
            // @ts-ignore
            formData.append('right', { uri: rightUri, type: 'image/jpeg', name: 'right.jpg' });
            return formData;
        };

        // Per-attempt hard timeout. This request runs the FULL vision analysis
        // server-side (~75s ceiling), so give it headroom — but never infinity:
        // a stalled cellular connection used to hang this fetch forever, which
        // left the user trapped on the full-screen AnalyzingScreen.
        const ATTEMPT_TIMEOUT_MS = 110_000;
        const doFetch = async (formData: FormData) => {
            const token = await this.getToken();
            const headers: Record<string, string> = {};
            if (token) headers.Authorization = `Bearer ${token}`;
            const ctrl = new AbortController();
            const timer = setTimeout(() => ctrl.abort(), ATTEMPT_TIMEOUT_MS);
            try {
                return await fetch(url, {
                    method: 'POST', headers, body: formData, signal: ctrl.signal,
                });
            } finally {
                clearTimeout(timer);
            }
        };

        const RETRY_DELAYS = [1000, 2000];
        let lastError: unknown;
        for (let attempt = 0; attempt <= RETRY_DELAYS.length; attempt++) {
            if (attempt > 0) {
                await new Promise((r) => setTimeout(r, RETRY_DELAYS[attempt - 1]));
            }
            try {
                let form = await buildForm();
                let res = await doFetch(form);
                if (res.status === 401) {
                    await this.refreshToken();
                    form = await buildForm();
                    res = await doFetch(form);
                }
                if (!res.ok) {
                    if (res.status >= 500 && attempt < RETRY_DELAYS.length) {
                        lastError = new Error(`Upload failed (${res.status})`);
                        continue;
                    }
                    const text = await res.text();
                    let msg = text;
                    try {
                        const j = JSON.parse(text);
                        msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j);
                    } catch { /* keep text */ }
                    const err = new Error(msg);
                    (err as any).statusCode = res.status;
                    throw err;
                }
                return res.json() as Promise<unknown>;
            } catch (e: any) {
                lastError = e;
                const code = e?.statusCode;
                if (code && code >= 400 && code < 500) throw e;
                if (attempt < RETRY_DELAYS.length) continue;
            }
        }
        throw lastError;
    }

    async uploadScanTripleBlobs(front: Blob, left: Blob, right: Blob) {
        const url = this.scansTripleUploadUrl();
        const buildForm = () => {
            const fd = new FormData();
            fd.append('front', front, 'front.jpg');
            fd.append('left', left, 'left.jpg');
            fd.append('right', right, 'right.jpg');
            return fd;
        };
        const doFetch = async (formData: FormData) => {
            const token = await this.getToken();
            const headers: Record<string, string> = {};
            if (token) headers.Authorization = `Bearer ${token}`;
            return fetch(url, { method: 'POST', headers, body: formData });
        };
        let form = buildForm();
        let res = await doFetch(form);
        if (res.status === 401) {
            await this.refreshToken();
            form = buildForm();
            res = await doFetch(form);
        }
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`Upload failed (${res.status}): ${text}`);
        }
        return res.json() as Promise<unknown>;
    }

    async uploadScanVideo(videoUri: string) {
        const formData = new FormData();
        // @ts-ignore
        formData.append('video', {
            uri: videoUri,
            type: 'video/mp4',
            name: 'scan.mp4',
        });

        // Large multipart upload — allow 60s for slow cellular connections.
        const response = await this.client.post('scans/upload-video', formData, { timeout: 60_000 });
        return response.data;
    }

    async uploadScanVideoBlob(blob: Blob) {
        const formData = new FormData();
        formData.append('video', blob, 'scan.webm');
        const response = await this.client.post('scans/upload-video', formData, { timeout: 60_000 });
        return response.data;
    }

    async analyzeScan(scanId: string) {
        // Kicks off async analysis — the POST itself should return quickly,
        // but allow 30s for backend to enqueue.
        const response = await this.client.post(`scans/${scanId}/analyze`, undefined, { timeout: 30_000 });
        return response.data;
    }

    async getLatestScan() {
        // Treat 404/204/null as "no scan yet" (a normal state for fresh users)
        // so screens can render an empty/CTA state instead of getting wedged
        // on a perpetual loading spinner.
        try {
            const response = await this.client.get('scans/latest');
            if (response.status === 204 || response.data === '' || response.data === null) {
                return null;
            }
            return response.data;
        } catch (e: any) {
            if (e?.response?.status === 404) return null;
            throw e;
        }
    }

    async dismissPostSubscriptionOnboarding() {
        const response = await this.client.post('users/post-subscription-onboarding/dismiss');
        return response.data;
    }

    async completeMainAppTour() {
        const response = await this.client.post('users/main-app-tour/complete');
        return response.data;
    }

    /** Clear the one-time Chad-Lite→Chad grandfather-upgrade popup flag. */
    async ackChadUpgrade() {
        const response = await this.client.post('users/ack-chad-upgrade');
        return response.data;
    }

    /**
     * DEBUG: bulk-reset user flags so a single account can replay
     * onboarding / scan / paywall flows. Backend 404s when DEBUG=false.
     */
    async devReset(scope: { onboarding?: boolean; scan?: boolean; subscription?: boolean; all?: boolean }) {
        const response = await this.client.post('users/dev/reset', scope);
        return response.data as {
            message: string;
            reset: { onboarding: boolean; scan: boolean; subscription: boolean };
            state: {
                is_paid: boolean;
                subscription_tier: string | null;
                first_scan_completed: boolean;
                onboarding_completed: boolean;
            };
        };
    }

    /** DEBUG: mark scan completed without an actual face scan upload. */
    async devMarkScanCompleted() {
        const response = await this.client.post('users/dev/mark-scan-completed');
        return response.data;
    }

    /** Curated catalog products tailored to this user's onboarding signals. */
    async getMyProducts(): Promise<{
        products: {
            id: string;
            name: string;
            brand: string;
            module: string;
            url: string;
            price_tier: 'budget' | 'mid' | 'premium' | string;
            rationale: string;
            tags: Record<string, boolean | null>;
        }[];
    }> {
        const response = await this.client.get('users/me/products');
        return response.data;
    }

    async registerPushToken(token: string) {
        const response = await this.client.post('users/push-token', { token });
        return response.data;
    }

    async sendTestPush() {
        const response = await this.client.post('users/test-push');
        return response.data;
    }

    async clearPushToken() {
        const response = await this.client.delete('users/push-token');
        return response.data;
    }

    async patchCoachingTone(tone: 'default' | 'hardcore' | 'gentle' | 'influencer') {
        const response = await this.client.patch('users/coaching-tone', { tone });
        return response.data as { message: string; tone: string };
    }

    async patchResponseLength(length: 'concise' | 'medium' | 'detailed') {
        const response = await this.client.patch('users/response-length', { length });
        return response.data as { message: string; length: string };
    }

    async getScanHistory() {
        const response = await this.client.get('scans/history');
        return response.data;
    }

    async getScanById(scanId: string) {
        const response = await this.client.get(`scans/${scanId}`);
        return response.data;
    }

    // Payments — native SetupIntent + Subscription flow

    async getBillingPreview(tier: 'basic' | 'premium'): Promise<{
        customer_id: string;
        ephemeral_key_secret: string;
        setup_intent_client_secret: string;
        setup_intent_id: string;
        publishable_key: string;
    }> {
        const response = await this.client.post('payments/billing-preview', { tier });
        return response.data;
    }

    async subscribe(tier: 'basic' | 'premium', setupIntentId: string): Promise<{
        subscription_id: string;
        status: string;
    }> {
        const response = await this.client.post('payments/subscribe', {
            tier,
            setup_intent_id: setupIntentId,
        });
        return response.data;
    }

    /** iOS StoreKit: verify transaction with backend (`POST /api/payments/apple/verify`). */
    async verifyAppleIapTransaction(transactionId: string, productId?: string): Promise<{ status: string; tier?: string }> {
        const response = await this.client.post('payments/apple/verify', {
            transaction_id: transactionId,
            product_id: productId,
        });
        return response.data;
    }

    async cancelSubscription(immediate = false): Promise<{ canceled: boolean }> {
        const response = await this.client.post('payments/cancel', { immediate });
        return response.data;
    }

    // Legacy
    async createCheckoutSession(successUrl: string, cancelUrl: string) {
        const response = await this.client.post('payments/create-session', { success_url: successUrl, cancel_url: cancelUrl });
        return response.data;
    }

    async getSubscriptionStatus(): Promise<{
        is_active: boolean;
        subscription_tier?: string | null;
        cancel_at_period_end?: boolean;
        current_period_end_iso?: string | null;
        current_period_start_iso?: string | null;
        /** False for dev test-activate and similar (no Stripe subscription id on file). */
        has_stripe_subscription?: boolean;
        /** True when Stripe metadata could not be loaded; avoid destructive billing actions. */
        degraded?: boolean;
        subscription?: {
            id?: string;
            status?: string;
            current_period_start?: string | null;
            current_period_end?: string | null;
            cancel_at_period_end?: boolean;
        } | null;
    }> {
        const response = await this.client.get('payments/status');
        return response.data;
    }

    async changeSubscriptionTier(tier: 'basic' | 'premium'): Promise<{ status: string; subscription_tier: string }> {
        const response = await this.client.post('payments/change-tier', { tier });
        return response.data;
    }

    async resumeSubscription(): Promise<{ resumed: boolean }> {
        const response = await this.client.post('payments/resume');
        return response.data;
    }

    async testActivateSubscription(tier: 'basic' | 'premium' = 'premium') {
        // Defense-in-depth: this mints a paid subscription with no payment. The
        // calling UI (PaymentScreen devBypass) is __DEV__-gated and the backend
        // 404s this in prod, but guard here too so it can never run in a prod build.
        if (!__DEV__) throw new Error('test-activate is unavailable in production builds.');
        const response = await this.client.post('payments/test-activate', { tier });
        return response.data;
    }

    // Maxes
    async getMaxxes() {
        const response = await this.client.get('maxes');
        return response.data;
    }

    async getMaxx(maxxId: string) {
        const response = await this.client.get(`maxes/${maxxId}`);
        return response.data;
    }

    // Marketplace
    async getMarketplace(): Promise<{ maxxes: MarketplaceItem[]; courses: MarketplaceItem[] }> {
        const response = await this.client.get('marketplace');
        return response.data;
    }

    // --- Referral / promo codes (RALPH_REFERRAL) -------------------------------
    /** Pure check, no side effects — used to show "code applied" before redeem. */
    async validateReferral(code: string): Promise<ReferralValidateResult> {
        const response = await this.client.post('referral/validate', { code });
        return response.data;
    }

    /** Server-authoritative redeem. Free comps grant entitlement (caller should
     *  refreshUser() and route past the paywall); discounts return platform targets. */
    async redeemReferral(code: string, platform: 'ios' | 'web'): Promise<ReferralRedeemResult> {
        const response = await this.client.post('referral/redeem', { code, platform });
        return response.data;
    }

    async getMarketplaceItem(itemId: string): Promise<MarketplaceItem> {
        const response = await this.client.get(`marketplace/item/${itemId}`);
        return response.data;
    }

    // --- Creator applications (own-your-own-max) -------------------------------
    /** Submit a creator application. Throws on 409 when the max is already claimed. */
    async submitCreatorApplication(body: {
        applicant_name: string;
        max_name: string;
        max_description: string;
        max_differentiator: string;
        brand_fit: string;
        course_docs?: { filename: string; url: string; source?: string }[];
    }): Promise<{ id: string; status: string; max_name: string; instagram_url: string | null; tiktok_url: string | null }> {
        const response = await this.client.post('creator-applications', body);
        return response.data;
    }

    /** Live public-profile lookup for the apply flow — follower count, avatar, etc. */
    async lookupSocialProfile(platform: 'instagram' | 'tiktok', handle: string): Promise<SocialProfile> {
        const response = await this.client.post('creator-applications/social-lookup', { platform, handle });
        return response.data;
    }

    /** Is a max niche still open? (first-come-first-served gate, pre-submit). */
    async checkMaxAvailability(maxName: string): Promise<{ available: boolean; max_name: string }> {
        const response = await this.client.get('creator-applications/availability', { params: { max_name: maxName } });
        return response.data;
    }

    /** The caller's latest creator application (or null) — used to show "applied" state. */
    async getMyCreatorApplication(): Promise<{ application: null | {
        id: string; status: string; applicant_name: string; max_name: string;
        max_description: string; instagram_url: string | null; tiktok_url: string | null; created_at: string | null;
    } }> {
        const response = await this.client.get('creator-applications/mine');
        return response.data;
    }

    /** OAuth status for Instagram/TikTok sign-in during creator application. */
    async getCreatorSocialStatus(): Promise<CreatorSocialStatus> {
        const response = await this.client.get('creator-social/status');
        return response.data;
    }

    /** Start OAuth — returns the consent URL to open in the system browser. */
    async getCreatorSocialConnectUrl(
        platform: 'instagram' | 'tiktok',
        returnUrl?: string,
    ): Promise<{ auth_url: string }> {
        const response = await this.client.get(`creator-social/connect/${platform}`, {
            params: returnUrl ? { return_url: returnUrl } : undefined,
        });
        return response.data;
    }

    /** Disconnect an OAuth-verified social account. */
    async disconnectCreatorSocial(platform: 'instagram' | 'tiktok'): Promise<{ disconnected: boolean }> {
        const response = await this.client.delete(`creator-social/disconnect/${platform}`);
        return response.data;
    }

    /** Multipart POST via fetch — axios breaks file uploads on web (422). */
    private async postMultipartJson<T>(
        path: string,
        buildForm: () => FormData | Promise<FormData>,
    ): Promise<T> {
        const url = `${API_BASE_URL.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
        const doFetch = async (formData: FormData) => {
            const token = await this.getToken();
            const headers: Record<string, string> = {};
            if (token) headers.Authorization = `Bearer ${token}`;
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 60_000);
            try {
                return await fetch(url, { method: 'POST', headers, body: formData, signal: controller.signal });
            } finally {
                clearTimeout(timer);
            }
        };
        let form = await buildForm();
        let res = await doFetch(form);
        if (res.status === 401) {
            await this.refreshToken();
            form = await buildForm();
            res = await doFetch(form);
        }
        if (!res.ok) {
            const text = await res.text();
            let msg = text;
            try {
                const j = JSON.parse(text);
                msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j);
            } catch { /* keep text */ }
            const err = new Error(msg);
            (err as any).statusCode = res.status;
            throw err;
        }
        return res.json() as Promise<T>;
    }

    async uploadCreatorDoc(
        file: File | Blob | { uri: string; name: string; type?: string },
    ): Promise<{ filename: string; url: string; source: string }> {
        return this.postMultipartJson('creator-applications/upload-doc', () => {
            const fd = new FormData();
            if (Platform.OS === 'web' && (file instanceof Blob || (typeof File !== 'undefined' && file instanceof File))) {
                fd.append('file', file as Blob, (file as File).name || 'document');
            } else if (typeof file === 'object' && file != null && 'uri' in file) {
                // @ts-ignore - React Native FormData accepts { uri, name, type }
                fd.append('file', file);
            } else {
                fd.append('file', file as any);
            }
            return fd;
        });
    }

    async linkCreatorDoc(url: string, filename?: string): Promise<{ filename: string; url: string; source: string }> {
        const response = await this.client.post('creator-applications/link-doc', { url, filename });
        return response.data;
    }

    async getInboxMessages(): Promise<{ messages: InboxMessage[] }> {
        const response = await this.client.get('user-inbox');
        return response.data;
    }

    async getInboxUnreadCount(): Promise<{ unread: number }> {
        const response = await this.client.get('user-inbox/unread-count');
        return response.data;
    }

    async markInboxRead(messageId: string): Promise<{ read: boolean }> {
        const response = await this.client.post(`user-inbox/${messageId}/read`);
        return response.data;
    }

    async markAllInboxRead(): Promise<{ read: boolean }> {
        const response = await this.client.post('user-inbox/read-all');
        return response.data;
    }

    // ── Creator studio onboarding ───────────────────────────────────────────
    async getCreatorOnboarding(): Promise<CreatorOnboardingState> {
        const response = await this.client.get('creators/me/onboarding');
        return response.data;
    }

    async setCreatorOnboardingStep(step: number): Promise<CreatorOnboardingState> {
        const response = await this.client.patch('creators/me/onboarding/step', { step });
        return response.data;
    }

    async analyzeCreatorKnowledge(): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/analyze');
        return response.data;
    }

    async uploadCreatorOnboardingDoc(
        file: File | Blob | { uri: string; name: string; type?: string },
    ): Promise<{ filename: string; url: string; source: string }> {
        return this.postMultipartJson('creators/me/onboarding/upload-doc', () => {
            const fd = new FormData();
            if (Platform.OS === 'web' && (file instanceof Blob || (typeof File !== 'undefined' && file instanceof File))) {
                fd.append('file', file as Blob, (file as File).name || 'document');
            } else if (typeof file === 'object' && file != null && 'uri' in file) {
                // @ts-ignore
                fd.append('file', file);
            } else {
                fd.append('file', file as any);
            }
            return fd;
        });
    }

    async linkCreatorOnboardingDoc(url: string, filename?: string) {
        const response = await this.client.post('creators/me/onboarding/link-doc', { url, filename });
        return response.data;
    }

    async submitCreatorVoiceAnswer(sampleId: string, answer: string): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/voice/answer', {
            sample_id: sampleId, answer,
        });
        return response.data;
    }

    async submitCreatorVoiceFeedback(sampleId: string, approved: boolean, correction?: string): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/voice/feedback', {
            sample_id: sampleId, approved, correction,
        });
        return response.data;
    }

    async updateCreatorHabitLibrary(habits: CreatorHabitTemplate[]): Promise<CreatorOnboardingState> {
        const response = await this.client.put('creators/me/onboarding/habits', { habits });
        return response.data;
    }

    async setCreatorOnboardingPricing(tier: string): Promise<CreatorOnboardingState> {
        const response = await this.client.patch('creators/me/onboarding/pricing', { tier });
        return response.data;
    }

    async setCreatorOnboardingMedia(introVideoUrl?: string, welcomeMessage?: string): Promise<CreatorOnboardingState> {
        const response = await this.client.patch('creators/me/onboarding/media', {
            intro_video_url: introVideoUrl,
            welcome_message: welcomeMessage,
        });
        return response.data;
    }

    async creatorOnboardingTestChat(message: string): Promise<CreatorOnboardingState & { reply: string }> {
        const response = await this.client.post('creators/me/onboarding/test-chat', { message });
        return response.data;
    }

    async deleteCreatorOnboardingDoc(url: string): Promise<CreatorOnboardingState> {
        const response = await this.client.delete('creators/me/onboarding/docs', { data: { url } });
        return response.data;
    }

    async submitTestDriveAnswer(stepId: string, answer: string): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/test-drive/answer', {
            step_id: stepId,
            answer,
        });
        return response.data;
    }

    async resetCreatorOnboardingTest(): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/test-reset');
        return response.data;
    }

    async syncCreatorOnboardingHabits(): Promise<{ synced: number }> {
        const response = await this.client.post('creators/me/onboarding/sync-habits');
        return response.data;
    }

    async launchCreatorMax(): Promise<CreatorOnboardingState> {
        const response = await this.client.post('creators/me/onboarding/launch');
        return response.data;
    }

    async enterMarketplaceItem(itemId: string): Promise<{
        entered: boolean;
        item_id: string;
        kind?: string;
        checkout_url?: string;
        /** Creator maxx with a paid sub: 'creator_subscription' → open CreatorPaywall. */
        requires?: string;
        apple_product_id?: string;
        price_cents?: number;
        price_label?: string;
    }> {
        const response = await this.client.post(`marketplace/enter/${itemId}`);
        return response.data;
    }

    async cancelMarketplaceItem(
        itemId: string,
        pause = false,
    ): Promise<{ status: string; access_until?: string | null; until?: string }> {
        const response = await this.client.post(`marketplace/cancel/${itemId}`, { pause });
        return response.data;
    }

    // Planner (Today Loop)
    async getPlannerToday(day?: string): Promise<{
        date: string;
        tasks: any[];
        structure: { time: string; label: string; end?: string; source?: string; event_id?: string }[];
        today_read: { level: 'green' | 'yellow' | 'red'; icon: string; color: string; line: string };
        held_back_count: number;
        locked_in: boolean;
        calendar_event_count: number;
        slipped: { task_id?: string; title?: string; from_time?: string; suggested_time?: string | null }[];
        welcome_back: { gap_days: number; line: string; sub: string } | null;
        insights: { id: string; text: string; kind: string }[];
        leave_by: { task_id?: string; time: string; estimated: boolean; line: string } | null;
        streak_armed_freeze: boolean;
        freeze_used_yesterday?: boolean;
    }> {
        const response = await this.client.get('planner/today', { params: day ? { day } : {} });
        return response.data;
    }

    async skipPlannerTask(scheduleId: string, taskId: string): Promise<{ skipped: boolean }> {
        const response = await this.client.post('planner/task/skip', {
            schedule_id: scheduleId,
            task_id: taskId,
        });
        return response.data;
    }

    async getLifeModel(): Promise<any> {
        const response = await this.client.get('planner/life-model');
        return response.data;
    }

    // Google integrations
    async getGoogleStatus(): Promise<{
        oauth_available: boolean;
        maps_available: boolean;
        gmail_available: boolean;
        calendar_link_enabled: boolean;
        connected: boolean;
        last_synced_at: string | null;
        synced_through: string | null;
        needs_resync: boolean;
    }> {
        const response = await this.client.get('google/status');
        return response.data;
    }

    async disconnectGoogle(): Promise<{ disconnected: boolean }> {
        const response = await this.client.delete('google/disconnect');
        return response.data;
    }

    async resyncGoogleCalendar(): Promise<{ synced: number }> {
        const response = await this.client.post('google/sync');
        return response.data;
    }

    async getGoogleAuthUrl(includeGmail = false, returnUrl?: string): Promise<{ auth_url: string }> {
        const response = await this.client.get('google/connect', {
            params: { include_gmail: includeGmail, ...(returnUrl ? { return_url: returnUrl } : {}) },
        });
        return response.data;
    }

    async googleSyncNow(): Promise<{ synced: number }> {
        const response = await this.client.post('google/sync');
        return response.data;
    }

    async googleGmailScan(): Promise<{ proposed: number }> {
        const response = await this.client.post('google/gmail/scan');
        return response.data;
    }

    async getGoogleProposed(): Promise<{
        proposed: { id: string; title: string; starts_at: string; ends_at: string }[];
    }> {
        const response = await this.client.get('google/proposed');
        return response.data;
    }

    async resolveGoogleProposed(eventId: string, confirm: boolean): Promise<{ status: string }> {
        const response = await this.client.post(`google/proposed/${eventId}`, { confirm });
        return response.data;
    }

    async removeCalendarEvent(eventId: string): Promise<{ removed: boolean }> {
        const response = await this.client.delete(`planner/calendar-events/${eventId}`);
        return response.data;
    }

    async getPlaces(): Promise<{ places: { id: string; name: string; kind: string; radius_m: number; source: string; lat?: number | null; lng?: number | null; resolved?: boolean }[] }> {
        const response = await this.client.get('planner/places');
        return response.data;
    }

    async addPlace(name: string, kind: string): Promise<{ id: string; name: string; kind: string }> {
        const response = await this.client.post('planner/places', { name, kind });
        return response.data;
    }

    async removePlace(placeId: string): Promise<{ removed: boolean }> {
        const response = await this.client.delete(`planner/places/${placeId}`);
        return response.data;
    }

    async pushPlannerSignals(payload: {
        calendar?: { provider: string; events: { starts_at: string; ends_at: string; title?: string }[]; window_from?: string; window_to?: string };
        geofence_events?: any[];
        derived_prefs?: Record<string, string>;
    }): Promise<{ stored: Record<string, number> }> {
        const response = await this.client.post('planner/signals', payload);
        return response.data;
    }

    async getPlannerHeldBack(day?: string): Promise<{
        date: string;
        items: { title: string; program_id: string; reason: string; returns_on?: string | null }[];
    }> {
        const response = await this.client.get('planner/held-back', { params: day ? { day } : {} });
        return response.data;
    }

    async plannerLockIn(date?: string): Promise<{ locked_in: boolean; date: string }> {
        const response = await this.client.post('planner/lock-in', date ? { date } : {});
        return response.data;
    }

    async getWeeklyReview(): Promise<{
        days: { date: string; weekday: string; closed: boolean; done: number; total: number }[];
        closed_count: number;
        active_days: number;
        strongest_window: 'morning' | 'midday' | 'evening' | null;
        facts: { id: string; text: string; value?: string }[];
    }> {
        const response = await this.client.get('planner/reviews/weekly');
        return response.data;
    }

    async trackEvents(
        events: { event: string; props?: Record<string, unknown> }[],
    ): Promise<{ stored: number; dropped: number }> {
        const response = await this.client.post('analytics/track', { events });
        return response.data;
    }

    async getPlannerFeasibility(programId: string): Promise<{
        verdict: 'green' | 'amber' | 'red';
        fits_n_of_m: { fits: number; of: number };
        minutes_per_session: number;
        ghost_week: { day: string; slots: string[] }[];
    }> {
        const response = await this.client.post('planner/feasibility', { program_id: programId });
        return response.data;
    }

    async confirmWeeklyFacts(
        confirmations: { id: string; accepted: boolean; value?: string }[],
    ): Promise<{ stored: number }> {
        const response = await this.client.post('planner/reviews/weekly', { confirmations });
        return response.data;
    }

    // Events
    async getEvents() {
        const response = await this.client.get('events');
        return response.data;
    }

    async getLiveEvents() {
        const response = await this.client.get('events/live');
        return response.data;
    }

    async getCalendar(month?: number, year?: number) {
        const response = await this.client.get('events/calendar', { params: { month, year } });
        return response.data;
    }

    // Chat
    async sendChatMessage(
        message: string,
        attachmentUrl?: string,
        attachmentType?: string,
        initContext?: string,
        chatIntent?: string,
        conversationId?: string | null,
        replyToMessageId?: string | null,
        signal?: AbortSignal,
    ): Promise<{
        response: string;
        choices?: string[];
        /** When true the chip row renders multi-select with a Submit button. */
        multi_choice?: boolean;
        // Optional structured input widget. The backend returns either a
        // numeric `slider` (→ ChatSliderInput) or a per-max `habit_picker`
        // shown right after a schedule is built (→ ChatHabitPicker). Typed
        // loosely (the widgets validate their own `type` before rendering).
        //   slider:       { type, min, max, step, default, label, unit }
        //   habit_picker: { type, maxx_id, schedule_id, label }
        input_widget?: ({ type: string } & Record<string, any>) | null;
        // Structured product recommendations rendered as preview cards under
        // the reply. Populated from the catalog (authoritative name/brand/url).
        products?: Array<{ name: string; brand?: string; url: string; description?: string; image?: string }>;
        conversation_id?: string | null;
        // When the coach proposed a schedule change this turn, the client renders
        // Yes/No buttons; Yes → confirmScheduleChange(proposal_id). (RALPH_CHAT_RESCHEDULE)
        confirm?: { proposal_id: string; summary: string } | null;
        // Structured visuals (tables/comparisons/timelines/flowcharts/stat-cards/
        // checklists) extracted from the answer; rendered as native components.
        visual_blocks?: VisualBlock[];
        // Per-method confidence, surfaced behind a small "i" button.
        method_metadata?: { methods: MethodConfidence[] } | null;
    }> {
        const body: any = {
            message,
            attachment_url: attachmentUrl,
            attachment_type: attachmentType,
        };
        if (initContext) body.init_context = initContext;
        if (chatIntent) body.chat_intent = chatIntent;
        if (conversationId) body.conversation_id = conversationId;
        if (replyToMessageId) body.reply_to_message_id = replyToMessageId;
        // LangChain agent may chain multiple tool calls + LLM fallback,
        // so allow up to 120s before timing out.
        const response = await this.client.post('chat/message', body, {
            timeout: 120_000,
            signal,
            // @ts-expect-error custom flag consumed by response interceptor
            _skipNetRetry: true,
        });
        return response.data;
    }

    /**
     * Apply (Yes) or reject (No) a chat-proposed schedule change. Yes replays the
     * EXACT stored proposal server-side (deterministic, idempotent) so the schedule
     * + Planner update immediately. (RALPH_CHAT_RESCHEDULE)
     */
    async confirmScheduleChange(
        proposalId: string,
        decision: 'yes' | 'no',
        signal?: AbortSignal,
    ): Promise<{ ok: boolean; applied: boolean; message: string }> {
        const response = await this.client.post(
            'chat/confirm-change',
            { proposal_id: proposalId, decision },
            { timeout: 60_000, signal },
        );
        return response.data;
    }

    /** Voice dictation: upload a recorded clip, get back the transcript text. */
    async transcribeAudio(uri: string): Promise<string> {
        const name = uri.split('/').pop() || 'audio.m4a';
        const ext = (name.split('.').pop() || 'm4a').toLowerCase();
        const form = new FormData();
        form.append('file', { uri, name, type: `audio/${ext === 'caf' ? 'x-caf' : ext}` } as any);
        const response = await this.client.post('chat/transcribe', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 60_000,
        });
        return (response.data?.text as string) || '';
    }

    /**
     * Apply the chat habit-picker's want/avoid choices to one max's schedule.
     * Writes them into schedule_context and re-expands just that max, so the
     * picks take effect immediately. Used by the in-chat ChatHabitPicker.
     */
    async updateHabitPrefs(
        scheduleId: string,
        wantedCatalogIds: string[],
        avoidedCatalogIds: string[],
    ): Promise<{
        status: string;
        schedule: { id: string; maxx_id: string; days: any[] } | null;
        wanted: string[];
        avoided: string[];
    }> {
        const response = await this.client.post(
            `schedules/${scheduleId}/habit-prefs`,
            { wanted_catalog_ids: wantedCatalogIds, avoided_catalog_ids: avoidedCatalogIds },
            { timeout: 60_000 },
        );
        return response.data;
    }

    /** Offered habit set for the tune-later sheet: the distinct catalog tasks
     *  actually on this schedule (id/label/area) + current wanted/avoided, so the
     *  picker is driven by the real plan and prefills accurately. */
    async getHabitOptions(scheduleId: string): Promise<{
        schedule_id: string;
        maxx_id: string;
        offered: { id: string; label: string; area: string }[];
        wanted: string[];
        avoided: string[];
    }> {
        const response = await this.client.get(`schedules/${scheduleId}/habit-options`);
        return response.data;
    }

    async getChatHistory(opts?: {
        limit?: number;
        offset?: number;
        conversationId?: string | null;
    }) {
        const params: Record<string, string | number> = {};
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        if (opts?.conversationId) params.conversation_id = opts.conversationId;
        const response = await this.client.get('chat/history', { params });
        return response.data as {
            conversation_id: string | null;
            messages: Array<{
                id: string;
                role: 'user' | 'assistant';
                content: string;
                created_at: string;
                reply_to?: { id: string; role: 'user' | 'assistant'; preview: string } | null;
            }>;
            pending_question?: {
                max: string;
                field_id: string;
                text: string;
                choices: string[];
                multi_choice?: boolean;
                input_widget?: {
                    type: 'slider';
                    min: number;
                    max: number;
                    step: number;
                    default: number;
                    label: string;
                    unit?: string;
                } | null;
            } | null;
        };
    }

    // --- Multi-chat conversations ---
    async listChatConversations(opts?: { includeArchived?: boolean; limit?: number }) {
        const params: Record<string, string | number> = {};
        if (opts?.includeArchived) params.include_archived = 'true';
        if (opts?.limit != null) params.limit = opts.limit;
        const response = await this.client.get('chat/conversations', { params });
        return response.data as {
            conversations: Array<{
                id: string;
                title: string;
                channel: string;
                is_archived: boolean;
                last_message_at: string | null;
                created_at: string | null;
                updated_at: string | null;
            }>;
        };
    }

    async createChatConversation(title?: string) {
        const response = await this.client.post('chat/conversations', { title: title ?? null });
        return response.data as {
            conversation: {
                id: string;
                title: string;
                channel: string;
                is_archived: boolean;
                last_message_at: string | null;
                created_at: string | null;
                updated_at: string | null;
            };
        };
    }

    async renameChatConversation(conversationId: string, title: string) {
        const response = await this.client.patch(
            `chat/conversations/${conversationId}`,
            { title },
        );
        return response.data as {
            conversation: { id: string; title: string };
        };
    }

    async deleteChatConversation(conversationId: string) {
        const response = await this.client.delete(`chat/conversations/${conversationId}`);
        return response.data as { ok: boolean };
    }

    // Channels (Discord-like chat)
    async getChannels(search?: string, opts?: { limit?: number; offset?: number }) {
        const params: Record<string, string | number> = {};
        if (search) params.q = search;
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        const response = await this.client.get('forums', { params });
        return response.data;
    }

    async createForum(data: { name: string; description: string; category?: string; tags?: string[]; is_admin_only?: boolean }) {
        const response = await this.client.post('forums', data);
        return response.data;
    }

    async getChannelMessages(channelId: string, limit: number = 50, query?: string, before?: string) {
        const response = await this.client.get(`forums/${channelId}/messages`, { params: { limit, query, before } });
        return response.data;
    }

    async uploadChatFile(formData: FormData) {
        const response = await this.client.post('forums/upload', formData, {
            transformRequest: [(data: unknown, headers?: Record<string, string>) => {
                if (headers) delete headers['Content-Type'];
                return data;
            }],
        });
        return response.data;
    }

    async sendChannelMessage(channelId: string, content: string, parentId?: string, attachmentUrl?: string, attachmentType?: string) {
        const response = await this.client.post(`forums/${channelId}/messages`, {
            content,
            parent_id: parentId,
            attachment_url: attachmentUrl,
            attachment_type: attachmentType
        });
        return response.data;
    }

    async toggleReaction(channelId: string, messageId: string, emoji: string) {
        const response = await this.client.post(`forums/${channelId}/messages/${messageId}/reactions`, null, {
            params: { emoji }
        });
        return response.data;
    }

    // Legacy alias for getChannels
    async getForums() {
        return this.getChannels();
    }

    // Forums v2 (classic threads)
    async getForumV2Categories(): Promise<{ categories: any[] }> {
        const response = await this.client.get('forums/v2/categories');
        return response.data;
    }

    async getForumV2Subforums(categoryId?: string): Promise<{ subforums: any[] }> {
        const params: any = {};
        if (categoryId) params.category_id = categoryId;
        const response = await this.client.get('forums/v2/subforums', { params });
        return response.data;
    }

    async searchForumV2Threads(opts: { q: string; limit?: number; offset?: number }): Promise<any> {
        const params: any = { q: opts.q };
        if (opts.limit != null) params.limit = opts.limit;
        if (opts.offset != null) params.offset = opts.offset;
        const response = await this.client.get('forums/v2/search/threads', { params });
        return response.data;
    }

    async createForumV2Subforum(data: { category_id: string; name: string; description?: string }): Promise<{ id: string; slug: string } | any> {
        const response = await this.client.post('forums/v2/subforums', data);
        return response.data;
    }

    async getForumV2Threads(
        subforumId: string,
        opts?: { sort?: 'new' | 'hot' | 'top'; q?: string; tag?: string; limit?: number; offset?: number },
    ): Promise<any> {
        const params: any = {};
        if (opts?.sort) params.sort = opts.sort;
        if (opts?.q) params.q = opts.q;
        if (opts?.tag) params.tag = opts.tag;
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        const response = await this.client.get(`forums/v2/subforums/${encodeURIComponent(subforumId)}/threads`, { params });
        return response.data;
    }

    async getForumV2Thread(threadId: string): Promise<any> {
        const response = await this.client.get(`forums/v2/threads/${encodeURIComponent(threadId)}`);
        return response.data;
    }

    async getForumV2Posts(
        threadId: string,
        opts?: { sort?: 'new' | 'top'; limit?: number; offset?: number },
    ): Promise<any> {
        const params: any = {};
        if (opts?.sort) params.sort = opts.sort;
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        const response = await this.client.get(`forums/v2/threads/${encodeURIComponent(threadId)}/posts`, { params });
        return response.data;
    }

    async createForumV2Thread(data: {
        subforum_id: string;
        title: string;
        body: string;
        tags?: string[];
        attachment_url?: string;
        attachment_type?: string;
    }): Promise<{ thread_id: string; post_id: string } | any> {
        const response = await this.client.post('forums/v2/threads', data);
        return response.data;
    }

    async replyForumV2Thread(
        threadId: string,
        data: {
            content: string;
            quote_post_id?: string;
            parent_post_id?: string;
            attachment_url?: string;
            attachment_type?: string;
        },
    ) {
        const response = await this.client.post(`forums/v2/threads/${encodeURIComponent(threadId)}/posts`, data);
        return response.data;
    }

    async voteForumV2Post(postId: string, value: 1 | -1) {
        const response = await this.client.post(`forums/v2/posts/${encodeURIComponent(postId)}/vote`, { value });
        return response.data;
    }

    async watchForumV2Thread(threadId: string, watch: boolean) {
        const response = await this.client.post(`forums/v2/threads/${encodeURIComponent(threadId)}/watch`, null, { params: { watch } });
        return response.data;
    }

    async reportForumV2Post(postId: string, reason: string) {
        const response = await this.client.post(`forums/v2/posts/${encodeURIComponent(postId)}/report`, { reason });
        return response.data;
    }

    async getForumV2Notifications(opts?: { unread_only?: boolean; limit?: number; offset?: number }) {
        const params: any = {};
        if (opts?.unread_only) params.unread_only = true;
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        const response = await this.client.get('forums/v2/notifications', { params });
        return response.data;
    }

    async markForumV2NotificationRead(notificationId: string) {
        const response = await this.client.post(`forums/v2/notifications/${encodeURIComponent(notificationId)}/read`);
        return response.data;
    }

    // Leaderboard
    async getLeaderboard() {
        const response = await this.client.get('leaderboard');
        return response.data;
    }

    async getMyRank() {
        const response = await this.client.get('leaderboard/me');
        return response.data;
    }

    // Admin
    async getAdminStats() {
        const response = await this.client.get('admin/stats');
        return response.data;
    }

    async getAdminUsers(query: string = '') {
        const response = await this.client.get('admin/users', { params: { q: query } });
        return response.data;
    }

    async getAdminChannelReports(skip: number = 0, limit: number = 50) {
        const response = await this.client.get('admin/channel-reports', { params: { skip, limit } });
        return response.data as {
            total: number;
            reports: Array<{
                id: string;
                created_at: string;
                reason: string;
                channel_id: string;
                channel_name: string | null;
                message_id: string;
                message_preview: string | null;
                message_has_attachment: boolean;
                reporter_email: string | null;
                reported_email: string | null;
            }>;
            skip: number;
            limit: number;
        };
    }

    async sendAdminBroadcast(content: string) {
        const response = await this.client.post('admin/broadcast', { content });
        return response.data;
    }

    // Admin: creator applications (approve / reject / provision)
    async getAdminCreatorApplications(
        statusFilter: 'pending' | 'approved' | 'rejected' = 'pending',
        skip: number = 0,
        limit: number = 100,
    ) {
        const response = await this.client.get('admin/creator-applications', {
            params: { status_filter: statusFilter, skip, limit },
        });
        return response.data as {
            applications: Array<{
                id: string;
                user_id: string;
                user_email: string | null;
                applicant_name: string;
                max_name: string;
                max_description: string;
                instagram_handle: string | null;
                tiktok_handle: string | null;
                social_stats: Record<string, any>;
                status: string;
                created_at: string | null;
            }>;
            skip: number;
            limit: number;
        };
    }

    /** Approve → provisions the Creator (status "onboarding"), flips is_creator. */
    async approveCreatorApplication(applicationId: string, tier: string) {
        const response = await this.client.post(
            `admin/creator-applications/${applicationId}/approve`,
            { tier },
        );
        return response.data as { ok: boolean; creator: any };
    }

    async rejectCreatorApplication(applicationId: string, notes?: string) {
        const response = await this.client.post(
            `admin/creator-applications/${applicationId}/reject`,
            { notes: notes ?? null },
        );
        return response.data as { ok: boolean };
    }

    /** Force a creator live / paused / taken-down. "live" also approves the Apple SKU. */
    async setAdminCreatorStatus(creatorId: string, status: 'live' | 'paused' | 'takedown' | 'onboarding') {
        const response = await this.client.post(`admin/creators/${creatorId}/status`, { status });
        return response.data as { ok: boolean; creator: any };
    }

    /** Attach marketplace card art by URL (the manual-first art pipeline). */
    async setAdminCreatorArt(creatorId: string, artUrl: string) {
        const form = new FormData();
        form.append('art_url', artUrl);
        const response = await this.client.post(`admin/creators/${creatorId}/art`, form, {
            headers: { 'Content-Type': 'multipart/form-data' }, timeout: 30000,
        });
        return response.data;
    }

    async sendAdminDirect(userId: string, content: string) {
        const response = await this.client.post('admin/direct', { user_id: userId, content });
        return response.data;
    }

    // Admin: Chat as Max for a specific user
    async getAdminUserChat(userId: string) {
        const response = await this.client.get(`admin/users/${userId}/chat`);
        return response.data;
    }

    async sendAdminUserChat(userId: string, message: string) {
        const response = await this.client.post(`admin/users/${userId}/chat`, { message });
        return response.data;
    }

    async getAdminForumsV2Overview() {
        const response = await this.client.get('admin/forums/v2/overview', { timeout: 30_000 });
        return response.data as {
            categories: Array<{
                id: string;
                name: string;
                slug: string;
                description?: string | null;
                order: number;
                subforums: Array<{
                    id: string;
                    category_id: string;
                    name: string;
                    slug: string;
                    description?: string | null;
                    order: number;
                    access_tier: string;
                    is_read_only: boolean;
                    thread_count: number;
                }>;
            }>;
        };
    }

    async createAdminForumCategory(body: { name: string; description?: string; order?: number }) {
        const response = await this.client.post('admin/forums/v2/categories', body, { timeout: 30_000 });
        return response.data as { id: string; slug: string };
    }

    async updateAdminForumCategory(
        categoryId: string,
        body: { name?: string; description?: string; order?: number },
    ) {
        const response = await this.client.patch(`admin/forums/v2/categories/${encodeURIComponent(categoryId)}`, body, {
            timeout: 30_000,
        });
        return response.data as { id: string; slug: string };
    }

    async deleteAdminForumCategory(categoryId: string) {
        const response = await this.client.delete(`admin/forums/v2/categories/${encodeURIComponent(categoryId)}`, {
            timeout: 30_000,
        });
        return response.data as { deleted: boolean };
    }

    async createAdminForumSubforum(body: {
        category_id: string;
        name: string;
        description?: string;
        access_tier: 'public' | 'premium';
        is_read_only?: boolean;
        order?: number | null;
    }) {
        const response = await this.client.post('admin/forums/v2/subforums', body, { timeout: 30_000 });
        return response.data as { id: string; slug: string };
    }

    async updateAdminForumSubforum(
        subforumId: string,
        body: {
            category_id?: string;
            name?: string;
            description?: string;
            access_tier?: 'public' | 'premium';
            is_read_only?: boolean;
            order?: number | null;
        },
    ) {
        const response = await this.client.patch(
            `admin/forums/v2/subforums/${encodeURIComponent(subforumId)}`,
            body,
            { timeout: 30_000 },
        );
        return response.data as { id: string; slug: string };
    }

    async deleteAdminForumSubforum(subforumId: string) {
        const response = await this.client.delete(`admin/forums/v2/subforums/${encodeURIComponent(subforumId)}`, {
            timeout: 30_000,
        });
        return response.data as { deleted: boolean };
    }

    // Schedules
    async generateSchedule(courseId: string, moduleNumber: number, numDays: number = 30, preferences?: any) {
        // AI generation — can take 20-40s. Use the long timeout.
        const response = await this.client.post('schedules/generate', {
            course_id: courseId,
            module_number: moduleNumber,
            num_days: numDays,
            preferences,
        }, { timeout: 60_000 });
        return response.data;
    }

    async generateMaxxSchedule(
        maxxId: string,
        wakeTime: string,
        sleepTime: string,
        outsideToday: boolean = false,
        numDays: number = 30,
        heightComponents?: Record<string, boolean>,
    ) {
        const body: Record<string, unknown> = {
            maxx_id: maxxId,
            wake_time: wakeTime,
            sleep_time: sleepTime,
            outside_today: outsideToday,
            num_days: numDays,
        };
        if (maxxId === 'heightmax' && heightComponents && Object.keys(heightComponents).length > 0) {
            body.height_components = heightComponents;
        }
        const response = await this.client.post('schedules/generate-maxx', body, { timeout: 60_000 });
        return response.data;
    }

    async getMaxxSchedule(maxxId: string) {
        const response = await this.client.get(`schedules/maxx/${maxxId}`);
        return response.data;
    }

    async getCurrentSchedule(courseId?: string, moduleNumber?: number) {
        const response = await this.client.get('schedules/current', {
            params: {
                course_id: courseId,
                module_number: moduleNumber
            }
        });
        return response.data;
    }

    async getSchedule(scheduleId: string) {
        const response = await this.client.get(`schedules/${scheduleId}`);
        return response.data;
    }

    async completeScheduleTask(scheduleId: string, taskId: string, feedback?: string) {
        const response = await this.client.put(`schedules/${scheduleId}/tasks/${taskId}/complete`, {
            feedback,
        });
        return response.data;
    }

    async uncompleteScheduleTask(scheduleId: string, taskId: string) {
        const response = await this.client.put(`schedules/${scheduleId}/tasks/${taskId}/pending`, {});
        return response.data;
    }

    async updateSchedulePreferences(preferences: any) {
        const response = await this.client.put('schedules/preferences', preferences);
        return response.data;
    }

    async adaptSchedule(scheduleId: string, feedback: string) {
        const response = await this.client.post(`schedules/${scheduleId}/adapt`, { feedback });
        return response.data;
    }

    async editScheduleTask(
        scheduleId: string,
        taskId: string,
        updates: { time?: string; title?: string; description?: string; duration_minutes?: number },
        scope: 'instance' | 'series' = 'instance',
    ) {
        // scope="series" applies the change to the recurring part across every
        // day and durably re-pins a moved time through future re-expansions.
        const response = await this.client.put(`schedules/${scheduleId}/tasks/${taskId}`, updates, {
            params: { scope },
        });
        return response.data;
    }

    async deleteScheduleTask(scheduleId: string, taskId: string, scope: 'instance' | 'series' = 'instance') {
        // scope="series" removes the whole recurring part across every day and
        // keeps it from coming back on re-expansion (used by the routine review).
        const response = await this.client.delete(`schedules/${scheduleId}/tasks/${taskId}`, {
            params: { scope },
        });
        return response.data;
    }

    async stopSchedule(scheduleId: string) {
        const response = await this.client.post(`schedules/${scheduleId}/stop`);
        return response.data;
    }

    async getTaskGuide(scheduleId: string, taskId: string): Promise<{
        task_key: string;
        title: string;
        overview: string;
        hero_image?: string;
        steps: {
            n: number;
            title: string;
            body: string;
            tip: string | null;
            image?: string;
            video?: string | null;
            ingredients?: { name: string; generic_name?: string; note: string; brand?: string; url?: string; image?: string }[];
        }[];
        products?: { name: string; note: string; url?: string; image?: string }[];
        duration_minutes: number;
        why_it_matters: string;
    }> {
        const response = await this.client.get(`schedules/${scheduleId}/tasks/${taskId}/guide`);
        return response.data;
    }

    async getActiveSchedules(): Promise<{ count: number; labels: string[]; max: number }> {
        const response = await this.client.get('schedules/active/all');
        return response.data;
    }

    async getActiveSchedulesFull(): Promise<{
        schedules: any[];
        schedule_streak?: { current: number; last_perfect_date?: string | null; today_date: string };
        today_date?: string;
        newly_earned_achievements?: EarnedAchievement[];
        gamification?: Gamification | null;
    }> {
        const response = await this.client.get('schedules/active/full');
        return response.data;
    }

    /** Notification engagement signals (best-effort). `client` is private, so these
     *  must be methods — calling api.post(...) directly throws "post is not a
     *  function" and crashes the app at startup. */
    async notificationOpened(): Promise<void> {
        try { await this.client.post('notifications/opened'); } catch { /* best-effort */ }
    }
    async notificationActivity(): Promise<void> {
        try { await this.client.post('notifications/activity'); } catch { /* best-effort */ }
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Creator platform
    // ─────────────────────────────────────────────────────────────────────

    /** Studio: my creator profile (private view). */
    async getMyCreator(): Promise<any> {
        const response = await this.client.get('creators/me');
        return response.data;
    }
    async updateMyCreator(patch: Record<string, unknown>): Promise<any> {
        const response = await this.client.patch('creators/me', patch);
        return response.data;
    }
    async getMyCreatorPosts(): Promise<{ posts: any[] }> {
        const response = await this.client.get('creators/me/posts');
        return response.data;
    }
    async getMyCreatorStats(): Promise<any> {
        const response = await this.client.get('creators/me/stats');
        return response.data;
    }

    /** Create an update. Video is a local file uri (multipart, background upload).
     *  A text post sends no video. Mirrors uploadProgressPhoto's boundary handling. */
    async createCreatorPost(input: {
        type: 'video' | 'text';
        body: string;
        videoUri?: string | null;
        posterUri?: string | null;
        durationS?: number | null;
    }): Promise<any> {
        const formData = new FormData();
        formData.append('type', input.type);
        formData.append('body', input.body ?? '');
        if (input.durationS != null) formData.append('duration_s', String(Math.round(input.durationS)));
        const appendFile = (field: string, uri: string, name: string, type: string) => {
            if (Platform.OS === 'web') {
                return fetch(uri).then((r) => r.blob()).then((b) => formData.append(field, b, name));
            }
            // @ts-ignore RN FormData file shape
            formData.append(field, { uri, name, type });
            return Promise.resolve();
        };
        if (input.videoUri) await appendFile('video', input.videoUri, 'update.mp4', 'video/mp4');
        if (input.posterUri) await appendFile('poster', input.posterUri, 'poster.jpg', 'image/jpeg');
        const response = await this.client.post('creators/me/posts', formData, {
            timeout: 120_000, // large video upload
            transformRequest: [(data: unknown, headers?: Record<string, string>) => {
                if (headers) delete headers['Content-Type'];
                return data;
            }],
        });
        return response.data;
    }
    async editCreatorPost(postId: string, patch: { body?: string; pinned?: boolean }): Promise<any> {
        const response = await this.client.patch(`creators/me/posts/${postId}`, patch);
        return response.data;
    }
    async deleteCreatorPost(postId: string): Promise<void> {
        await this.client.delete(`creators/me/posts/${postId}`);
    }
    async getPostCommentsForManage(postId: string): Promise<{ comments: any[] }> {
        const response = await this.client.get(`creators/me/posts/${postId}/comments`);
        return response.data;
    }
    async pinCreatorComment(commentId: string): Promise<void> {
        await this.client.post(`creators/comments/${commentId}/pin`);
    }
    async blockCreatorUser(userId: string): Promise<void> {
        await this.client.post('creators/me/blocks', { user_id: userId });
    }
    async unblockCreatorUser(userId: string): Promise<void> {
        await this.client.delete(`creators/me/blocks/${userId}`);
    }

    // Course editing
    async getMyCreatorLessons(): Promise<{ lessons: any[]; course_version: number; course_modules: Record<string, { title?: string }> }> {
        const response = await this.client.get('creators/me/course/lessons');
        return response.data;
    }
    async upsertCreatorLesson(lesson: Record<string, unknown>): Promise<any> {
        const response = await this.client.put('creators/me/course/lessons', lesson);
        return response.data;
    }
    async deleteCreatorLesson(lessonId: string): Promise<void> {
        await this.client.delete(`creators/me/course/lessons/${lessonId}`);
    }
    /** Batch move/reorder — one course_version bump server-side. */
    async reorderCreatorLessons(items: { id: string; module_number: number; sort: number }[]): Promise<{ course_version: number }> {
        const response = await this.client.post('creators/me/course/reorder', { items });
        return response.data;
    }
    /** Name a module ("Foundations"); empty title clears it. */
    async setCreatorModuleTitle(moduleNumber: number, title: string): Promise<{ course_modules: Record<string, { title?: string }> }> {
        const response = await this.client.patch('creators/me/course/modules', { module_number: moduleNumber, title });
        return response.data;
    }
    /** Server-computed go-live checklist (shares rules with the go_live gate). */
    async getCreatorChecklist(): Promise<{
        items: { key: string; label: string; done: boolean; required: boolean }[];
        can_go_live: boolean; done_count: number; total_count: number; is_live: boolean;
    }> {
        const response = await this.client.get('creators/me/checklist');
        return response.data;
    }
    /** AI course assist. mode 'outline' → {modules:[{title,lessons:[{title,subtitle}]}]};
     *  mode 'lesson' → {subtitle, body_md}. 503 = assist unavailable on this build. */
    async creatorCourseAssist(body: {
        mode: 'outline' | 'lesson'; topic?: string; notes?: string;
        module_count?: number; lesson_title?: string;
    }): Promise<any> {
        const response = await this.client.post('creators/me/course/assist', body, { timeout: 90000 });
        return response.data;
    }
    async uploadCreatorAvatar(uri: string): Promise<any> {
        const form = new FormData();
        form.append('image', { uri, name: 'avatar.jpg', type: 'image/jpeg' } as any);
        const response = await this.client.post('creators/me/avatar', form, {
            headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
        });
        return response.data;
    }

    // ── User side ──
    async browseCreators(): Promise<{ creators: any[] }> {
        const response = await this.client.get('creators/browse');
        return response.data;
    }
    async getCreatorByMaxx(maxxId: string): Promise<any> {
        const response = await this.client.get(`creators/by-maxx/${maxxId}`);
        return response.data;
    }
    async getCreatorFeed(maxxId: string, opts?: { limit?: number; offset?: number }): Promise<{
        posts: any[]; total: number; has_access: boolean; creator: any;
    }> {
        const response = await this.client.get(`creators/by-maxx/${maxxId}/posts`, {
            params: { limit: opts?.limit ?? 20, offset: opts?.offset ?? 0 },
        });
        return response.data;
    }
    /** The subscriber-facing course: published lessons grouped into modules.
     *  Non-subscribers get the outline with content redacted server-side
     *  (free-preview lessons stay readable). */
    async getCreatorCourse(maxxId: string): Promise<{
        creator: any;
        modules: { module_number: number; title: string; lessons: any[] }[];
        course_version: number; has_access: boolean;
        lesson_count: number; free_preview_count: number;
    }> {
        const response = await this.client.get(`creators/by-maxx/${maxxId}/course`);
        return response.data;
    }
    /** Debounced feed impression (fire-and-forget; once per post per session). */
    async recordCreatorPostView(postId: string): Promise<void> {
        await this.client.post(`creators/posts/${postId}/view`);
    }
    async likeCreatorPost(postId: string): Promise<{ like_count: number }> {
        const response = await this.client.post(`creators/posts/${postId}/like`);
        return response.data;
    }
    async unlikeCreatorPost(postId: string): Promise<{ like_count: number }> {
        const response = await this.client.delete(`creators/posts/${postId}/like`);
        return response.data;
    }
    async getCreatorPostComments(postId: string, opts?: { limit?: number; offset?: number }): Promise<{
        comments: any[]; total: number;
    }> {
        const response = await this.client.get(`creators/posts/${postId}/comments`, {
            params: { limit: opts?.limit ?? 40, offset: opts?.offset ?? 0 },
        });
        return response.data;
    }
    async addCreatorComment(postId: string, body: string): Promise<any> {
        const response = await this.client.post(`creators/posts/${postId}/comments`, { body });
        return response.data;
    }
    async deleteCreatorComment(commentId: string): Promise<void> {
        await this.client.delete(`creators/comments/${commentId}`);
    }
    async reportCreatorComment(commentId: string, reason?: string): Promise<{ message: string }> {
        const response = await this.client.post(`creators/comments/${commentId}/report`, { reason: reason ?? '' });
        return response.data;
    }
    async getMyCreatorSubscriptions(): Promise<{ subscriptions: any[] }> {
        const response = await this.client.get('creators/subscriptions');
        return response.data;
    }
    async verifyCreatorSubscription(maxxId: string, transactionId: string, productId?: string): Promise<{ status: string; schedule_created?: boolean; schedule_blocked?: string | null }> {
        const response = await this.client.post(`creators/subscribe/${maxxId}/verify`, {
            transaction_id: transactionId, product_id: productId,
        });
        return response.data;
    }
    /** DEV-only: activate a creator sub without Apple (sim testing). */
    async devActivateCreatorSubscription(maxxId: string): Promise<{ status: string; schedule_created?: boolean; schedule_blocked?: string | null }> {
        if (!__DEV__) throw new Error('dev-activate is unavailable in production builds.');
        const response = await this.client.post(`creators/subscribe/${maxxId}/dev-activate`);
        return response.data;
    }

    // ── Community channels (member side) ──
    /** A creator maxx's channels. 403 {detail:'Subscribe to join the community.'}
     *  for non-members; defaults (#announcements + #general) self-heal server-side. */
    async getCreatorChannels(maxxId: string): Promise<{ forums: any[]; total: number }> {
        const response = await this.client.get('forums', { params: { maxx_id: maxxId } });
        return response.data;
    }
    /** Delete a channel message — author, admin, or the owning creator. */
    async deleteChannelMessage(channelId: string, messageId: string): Promise<void> {
        await this.client.delete(`forums/${channelId}/messages/${messageId}`);
    }

    // ── Studio: channels CRUD ──
    async getMyCreatorChannels(): Promise<{ channels: any[] }> {
        const response = await this.client.get('creators/me/channels');
        return response.data;
    }
    /** 409 = duplicate name, 422 = cap (8 channels). */
    async createCreatorChannel(body: {
        name: string;
        description?: string;
        who_can_post?: 'creator' | 'members';
        allow_replies?: boolean;
        icon?: string;
    }): Promise<any> {
        const response = await this.client.post('creators/me/channels', body);
        return response.data;
    }
    async updateCreatorChannel(channelId: string, patch: Record<string, unknown>): Promise<any> {
        const response = await this.client.patch(`creators/me/channels/${channelId}`, patch);
        return response.data;
    }
    async reorderCreatorChannels(ids: string[]): Promise<any> {
        const response = await this.client.post('creators/me/channels/reorder', { order: ids });
        return response.data;
    }
    /** Archive (soft-delete). 422 when it's the creator's last channel. */
    async archiveCreatorChannel(channelId: string): Promise<any> {
        const response = await this.client.delete(`creators/me/channels/${channelId}`);
        return response.data;
    }

    // ── Studio: daily-program habits ──
    async getMyCreatorHabits(): Promise<{ habits: CreatorHabitRow[]; habits_version: number }> {
        const response = await this.client.get('creators/me/habits');
        return response.data;
    }
    /** Whole-list save: server archives omitted rows, mints slugs for new ones,
     *  re-registers the catalog and regenerates subscriber schedules. 422 when a
     *  live max would leave the 2-8 habit range. */
    async putMyCreatorHabits(habits: CreatorHabitInput[]): Promise<{ habits: CreatorHabitRow[]; habits_version: number }> {
        const response = await this.client.put('creators/me/habits', { habits }, { timeout: 60_000 });
        return response.data;
    }
}

export const api = new ApiService();
export default api;
