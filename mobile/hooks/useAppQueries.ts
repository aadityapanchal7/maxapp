import { keepPreviousData, useQuery } from '@tanstack/react-query';
import api from '../services/api';
import { queryKeys } from '../lib/queryClient';

const STALE_MAXXES_MS = 5 * 60 * 1000;
const STALE_SCHEDULES_FULL_MS = 60 * 1000;
const STALE_CHANNELS_MS = 2 * 60 * 1000;
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

export function useChatHistoryQuery() {
    return useQuery({
        queryKey: queryKeys.chatHistory,
        queryFn: async () => {
            const { messages } = await api.getChatHistory({ limit: 80, offset: 0 });
            return messages ?? [];
        },
        staleTime: STALE_CHAT_HISTORY_MS,
    });
}
