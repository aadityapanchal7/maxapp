import { keepPreviousData, useQuery } from '@tanstack/react-query';
import api from '../services/api';
import { queryKeys } from '../lib/queryClient';

const STALE_MAXXES_MS = 5 * 60 * 1000;
const STALE_SCHEDULES_FULL_MS = 60 * 1000;
const STALE_CHANNELS_MS = 2 * 60 * 1000;
const STALE_FORUM_V2_MS = 60 * 1000;
const STALE_CHAT_HISTORY_MS = 60 * 1000;
const STALE_MAXX_MS = 3 * 60 * 1000;

export function useMaxxesQuery() {
    return useQuery({
        queryKey: queryKeys.maxes,
        queryFn: () => api.getMaxxes(),
        staleTime: STALE_MAXXES_MS,
    });
}

export function useActiveSchedulesFullQuery() {
    return useQuery({
        queryKey: queryKeys.schedulesActiveFull,
        queryFn: () => api.getActiveSchedulesFull(),
        staleTime: STALE_SCHEDULES_FULL_MS,
    });
}

export function useMaxxQuery(maxxId: string | undefined) {
    return useQuery({
        queryKey: queryKeys.maxx(maxxId ?? ''),
        queryFn: () => api.getMaxx(maxxId as string),
        enabled: !!maxxId,
        staleTime: STALE_MAXX_MS,
    });
}

export function useMaxxScheduleQuery(maxxId: string | undefined, enabled: boolean) {
    return useQuery({
        queryKey: queryKeys.maxxSchedule(maxxId ?? ''),
        queryFn: async () => {
            const r = await api.getMaxxSchedule(maxxId as string);
            return r?.schedule ?? null;
        },
        enabled: !!maxxId && enabled,
        staleTime: STALE_SCHEDULES_FULL_MS,
    });
}

export function useActiveSchedulesSummaryQuery(enabled: boolean) {
    return useQuery({
        queryKey: queryKeys.activeSchedulesSummary,
        queryFn: () => api.getActiveSchedules(),
        enabled,
        staleTime: STALE_SCHEDULES_FULL_MS,
    });
}

export function useChannelsQuery(searchTrimmed: string) {
    return useQuery({
        queryKey: queryKeys.channels(searchTrimmed),
        queryFn: async () => {
            const res = await api.getChannels(searchTrimmed, { limit: 200, offset: 0 });
            return res?.forums ?? [];
        },
        placeholderData: keepPreviousData,
        staleTime: STALE_CHANNELS_MS,
    });
}

export function useForumV2CategoriesQuery() {
    return useQuery({
        queryKey: queryKeys.forumV2Categories,
        queryFn: async () => {
            const res = await api.getForumV2Categories();
            return res?.categories ?? [];
        },
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useForumV2SubforumsQuery(categoryId: string | null) {
    return useQuery({
        queryKey: queryKeys.forumV2Subforums(categoryId),
        queryFn: async () => {
            const res = await api.getForumV2Subforums(categoryId ?? undefined);
            return res?.subforums ?? [];
        },
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useForumV2SearchQuery(q: string) {
    const trimmed = q.trim();
    return useQuery({
        queryKey: queryKeys.forumV2Search(trimmed),
        queryFn: async () => {
            const res = await api.searchForumV2Threads({ q: trimmed, limit: 40, offset: 0 });
            return res?.threads ?? [];
        },
        enabled: trimmed.length >= 2,
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useForumV2ThreadsQuery(args: { subforumId: string; sort: 'new' | 'hot' | 'top'; q: string; tag: string }) {
    const { subforumId, sort, q, tag } = args;
    return useQuery({
        queryKey: queryKeys.forumV2Threads(subforumId, sort, q, tag),
        queryFn: async () => {
            const res = await api.getForumV2Threads(subforumId, { sort, q, tag, limit: 30, offset: 0 });
            return res ?? { threads: [], total: 0, subforum: null };
        },
        enabled: !!subforumId,
        placeholderData: keepPreviousData,
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useForumV2PostsQuery(args: { threadId: string; sort: 'new' | 'top' }) {
    const { threadId, sort } = args;
    return useQuery({
        queryKey: queryKeys.forumV2Posts(threadId, sort),
        queryFn: async () => {
            const res = await api.getForumV2Posts(threadId, { sort, limit: 80, offset: 0 });
            return res ?? { posts: [], total: 0, thread: null };
        },
        enabled: !!threadId,
        placeholderData: keepPreviousData,
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useForumV2NotificationsQuery(unreadOnly: boolean) {
    return useQuery({
        queryKey: queryKeys.forumV2Notifications(unreadOnly),
        queryFn: async () => {
            const res = await api.getForumV2Notifications({ unread_only: unreadOnly, limit: 80, offset: 0 });
            return res?.notifications ?? [];
        },
        staleTime: STALE_FORUM_V2_MS,
    });
}

export function useChatHistoryQuery(conversationId?: string | null) {
    // When `conversationId` is undefined the backend returns the user's most-recent
    // thread (matches legacy single-thread behavior). When it's a specific id, the
    // history is scoped to that thread.
    return useQuery({
        queryKey: conversationId
            ? queryKeys.chatHistoryByConv(conversationId)
            : queryKeys.chatHistory,
        queryFn: async () => {
            const { messages, conversation_id } = await api.getChatHistory({
                limit: 80,
                offset: 0,
                conversationId: conversationId ?? null,
            });
            return { messages: messages ?? [], conversationId: conversation_id ?? null };
        },
        staleTime: STALE_CHAT_HISTORY_MS,
    });
}


export function useChatConversationsQuery() {
    return useQuery({
        queryKey: queryKeys.chatConversations,
        queryFn: async () => {
            const { conversations } = await api.listChatConversations({ limit: 100 });
            return conversations ?? [];
        },
        staleTime: 30 * 1000,
    });
}
