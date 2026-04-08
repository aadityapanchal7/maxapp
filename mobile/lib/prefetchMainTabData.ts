import type { QueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { queryKeys } from './queryClient';

/** Warm cache for all main-tab endpoints so switching tabs feels instant. */
export function prefetchMainTabData(qc: QueryClient): void {
    void qc.prefetchQuery({
        queryKey: queryKeys.maxes,
        queryFn: () => api.getMaxxes(),
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.schedulesActiveFull,
        queryFn: () => api.getActiveSchedulesFull(),
    });
    // v2 forums (categories + subforums) — primary Forums tab
    void qc.prefetchQuery({
        queryKey: queryKeys.forumV2Categories,
        queryFn: async () => {
            const res = await api.getForumV2Categories();
            return res?.categories ?? [];
        },
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.forumV2Subforums(null),
        queryFn: async () => {
            const res = await api.getForumV2Subforums();
            return res?.subforums ?? [];
        },
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.chatHistory,
        queryFn: async () => {
            const { messages } = await api.getChatHistory({ limit: 80, offset: 0 });
            return messages ?? [];
        },
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.activeSchedulesSummary,
        queryFn: () => api.getActiveSchedules(),
    });
}
