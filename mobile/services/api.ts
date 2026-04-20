/**
 * API Service - Backend communication
 */

import axios, { AxiosInstance } from 'axios';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { getItemAsync, setItemAsync, deleteItemAsync } from './storage';

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
 * - Native dev: if .env is still loopback, use Metro’s dev-machine IP (physical iPhone).
 */
function resolveApiBaseUrl(): string {
    const fromEnv =
        process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || 'http://localhost:8000/api/';

    if (__DEV__ && Platform.OS !== 'web' && envTargetsLoopback(fromEnv)) {
        const devHost = getExpoDevBundlerHost();
        if (devHost) {
            const next = replaceUrlHostname(fromEnv, devHost);
            if (__DEV__) {
                console.log(`[Max] API base ${next} (dev host from Metro; .env used loopback)`);
            }
            return next;
        }
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

class ApiService {
    private client: AxiosInstance;
    private accessToken: string | null = null;

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
                if (isNetErr && cfg && !skip) {
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
        return await getItemAsync('access_token');
    }

    private async refreshToken(): Promise<void> {
        const refreshToken = await getItemAsync('refresh_token');
        if (!refreshToken) throw new Error('No refresh token');

        const response = await axios.post(`${API_BASE_URL}auth/refresh`, { refresh_token: refreshToken }, {
            timeout: 15_000,
        });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
    }

    async setTokens(accessToken: string, refreshToken: string): Promise<void> {
        this.accessToken = accessToken;
        await setItemAsync('access_token', accessToken);
        await setItemAsync('refresh_token', refreshToken);
    }

    async clearTokens(): Promise<void> {
        this.accessToken = null;
        await deleteItemAsync('access_token');
        await deleteItemAsync('refresh_token');
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
        const response = await this.client.post(
            'auth/faux-signup',
            {},
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

    async getMe() {
        const response = await this.client.get('users/me');
        return response.data;
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

    async deleteAccount(password: string) {
        const response = await this.client.delete('users/me', { data: { password } });
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
        activity_level?: string;
        equipment?: string[];
        skin_type?: string;
        unit_system?: string;
        timezone?: string;
        completed?: boolean;
    }) {
        const response = await this.client.post('users/onboarding', data);
        return response.data;
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

        const doFetch = async (formData: FormData) => {
            const token = await this.getToken();
            const headers: Record<string, string> = {};
            if (token) headers.Authorization = `Bearer ${token}`;
            return fetch(url, { method: 'POST', headers, body: formData });
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
        const response = await this.client.get('scans/latest');
        return response.data;
    }

    async dismissPostSubscriptionOnboarding() {
        const response = await this.client.post('users/post-subscription-onboarding/dismiss');
        return response.data;
    }

    async completeMainAppTour() {
        const response = await this.client.post('users/main-app-tour/complete');
        return response.data;
    }

    async completeSendblueConnect(prefs?: { sms_opt_in?: boolean; app_notifications_opt_in?: boolean }) {
        const response = await this.client.post('users/sendblue-connect/complete', prefs ?? {});
        return response.data;
    }

    /** Dev-only: allow bypassing inbound SMS requirement. */
    async completeSendblueConnectDevSkip() {
        const response = await this.client.post('users/sendblue-connect/complete', undefined, {
            headers: { 'x-dev-skip-sendblue': '1' },
        });
        return response.data;
    }

    /** DEBUG: mark SMS engaged only — then show notification channel picker. */
    async devSkipSendblueEngageOnly() {
        const response = await this.client.post('users/sendblue-connect/dev-skip-engage');
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

    async patchNotificationChannels(prefs: { sms_opt_in: boolean; app_notifications_opt_in: boolean }) {
        const response = await this.client.patch('users/notification-channels', prefs);
        return response.data;
    }

    async patchCoachingTone(tone: 'default' | 'hardcore' | 'gentle' | 'influencer') {
        const response = await this.client.patch('users/coaching-tone', { tone });
        return response.data as { message: string; tone: string };
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

    // Courses
    async getCourses() {
        const response = await this.client.get('courses');
        return response.data;
    }

    async getCourse(courseId: string) {
        const response = await this.client.get(`courses/${courseId}`);
        return response.data;
    }

    async startCourse(courseId: string) {
        const response = await this.client.post(`courses/${courseId}/start`);
        return response.data;
    }

    async completeChapter(courseId: string, chapterId: string, moduleNumber: number) {
        const response = await this.client.put(`courses/${courseId}/complete-chapter`, {
            chapter_id: chapterId,
            module_number: moduleNumber
        });
        return response.data;
    }

    async getCourseProgress() {
        const response = await this.client.get('courses/progress/current');
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
    ): Promise<{ response: string; choices?: string[] }> {
        const body: any = {
            message,
            attachment_url: attachmentUrl,
            attachment_type: attachmentType,
        };
        if (initContext) body.init_context = initContext;
        if (chatIntent) body.chat_intent = chatIntent;
        // LangChain agent may chain multiple tool calls + LLM fallback,
        // so allow up to 120s before timing out.
        const response = await this.client.post('chat/message', body, {
            timeout: 120_000,
            // @ts-expect-error custom flag consumed by response interceptor
            _skipNetRetry: true,
        });
        return response.data;
    }

    async getChatHistory(opts?: { limit?: number; offset?: number }) {
        const params: Record<string, number> = {};
        if (opts?.limit != null) params.limit = opts.limit;
        if (opts?.offset != null) params.offset = opts.offset;
        const response = await this.client.get('chat/history', { params });
        return response.data;
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

    async getChannelMessages(channelId: string, limit: number = 50, query?: string) {
        const response = await this.client.get(`forums/${channelId}/messages`, { params: { limit, query } });
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

    async editScheduleTask(scheduleId: string, taskId: string, updates: { time?: string; title?: string; description?: string; duration_minutes?: number }) {
        const response = await this.client.put(`schedules/${scheduleId}/tasks/${taskId}`, updates);
        return response.data;
    }

    async deleteScheduleTask(scheduleId: string, taskId: string) {
        const response = await this.client.delete(`schedules/${scheduleId}/tasks/${taskId}`);
        return response.data;
    }

    async stopSchedule(scheduleId: string) {
        const response = await this.client.post(`schedules/${scheduleId}/stop`);
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
    }> {
        const response = await this.client.get('schedules/active/full');
        return response.data;
    }
}

export const api = new ApiService();
export default api;
