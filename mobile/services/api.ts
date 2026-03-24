/**
 * API Service - Backend communication
 */

import axios, { AxiosInstance } from 'axios';
import { Platform } from 'react-native';
import { getItemAsync, setItemAsync, deleteItemAsync } from './storage';

const API_BASE_URL =
    process.env.EXPO_PUBLIC_API_BASE_URL?.trim() ||
    'http://localhost:8000/api/';

class ApiService {
    private client: AxiosInstance;
    private accessToken: string | null = null;

    constructor() {
        this.client = axios.create({
            baseURL: API_BASE_URL,
            headers: { 'Content-Type': 'application/json' },
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

        // Response interceptor for token refresh
        this.client.interceptors.response.use(
            (response) => response,
            async (error) => {
                if (error.response?.status === 401) {
                    await this.refreshToken();
                    return this.client.request(error.config);
                }
                return Promise.reject(error);
            }
        );
    }

    getBaseUrl() {
        return API_BASE_URL;
    }

    resolveAttachmentUrl(url?: string) {
        if (!url) return undefined;
        if (url.startsWith('http')) return url;
        // Construct base URL from API_BASE_URL (removing /api/)
        const baseUrl = API_BASE_URL.replace('/api/', '');
        return `${baseUrl}${url.startsWith('/') ? url : `/${url}`}`;
    }

    private async getToken(): Promise<string | null> {
        if (this.accessToken) return this.accessToken;
        return await getItemAsync('access_token');
    }

    private async refreshToken(): Promise<void> {
        const refreshToken = await getItemAsync('refresh_token');
        if (!refreshToken) throw new Error('No refresh token');

        const response = await axios.post(`${API_BASE_URL}auth/refresh`, { refresh_token: refreshToken });
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
        const response = await this.client.post('auth/signup', { email, password, first_name, last_name, username, phone_number });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    /** `identifier` = email, username, or phone (matches account on file). */
    async login(identifier: string, password: string) {
        const response = await this.client.post('auth/login/json', { identifier, password });
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

    async uploadProgressPhoto(imageUri: string) {
        const formData = new FormData();
        // @ts-ignore - React Native FormData accepts { uri, name, type }
        formData.append('file', {
            uri: imageUri,
            name: 'progress.jpg',
            type: 'image/jpeg',
        });
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

    async updateProfile(data: any) {
        const response = await this.client.put('users/profile', data);
        return response.data;
    }

    async updateAccount(data: { first_name?: string; last_name?: string; username?: string }) {
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
        const buildForm = () => {
            const formData = new FormData();
            if (Platform.OS === 'web') {
                return (async () => {
                    const fd = new FormData();
                    fd.append('front', await fetch(frontUri).then((r) => r.blob()), 'front.jpg');
                    fd.append('left', await fetch(leftUri).then((r) => r.blob()), 'left.jpg');
                    fd.append('right', await fetch(rightUri).then((r) => r.blob()), 'right.jpg');
                    return fd;
                })();
            }
            // @ts-ignore RN file shape
            formData.append('front', { uri: frontUri, type: 'image/jpeg', name: 'front.jpg' });
            // @ts-ignore
            formData.append('left', { uri: leftUri, type: 'image/jpeg', name: 'left.jpg' });
            // @ts-ignore
            formData.append('right', { uri: rightUri, type: 'image/jpeg', name: 'right.jpg' });
            return Promise.resolve(formData);
        };

        const doFetch = async (formData: FormData) => {
            const token = await this.getToken();
            const headers: Record<string, string> = {};
            if (token) headers.Authorization = `Bearer ${token}`;
            return fetch(url, { method: 'POST', headers, body: formData });
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
            } catch {
                /* keep text */
            }
            throw new Error(`Upload failed (${res.status}): ${msg}`);
        }
        return res.json() as Promise<unknown>;
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

        const response = await this.client.post('scans/upload-video', formData);
        return response.data;
    }

    async uploadScanVideoBlob(blob: Blob) {
        const formData = new FormData();
        formData.append('video', blob, 'scan.webm');
        const response = await this.client.post('scans/upload-video', formData);
        return response.data;
    }

    async analyzeScan(scanId: string) {
        const response = await this.client.post(`scans/${scanId}/analyze`);
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

    async getScanHistory() {
        const response = await this.client.get('scans/history');
        return response.data;
    }

    async getScanById(scanId: string) {
        const response = await this.client.get(`scans/${scanId}`);
        return response.data;
    }

    // Payments
    async createCheckoutSession(successUrl: string, cancelUrl: string) {
        const response = await this.client.post('payments/create-session', { success_url: successUrl, cancel_url: cancelUrl });
        return response.data;
    }

    async getSubscriptionStatus() {
        const response = await this.client.get('payments/status');
        return response.data;
    }

    async testActivateSubscription() {
        // Dev only: Activate subscription without Stripe webhook
        const response = await this.client.post('payments/test-activate');
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
    async sendChatMessage(message: string, attachmentUrl?: string, attachmentType?: string, initContext?: string) {
        const body: any = {
            message,
            attachment_url: attachmentUrl,
            attachment_type: attachmentType,
        };
        if (initContext) body.init_context = initContext;
        const response = await this.client.post('chat/message', body);
        return response.data;
    }

    async getChatHistory() {
        const response = await this.client.get('chat/history');
        return response.data;
    }

    // Channels (Discord-like chat)
    async getChannels(search?: string) {
        const response = await this.client.get('forums', { params: { q: search } });
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

    // Schedules
    async generateSchedule(courseId: string, moduleNumber: number, numDays: number = 7, preferences?: any) {
        const response = await this.client.post('schedules/generate', {
            course_id: courseId,
            module_number: moduleNumber,
            num_days: numDays,
            preferences,
        });
        return response.data;
    }

    async generateMaxxSchedule(
        maxxId: string,
        wakeTime: string,
        sleepTime: string,
        outsideToday: boolean = false,
        numDays: number = 7,
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
        const response = await this.client.post('schedules/generate-maxx', body);
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
}

export const api = new ApiService();
export default api;
