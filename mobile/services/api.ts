/**
 * API Service - Backend communication
 */

import axios, { AxiosInstance } from 'axios';
import * as SecureStore from 'expo-secure-store';

// Use your computer's IP address for physical devices or emulators
// For Android Emulator: http://10.0.2.2:8000/api
// For iOS Simulator: http://localhost:8000/api  
// For physical devices (Expo Go): Use your computer's local IP
const API_BASE_URL = 'https://dalila-monocled-tatyana.ngrok-free.dev/api/';

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
        return await SecureStore.getItemAsync('access_token');
    }

    private async refreshToken(): Promise<void> {
        const refreshToken = await SecureStore.getItemAsync('refresh_token');
        if (!refreshToken) throw new Error('No refresh token');

        const response = await axios.post(`${API_BASE_URL}auth/refresh`, { refresh_token: refreshToken });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
    }

    async setTokens(accessToken: string, refreshToken: string): Promise<void> {
        this.accessToken = accessToken;
        await SecureStore.setItemAsync('access_token', accessToken);
        await SecureStore.setItemAsync('refresh_token', refreshToken);
    }

    async clearTokens(): Promise<void> {
        this.accessToken = null;
        await SecureStore.deleteItemAsync('access_token');
        await SecureStore.deleteItemAsync('refresh_token');
    }

    // Auth
    async signup(email: string, password: string, bio?: string) {
        const response = await this.client.post('auth/signup', { email, password, bio });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    async login(email: string, password: string) {
        const response = await this.client.post('auth/login/json', { email, password });
        await this.setTokens(response.data.access_token, response.data.refresh_token);
        return response.data;
    }

    async getMe() {
        const response = await this.client.get('users/me');
        return response.data;
    }

    async uploadAvatar(imageUri: string) {
        const formData = new FormData();
        // @ts-ignore
        formData.append('file', {
            uri: imageUri,
            name: 'avatar.jpg',
            type: 'image/jpeg',
        });

        const response = await this.client.post('users/me/avatar', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    }

    async updateProfile(data: any) {
        const response = await this.client.put('users/profile', data);
        return response.data;
    }

    // Onboarding
    async saveOnboarding(data: { goals: string[]; experience_level: string }) {
        const response = await this.client.post('users/onboarding', data);
        return response.data;
    }

    // Scans
    async uploadScanVideo(videoUri: string) {
        const formData = new FormData();
        // @ts-ignore
        formData.append('video', {
            uri: videoUri,
            type: 'video/mp4',
            name: 'scan.mp4',
        });

        const response = await this.client.post('scans/upload-video', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
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
    async sendChatMessage(message: string, attachmentUrl?: string, attachmentType?: string) {
        const response = await this.client.post('chat/message', {
            message,
            attachment_url: attachmentUrl,
            attachment_type: attachmentType
        });
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

    async getChannelMessages(channelId: string, limit: number = 50, query?: string) {
        const response = await this.client.get(`forums/${channelId}/messages`, { params: { limit, query } });
        return response.data;
    }

    async uploadChatFile(formData: FormData) {
        const response = await this.client.post('forums/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
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

    // Admin: Chat as Cannon for a specific user
    async getAdminUserChat(userId: string) {
        const response = await this.client.get(`admin/users/${userId}/chat`);
        return response.data;
    }

    async sendAdminUserChat(userId: string, message: string) {
        const response = await this.client.post(`admin/users/${userId}/chat`, { message });
        return response.data;
    }
}

export const api = new ApiService();
export default api;
