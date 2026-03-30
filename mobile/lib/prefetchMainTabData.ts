import type { QueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { queryKeys } from './queryClient';

/** Warm cache for all main-tab endpoints so switching tabs feels instant. */
export function prefetchMainTabData(qc: QueryClient): void {
    void qc.prefetchQuery({
        queryKey: queryKeys.maxes,
        queryFn: () => api.getMaxxes(),
    }).then((res: any) => {
        const maxes: any[] = res?.maxes ?? [];
        for (const m of maxes) {
            const id = m?.id;
            if (!id) continue;
            void qc.prefetchQuery({
                queryKey: queryKeys.maxx(id),
                queryFn: () => api.getMaxx(id),
            });
            void qc.prefetchQuery({
                queryKey: queryKeys.maxxSchedule(id),
                queryFn: () => api.getMaxxSchedule(id),
            });
        }
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.schedulesActiveFull,
        queryFn: () => api.getActiveSchedulesFull(),
    });
    void qc.prefetchQuery({
        queryKey: queryKeys.channels(''),
        queryFn: async () => {
            const res = await api.getChannels('', { limit: 200, offset: 0 });
            return res?.forums ?? [];
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
