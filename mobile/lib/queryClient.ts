import { QueryClient } from '@tanstack/react-query';

/** Shared server-state cache: avoids duplicate maxes / schedule fetches across Home + Master Schedule. */
export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 90 * 1000,
            gcTime: 10 * 60 * 1000,
            retry: 1,
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
