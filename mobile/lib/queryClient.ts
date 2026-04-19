import { QueryClient } from '@tanstack/react-query';

/** Shared server-state cache: avoids duplicate maxes / schedule fetches across Home + Master Schedule. */
export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            // 5min staleTime: most screens don't need sub-minute freshness, and this
            // cuts focus-refetch storms when users tab between screens.
            staleTime: 5 * 60 * 1000,
            gcTime: 30 * 60 * 1000,
            // Don't retry auth errors (401/403) — the axios interceptor already tried
            // a refresh; retrying here just multiplies the request storm when the
            // session is permanently dead.
            retry: (failureCount, error) => {
                const status = (error as any)?.response?.status;
                if (status === 401 || status === 403) return false;
                return failureCount < 2;
            },
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
            // Don't auto-refetch on mount if data is fresh — trust the cache.
            refetchOnMount: false,
            refetchOnWindowFocus: false,
            // RN: reconnect refetch is the only auto-refresh we want.
            refetchOnReconnect: true,
        },
    },
});

export const queryKeys = {
    maxes: ['maxes'] as const,
    schedulesActiveFull: ['schedules', 'active', 'full'] as const,
    maxx: (id: string) => ['maxx', id] as const,
    maxxSchedule: (id: string) => ['maxxSchedule', id] as const,
    activeSchedulesSummary: ['activeSchedules', 'summary'] as const,
    /** Forums channel list; `q` is trimmed search (empty = full list). */
    channels: (q: string) => ['channels', q] as const,
    forumV2Categories: ['forumV2', 'categories'] as const,
    forumV2Subforums: (categoryId: string | null) => ['forumV2', 'subforums', categoryId ?? 'all'] as const,
    forumV2Threads: (subforumId: string, sort: string, q: string, tag: string) =>
        ['forumV2', 'threads', subforumId, sort, q, tag] as const,
    forumV2Posts: (threadId: string, sort: string) => ['forumV2', 'posts', threadId, sort] as const,
    forumV2Search: (q: string) => ['forumV2', 'search', q] as const,
    forumV2Notifications: (unreadOnly: boolean) => ['forumV2', 'notifications', unreadOnly ? 'unread' : 'all'] as const,
    chatHistory: ['chat', 'history'] as const,
};
