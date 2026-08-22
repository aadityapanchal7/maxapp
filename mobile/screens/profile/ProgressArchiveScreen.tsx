import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    useWindowDimensions,
    Platform,
    ActivityIndicator,
    ScrollView,
    Modal,
    Pressable,
} from 'react-native'
import { Alert, InAppAlertHost } from '../../components/InAppAlert';
import { useNavigation } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';
import api from '../../services/api';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { CachedImage } from '../../components/CachedImage';
import { colors, spacing, borderRadius, fonts } from '../../theme/dark';
import { formatFaceRatingLabel } from '../../utils/faceRatingLabel';

// ─── helpers ────────────────────────────────────────────────────────────────

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];
const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function toDateKey(date: Date): string {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function buildCalendarDays(year: number, month: number): (number | null)[] {
    const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const days: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let d = 1; d <= daysInMonth; d++) days.push(d);
    while (days.length % 7 !== 0) days.push(null);
    return days;
}

function scoreAccentColor(score: number | null | undefined): string {
    if (score == null || !Number.isFinite(score)) return colors.textMuted;
    if (score >= 8) return '#D4A017';
    if (score >= 6.5) return '#4A9EFF';
    if (score >= 5) return '#E8804A';
    return '#E05050';
}

function formatProgressDate(dateStr: string): string {
    const d = new Date(dateStr);
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const day = d.getDate();
    const suffix = day === 1 || day === 21 || day === 31 ? 'st' : day === 2 || day === 22 ? 'nd' : day === 3 || day === 23 ? 'rd' : 'th';
    return `${months[d.getMonth()]} ${day}${suffix} ${d.getFullYear()}`;
}

function formatShortDate(dateStr: string): string {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear().toString().slice(2)}`;
}

function getScoreColor(score: number) {
    if (score >= 7) return colors.foreground;
    if (score >= 5) return '#E8804A';
    return '#E05050';
}

const getImageWidth = (width: number) =>
    Platform.OS === 'web' && width > 600
        ? Math.min(width - 96, 480)
        : Math.min(width - 48, 340);

// ─── component ──────────────────────────────────────────────────────────────

export default function ProgressArchiveScreen() {
    const navigation = useNavigation<any>();
    const queryClient = useQueryClient();
    const { width: winWidth } = useWindowDimensions();
    const insets = useSafeAreaInsets();

    const [photos, setPhotos] = useState<any[]>([]);
    const [scanHistory, setScanHistory] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    // calendar nav
    const today = new Date();
    const [calYear, setCalYear] = useState(today.getFullYear());
    const [calMonth, setCalMonth] = useState(today.getMonth());

    // viewer
    const [viewerVisible, setViewerVisible] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [expandedScan, setExpandedScan] = useState<any>(null);
    const [statsExpanded, setStatsExpanded] = useState(false);
    const [loadingScan, setLoadingScan] = useState(false);

    // compare
    const [compareMode, setCompareMode] = useState(false);
    const [comparePicks, setComparePicks] = useState<[number | null, number | null]>([null, null]);
    const [compareVisible, setCompareVisible] = useState(false);

    const imageWidth = getImageWidth(winWidth);
    const compareImageWidth = Math.floor((winWidth - 64) / 2);

    // horizontal padding so calendar fits nicely
    const CAL_H_PAD = 16;
    const cellSize = Math.floor((winWidth - CAL_H_PAD * 2) / 7);

    useEffect(() => { void loadPhotos(); }, []);

    const loadPhotos = async () => {
        try {
            const [photosRes, scansRes] = await Promise.all([
                api.getProgressPhotos().catch(() => ({ photos: [] })),
                api.getScanHistory().catch(() => ({ scans: [] })),
            ]);
            setPhotos(photosRes.photos || []);
            setScanHistory(scansRes.scans || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    // photos sorted newest-first for viewer nav
    const displayPhotos = useMemo(() =>
        [...photos].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
        [photos],
    );

    // map 'YYYY-MM-DD' → best (most recent) photo for that day
    const photoByDate = useMemo(() => {
        const map: Record<string, any> = {};
        for (const p of displayPhotos) {
            const key = toDateKey(new Date(p.created_at));
            if (!map[key]) map[key] = p;
        }
        return map;
    }, [displayPhotos]);

    // map photo id → nearest scan id (within 5 min)
    const photoScanMap = useMemo(() => {
        const map: Record<string, string> = {};
        for (const photo of photos) {
            const pTime = new Date(photo.created_at).getTime();
            let best: any = null, bestDiff = Infinity;
            for (const scan of scanHistory) {
                const diff = Math.abs(new Date(scan.created_at).getTime() - pTime);
                if (diff < bestDiff) { bestDiff = diff; best = scan; }
            }
            if (best && bestDiff < 5 * 60 * 1000) map[photo.id] = best.id;
        }
        return map;
    }, [photos, scanHistory]);

    // calendar days for current view
    const calDays = useMemo(() => buildCalendarDays(calYear, calMonth), [calYear, calMonth]);

    // month with photos count
    const monthPhotoCount = useMemo(() => {
        const prefix = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-`;
        return Object.keys(photoByDate).filter(k => k.startsWith(prefix)).length;
    }, [photoByDate, calYear, calMonth]);

    const prevMonth = () => {
        if (calMonth === 0) { setCalYear(y => y - 1); setCalMonth(11); }
        else setCalMonth(m => m - 1);
    };
    const nextMonth = () => {
        if (calMonth === 11) { setCalYear(y => y + 1); setCalMonth(0); }
        else setCalMonth(m => m + 1);
    };

    const openViewer = (photo: any) => {
        const idx = displayPhotos.findIndex(p => p.id === photo.id);
        setSelectedIndex(idx >= 0 ? idx : 0);
        setStatsExpanded(false);
        setExpandedScan(null);
        setViewerVisible(true);
    };

    const handleDayPress = (day: number) => {
        const key = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const photo = photoByDate[key];
        if (!photo) return;
        if (!compareMode) {
            openViewer(photo);
            return;
        }
        const idx = displayPhotos.findIndex(p => p.id === photo.id);
        if (idx < 0) return;
        setComparePicks(prev => {
            if (prev[0] === idx) return [null, prev[1]];
            if (prev[1] === idx) return [prev[0], null];
            if (prev[0] === null) return [idx, prev[1]];
            return [prev[0], idx];
        });
    };

    useEffect(() => {
        if (comparePicks[0] !== null && comparePicks[1] !== null) setCompareVisible(true);
    }, [comparePicks]);

    const exitCompare = () => {
        setCompareMode(false);
        setComparePicks([null, null]);
        setCompareVisible(false);
    };

    const fetchScanDetails = useCallback(async (scanId: string) => {
        setLoadingScan(true);
        try { setExpandedScan(await api.getScanById(scanId)); }
        catch { setExpandedScan(null); }
        finally { setLoadingScan(false); }
    }, []);

    const getRatingDelta = useCallback((currentPhoto: any): { text: string; color: string } | null => {
        if (currentPhoto?.face_rating == null || !Number.isFinite(Number(currentPhoto.face_rating))) return null;
        const currentDate = new Date(currentPhoto.created_at).getTime();
        const earlier = photos
            .filter(p => p.id !== currentPhoto.id && p.face_rating != null && Number.isFinite(Number(p.face_rating)) && new Date(p.created_at).getTime() < currentDate)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        if (!earlier.length) return null;
        const delta = Number(currentPhoto.face_rating) - Number(earlier[0].face_rating);
        if (delta > 0) return { text: `+${delta.toFixed(1)}`, color: '#4A9EFF' };
        if (delta < 0) return { text: delta.toFixed(1), color: '#E05050' };
        return { text: '0.0', color: colors.textMuted };
    }, [photos]);

    const handleShare = async (photo: any) => {
        if (!photo?.image_url) return;
        try {
            const url = api.resolveAttachmentUrl(photo.image_url);
            if (!url) return;
            if (Platform.OS === 'web') {
                if (typeof navigator !== 'undefined' && (navigator as any).share) {
                    await (navigator as any).share({ url });
                }
                return;
            }
            const dest = new FileSystem.File(FileSystem.Paths.cache, `progress_${photo.id}.jpg`);
            const downloaded = await FileSystem.File.downloadFileAsync(url, dest, { idempotent: true });
            if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(downloaded.uri);
            else Alert.alert('Sharing not available on this device');
        } catch { Alert.alert('Error', 'Could not share photo.'); }
    };

    const deletePhoto = (index: number) => {
        const photo = displayPhotos[index];
        if (!photo) return;
        Alert.alert('Delete photo', 'Delete this progress photo?', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Delete', style: 'destructive',
                onPress: async () => {
                    try {
                        await api.deleteProgressPhoto(photo.id);
                        const updated = photos.filter(p => p.id !== photo.id);
                        setPhotos(updated);
                        if (updated.length === 0) setViewerVisible(false);
                        else setSelectedIndex(prev => Math.min(prev, updated.length - 1));
                        // ProfileScreen caches the same grid under this key with
                        // no focus-refetch — without invalidating, the deleted
                        // photo kept showing there until staleTime lapsed.
                        void queryClient.invalidateQueries({ queryKey: queryKeys.profileProgressPhotos });
                    } catch { Alert.alert('Error', 'Could not delete photo.'); }
                },
            },
        ]);
    };

    // ─── loading ──────────────────────────────────────────────────────────
    if (loading) {
        return (
            <View style={[s.root, { paddingTop: insets.top }]}>
                <View style={s.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={s.backBtn} activeOpacity={0.7}>
                        <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={s.title}>Progress</Text>
                    <View style={{ width: 40 }} />
                </View>
                <View style={s.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            </View>
        );
    }

    const currentViewerPhoto = displayPhotos[selectedIndex];
    const delta = currentViewerPhoto ? getRatingDelta(currentViewerPhoto) : null;
    const todayKey = toDateKey(today);

    // ─── main render ──────────────────────────────────────────────────────
    return (
        <View style={[s.root, { paddingTop: insets.top }]}>
            {/* Header */}
            <View style={s.header}>
                <TouchableOpacity
                    onPress={() => { if (compareMode) exitCompare(); else navigation.goBack(); }}
                    style={s.backBtn}
                    activeOpacity={0.7}
                >
                    <Ionicons name={compareMode ? 'close' : 'arrow-back'} size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={s.title}>{compareMode ? 'Select 2 photos' : 'Progress'}</Text>
                <View style={s.headerRight}>
                    {!compareMode && photos.length >= 2 && (
                        <TouchableOpacity onPress={() => setCompareMode(true)} style={s.iconBtn} activeOpacity={0.7}>
                            <Ionicons name="git-compare-outline" size={20} color={colors.foreground} />
                        </TouchableOpacity>
                    )}
                    {compareMode && (
                        <TouchableOpacity onPress={exitCompare} style={s.iconBtn} activeOpacity={0.7}>
                            <Text style={s.cancelText}>Cancel</Text>
                        </TouchableOpacity>
                    )}
                </View>
            </View>

            <ScrollView
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}
            >
                {/* Month nav */}
                <View style={s.monthNav}>
                    <TouchableOpacity onPress={prevMonth} style={s.monthArrow} activeOpacity={0.7}>
                        <Ionicons name="chevron-back" size={18} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={s.monthLabel}>
                        {MONTH_NAMES[calMonth]} {calYear}
                    </Text>
                    <TouchableOpacity onPress={nextMonth} style={s.monthArrow} activeOpacity={0.7}>
                        <Ionicons name="chevron-forward" size={18} color={colors.foreground} />
                    </TouchableOpacity>
                </View>

                {/* Day-of-week labels */}
                <View style={[s.dayLabels, { paddingHorizontal: CAL_H_PAD }]}>
                    {DAY_LABELS.map(d => (
                        <Text key={d} style={[s.dayLabel, { width: cellSize }]}>{d}</Text>
                    ))}
                </View>

                {/* Calendar grid */}
                <View style={[s.grid, { paddingHorizontal: CAL_H_PAD }]}>
                    {calDays.map((day, i) => {
                        if (day === null) {
                            return <View key={`pad-${i}`} style={{ width: cellSize, height: cellSize + 6 }} />;
                        }

                        const dayKey = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                        const photo = photoByDate[dayKey];
                        const isToday = dayKey === todayKey;

                        // compare pick check
                        const pickIdx = photo ? displayPhotos.findIndex(p => p.id === photo.id) : -1;
                        const isPick1 = compareMode && pickIdx >= 0 && comparePicks[0] === pickIdx;
                        const isPick2 = compareMode && pickIdx >= 0 && comparePicks[1] === pickIdx;
                        const isComparePicked = isPick1 || isPick2;

                        const accent = photo ? scoreAccentColor(photo.face_rating) : null;

                        return (
                            <TouchableOpacity
                                key={dayKey}
                                style={[s.cell, { width: cellSize, height: cellSize + 6 }]}
                                onPress={() => handleDayPress(day)}
                                activeOpacity={photo ? 0.85 : 1}
                                disabled={!photo && !compareMode}
                            >
                                <View style={[
                                    s.cellInner,
                                    { width: cellSize - 4, height: cellSize - 4 },
                                    photo ? s.cellWithPhoto : s.cellEmpty,
                                    isToday && !photo && s.cellToday,
                                    isComparePicked && s.cellCompareSelected,
                                ]}>
                                    {photo ? (
                                        <CachedImage
                                            uri={api.resolveAttachmentUrl(photo.image_url)}
                                            style={[s.cellImg, { width: cellSize - 4, height: cellSize - 4 }]}
                                            contentFit="cover"
                                        />
                                    ) : null}

                                    {/* Day number */}
                                    <Text style={[
                                        s.cellDay,
                                        photo ? s.cellDayOnPhoto : s.cellDayEmpty,
                                        isToday && !photo && s.cellDayToday,
                                    ]}>
                                        {day}
                                    </Text>

                                    {/* Compare badge */}
                                    {isComparePicked && (
                                        <View style={s.compareBadge}>
                                            <Text style={s.compareBadgeText}>{isPick1 ? '1' : '2'}</Text>
                                        </View>
                                    )}
                                </View>

                                {/* Score accent bar */}
                                {accent && (
                                    <View style={[s.accentBar, { backgroundColor: accent }]} />
                                )}
                            </TouchableOpacity>
                        );
                    })}
                </View>

                {/* Stats section */}
                <View style={s.statsSection}>
                    <View style={s.statsHeader}>
                        <Text style={s.statsTitle}>Stats</Text>
                        <Text style={s.statsCount}>{monthPhotoCount}</Text>
                    </View>
                    {monthPhotoCount > 0 ? (
                        <>
                            <View style={s.statRow}>
                                <Text style={s.statLabel}>This month</Text>
                                <Text style={s.statValue}>{monthPhotoCount} photo{monthPhotoCount !== 1 ? 's' : ''}</Text>
                            </View>
                            <View style={[s.statBar, { width: '100%' }]}>
                                <View style={[s.statBarFill, { width: `${Math.min(100, (monthPhotoCount / 30) * 100)}%` }]} />
                            </View>
                            <View style={s.statRow}>
                                <Text style={s.statLabel}>All time</Text>
                                <Text style={s.statValue}>{photos.length} photo{photos.length !== 1 ? 's' : ''}</Text>
                            </View>
                        </>
                    ) : (
                        <Text style={s.statsEmpty}>No photos this month</Text>
                    )}
                </View>
            </ScrollView>

            {/* ── Full-screen viewer modal ─────────────────────────────── */}
            <Modal animationType="fade" transparent visible={viewerVisible} onRequestClose={() => setViewerVisible(false)}>
                <Pressable style={s.viewerOverlay} onPress={() => setViewerVisible(false)}>
                    <ScrollView contentContainerStyle={s.viewerScrollContent} showsVerticalScrollIndicator={false}>
                        <Pressable style={[s.viewerContent, { width: imageWidth + spacing.lg * 2 }]} onPress={() => {}}>
                            <TouchableOpacity style={s.viewerClose} onPress={() => setViewerVisible(false)} activeOpacity={0.7}>
                                <Ionicons name="close" size={22} color={colors.foreground} />
                            </TouchableOpacity>

                            {currentViewerPhoto && (
                                <View style={[s.imageBox, { width: imageWidth, height: imageWidth * (4 / 3) }]}>
                                    <CachedImage
                                        uri={api.resolveAttachmentUrl(currentViewerPhoto.image_url)}
                                        style={[s.slideImage, { width: imageWidth, height: imageWidth * (4 / 3) }]}
                                        contentFit="contain"
                                    />
                                    {currentViewerPhoto.face_rating != null && Number.isFinite(Number(currentViewerPhoto.face_rating)) && (
                                        <View style={s.viewerRatingRow}>
                                            <Text style={s.viewerRatingBadge}>
                                                {formatFaceRatingLabel(Number(currentViewerPhoto.face_rating))}
                                            </Text>
                                            {delta && (
                                                <Text style={[s.viewerDeltaBadge, { color: delta.color }]}>
                                                    ({delta.text})
                                                </Text>
                                            )}
                                        </View>
                                    )}
                                </View>
                            )}

                            {currentViewerPhoto && (
                                <Text style={s.dateText}>{formatProgressDate(currentViewerPhoto.created_at)}</Text>
                            )}

                            {currentViewerPhoto && photoScanMap[currentViewerPhoto.id] && (
                                <View style={s.scanStatsSection}>
                                    <TouchableOpacity
                                        style={s.expandStatsBtn}
                                        activeOpacity={0.7}
                                        onPress={() => {
                                            if (statsExpanded) { setStatsExpanded(false); return; }
                                            const scanId = photoScanMap[currentViewerPhoto.id];
                                            if (expandedScan?.id === scanId) { setStatsExpanded(true); return; }
                                            setStatsExpanded(true);
                                            void fetchScanDetails(scanId);
                                        }}
                                    >
                                        <Ionicons name={statsExpanded ? 'chevron-up' : 'analytics-outline'} size={16} color={colors.foreground} />
                                        <Text style={s.expandStatsBtnText}>
                                            {statsExpanded ? 'Hide scan details' : 'View scan details'}
                                        </Text>
                                    </TouchableOpacity>

                                    {statsExpanded && (
                                        loadingScan ? (
                                            <ActivityIndicator color={colors.foreground} style={{ marginTop: spacing.sm }} />
                                        ) : expandedScan?.analysis ? (
                                            <View style={s.scanStatsGrid}>
                                                {(() => {
                                                    const pr = expandedScan.analysis?.psl_rating || {};
                                                    const pi = expandedScan.analysis?.profile_insights;
                                                    const tier = typeof pr.psl_tier === 'string' ? pr.psl_tier.trim() : '';
                                                    const appeal = typeof pr.appeal === 'number' ? pr.appeal : parseFloat(String(pr.appeal || ''));
                                                    const arch = (typeof pr.archetype === 'string' ? pr.archetype.trim() : '') || (typeof pi?.archetype === 'string' ? pi.archetype.trim() : '');
                                                    const ascMonths = typeof pr.ascension_time_months === 'number' ? pr.ascension_time_months : parseInt(String(pr.ascension_time_months || '0'), 10) || 0;
                                                    const ageSc = typeof pr.age_score === 'number' ? pr.age_score : parseInt(String(pr.age_score || '0'), 10) || 0;
                                                    const potential = typeof pr.potential === 'number' ? pr.potential : parseFloat(String(pr.potential || ''));
                                                    const mogPct = typeof pr.mog_percentile === 'number' ? pr.mog_percentile : null;
                                                    const glowUp = typeof pr.glow_up_potential === 'number' ? pr.glow_up_potential : null;
                                                    const weakest = typeof pr.weakest_link === 'string' ? pr.weakest_link.trim() : '';
                                                    const auraTags: string[] = Array.isArray(pr.aura_tags) ? pr.aura_tags : [];
                                                    const featureScores = pr.feature_scores || {};
                                                    return (
                                                        <>
                                                            {tier ? <ScanRow label="Tier" value={tier} /> : null}
                                                            {!Number.isNaN(appeal) ? <ScanRow label="Appeal" value={`${appeal.toFixed(1)}/10`} score={appeal} /> : null}
                                                            {!Number.isNaN(potential) ? <ScanRow label="Potential" value={`${potential.toFixed(1)}/10`} score={potential} /> : null}
                                                            {arch ? <ScanRow label="Archetype" value={arch} /> : null}
                                                            {ascMonths > 0 ? <ScanRow label="Ascension time" value={`${ascMonths} months`} /> : null}
                                                            {ageSc > 0 ? <ScanRow label="Facial age" value={String(ageSc)} /> : null}
                                                            {mogPct !== null ? <ScanRow label="Mog percentile" value={`${mogPct}%`} /> : null}
                                                            {glowUp !== null ? <ScanRow label="Glow-up potential" value={`${glowUp.toFixed(1)}/10`} score={glowUp} /> : null}
                                                            {weakest ? <ScanRow label="Weakest link" value={weakest} /> : null}
                                                            {auraTags.length > 0 ? <ScanRow label="Aura tags" value={auraTags.join(', ')} /> : null}
                                                            {Object.keys(featureScores).length > 0 && (
                                                                <>
                                                                    <Text style={s.featureScoresHeader}>Feature Scores</Text>
                                                                    {Object.entries(featureScores).map(([key, val]: [string, any]) => {
                                                                        const sc = typeof val?.score === 'number' ? val.score : null;
                                                                        const tag = typeof val?.tag === 'string' ? val.tag : '';
                                                                        const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                                                                        return (
                                                                            <View key={key} style={s.featureRow}>
                                                                                <Text style={s.featureLabel}>{label}</Text>
                                                                                <View style={s.featureRight}>
                                                                                    {sc !== null && <Text style={[s.featureScore, { color: getScoreColor(sc) }]}>{sc.toFixed(1)}</Text>}
                                                                                    {tag ? <Text style={s.featureTag}>{tag}</Text> : null}
                                                                                </View>
                                                                            </View>
                                                                        );
                                                                    })}
                                                                </>
                                                            )}
                                                        </>
                                                    );
                                                })()}
                                            </View>
                                        ) : null
                                    )}
                                </View>
                            )}

                            <View style={s.actionRow}>
                                <TouchableOpacity style={s.actionBtn} onPress={() => void handleShare(currentViewerPhoto)} activeOpacity={0.7}>
                                    <Ionicons name="share-outline" size={18} color={colors.foreground} />
                                    <Text style={s.actionBtnText}>Share</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={s.actionBtn} onPress={() => deletePhoto(selectedIndex)} activeOpacity={0.7}>
                                    <Ionicons name="trash-outline" size={18} color="#E05050" />
                                    <Text style={[s.actionBtnText, { color: '#E05050' }]}>Delete</Text>
                                </TouchableOpacity>
                            </View>

                            {displayPhotos.length > 1 && (
                                <View style={[s.navRow, { width: imageWidth }]}>
                                    <TouchableOpacity
                                        style={[s.navButton, selectedIndex === 0 && s.navButtonDisabled]}
                                        onPress={() => { setSelectedIndex(p => Math.max(0, p - 1)); setStatsExpanded(false); setExpandedScan(null); }}
                                        disabled={selectedIndex === 0} activeOpacity={0.7}
                                    >
                                        <Ionicons name="chevron-back" size={22} color={selectedIndex === 0 ? colors.textMuted : colors.foreground} />
                                        <Text style={[s.navText, selectedIndex === 0 && s.navTextDisabled]}>Prev</Text>
                                    </TouchableOpacity>
                                    <Text style={s.counterText}>{selectedIndex + 1} / {displayPhotos.length}</Text>
                                    <TouchableOpacity
                                        style={[s.navButton, selectedIndex >= displayPhotos.length - 1 && s.navButtonDisabled]}
                                        onPress={() => { setSelectedIndex(p => Math.min(displayPhotos.length - 1, p + 1)); setStatsExpanded(false); setExpandedScan(null); }}
                                        disabled={selectedIndex >= displayPhotos.length - 1} activeOpacity={0.7}
                                    >
                                        <Text style={[s.navText, selectedIndex >= displayPhotos.length - 1 && s.navTextDisabled]}>Next</Text>
                                        <Ionicons name="chevron-forward" size={22} color={selectedIndex >= displayPhotos.length - 1 ? colors.textMuted : colors.foreground} />
                                    </TouchableOpacity>
                                </View>
                            )}
                        </Pressable>
                    </ScrollView>
                </Pressable>
                {/* Host an alert layer INSIDE this viewer modal so the delete-photo
                    confirm (Alert.alert in deletePhoto) renders ABOVE it — a
                    root-level host's modal would present BEHIND this one, making the
                    confirm dialog invisible and the Delete button appear dead. */}
                <InAppAlertHost />
            </Modal>

            {/* ── Compare modal ──────────────────────────────────────────── */}
            <Modal animationType="fade" transparent visible={compareVisible} onRequestClose={() => setCompareVisible(false)}>
                <Pressable style={s.viewerOverlay} onPress={() => setCompareVisible(false)}>
                    <Pressable style={s.compareContent} onPress={() => {}}>
                        <TouchableOpacity style={s.viewerClose} onPress={() => { setCompareVisible(false); exitCompare(); }} activeOpacity={0.7}>
                            <Ionicons name="close" size={22} color={colors.foreground} />
                        </TouchableOpacity>
                        <Text style={s.compareTitle}>Compare</Text>
                        <View style={s.compareSideBySide}>
                            {[comparePicks[0], comparePicks[1]].map((pickIdx, i) => {
                                const photo = pickIdx !== null ? displayPhotos[pickIdx] : null;
                                if (!photo) return <View key={i} style={[s.compareSlot, { width: compareImageWidth }]} />;
                                const hasRating = photo.face_rating != null && Number.isFinite(Number(photo.face_rating));
                                return (
                                    <View key={i} style={[s.compareSlot, { width: compareImageWidth }]}>
                                        <View style={[s.compareImageBox, { width: compareImageWidth, height: compareImageWidth * (4 / 3) }]}>
                                            <CachedImage
                                                uri={api.resolveAttachmentUrl(photo.image_url)}
                                                style={{ width: compareImageWidth, height: compareImageWidth * (4 / 3) }}
                                                contentFit="cover"
                                            />
                                        </View>
                                        <Text style={s.compareDate}>{formatShortDate(photo.created_at)}</Text>
                                        {hasRating && <Text style={s.compareRating}>{formatFaceRatingLabel(Number(photo.face_rating))}</Text>}
                                    </View>
                                );
                            })}
                        </View>
                        {comparePicks[0] !== null && comparePicks[1] !== null && (() => {
                            const p1 = displayPhotos[comparePicks[0]!];
                            const p2 = displayPhotos[comparePicks[1]!];
                            if (!p1 || !p2) return null;
                            const r1 = Number(p1.face_rating), r2 = Number(p2.face_rating);
                            if (!Number.isFinite(r1) || !Number.isFinite(r2)) return null;
                            const diff = r2 - r1;
                            return (
                                <Text style={[s.compareDelta, { color: diff > 0 ? '#4A9EFF' : diff < 0 ? '#E05050' : colors.textMuted }]}>
                                    {diff > 0 ? '+' : ''}{diff.toFixed(1)} rating change
                                </Text>
                            );
                        })()}
                    </Pressable>
                </Pressable>
            </Modal>
        </View>
    );
}

// ─── small helpers ───────────────────────────────────────────────────────────

function ScanRow({ label, value, score }: { label: string; value: string; score?: number }) {
    const col = score != null ? getScoreColor(score) : colors.foreground;
    return (
        <View style={s.scanStatRow}>
            <Text style={s.scanStatLabel}>{label}</Text>
            <Text style={[s.scanStatValue, { color: col }]}>{value}</Text>
        </View>
    );
}

// ─── styles ──────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },

    // header
    header: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        paddingHorizontal: 16, paddingBottom: 10, paddingTop: 8,
    },
    backBtn: {
        width: 38, height: 38, borderRadius: 19,
        backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
        alignItems: 'center', justifyContent: 'center',
    },
    title: { fontFamily: fonts.serif, fontSize: 22, fontWeight: '400', color: colors.foreground },
    headerRight: { flexDirection: 'row', alignItems: 'center', minWidth: 38 },
    iconBtn: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
    cancelText: { fontSize: 14, fontWeight: '500', color: '#E05050' },

    // month nav
    monthNav: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        paddingHorizontal: 16, marginTop: 4, marginBottom: 12,
    },
    monthArrow: {
        width: 36, height: 36, borderRadius: 18,
        backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
        alignItems: 'center', justifyContent: 'center',
    },
    monthLabel: {
        fontFamily: fonts.serif, fontSize: 17, fontWeight: '600', color: colors.foreground,
    },

    // day labels
    dayLabels: { flexDirection: 'row', marginBottom: 6 },
    dayLabel: {
        textAlign: 'center', fontSize: 11, fontWeight: '600',
        color: colors.textMuted, letterSpacing: 0.4,
    },

    // calendar grid
    grid: { flexDirection: 'row', flexWrap: 'wrap' },
    cell: { alignItems: 'center', paddingBottom: 2 },
    cellInner: {
        borderRadius: 10, overflow: 'hidden',
        backgroundColor: colors.card, borderWidth: 1, borderColor: colors.borderLight,
        position: 'relative',
    },
    cellEmpty: { backgroundColor: colors.card },
    cellWithPhoto: { borderColor: 'transparent', borderWidth: 0 },
    cellToday: { borderColor: colors.foreground, borderWidth: 1.5 },
    cellCompareSelected: { borderWidth: 2.5, borderColor: '#4A9EFF', borderRadius: 10 },
    cellImg: { position: 'absolute', top: 0, left: 0, borderRadius: 10 },

    // day number overlay
    cellDay: {
        position: 'absolute', top: 5, left: 6,
        fontSize: 12, fontWeight: '700', zIndex: 2,
    },
    cellDayEmpty: { color: colors.foreground },
    cellDayOnPhoto: {
        color: '#fff',
        textShadowColor: 'rgba(0,0,0,0.7)',
        textShadowOffset: { width: 0, height: 1 },
        textShadowRadius: 3,
    },
    cellDayToday: { color: colors.foreground },

    // compare badge
    compareBadge: {
        position: 'absolute', top: 4, right: 4, zIndex: 3,
        width: 18, height: 18, borderRadius: 9,
        backgroundColor: '#4A9EFF', alignItems: 'center', justifyContent: 'center',
    },
    compareBadgeText: { fontSize: 10, fontWeight: '700', color: '#fff' },

    // score accent bar
    accentBar: { height: 3, width: '70%', borderRadius: 2, marginTop: 2 },

    // stats
    statsSection: {
        marginTop: 24, marginHorizontal: 16,
        backgroundColor: colors.card, borderRadius: 16,
        borderWidth: 1, borderColor: colors.border, padding: 16,
    },
    statsHeader: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
    statsTitle: { fontFamily: fonts.serif, fontSize: 20, fontWeight: '600', color: colors.foreground },
    statsCount: { fontFamily: fonts.serif, fontSize: 28, fontWeight: '700', color: colors.foreground },
    statRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
    statLabel: { fontSize: 13, color: colors.textMuted, fontWeight: '500' },
    statValue: { fontSize: 13, color: colors.foreground, fontWeight: '600' },
    statBar: { height: 4, backgroundColor: colors.border, borderRadius: 2, marginBottom: 12 },
    statBarFill: { height: 4, backgroundColor: colors.foreground, borderRadius: 2 },
    statsEmpty: { color: colors.textMuted, fontSize: 13, textAlign: 'center', paddingVertical: 8 },

    // loading
    loadingWrap: { flex: 1, justifyContent: 'center', alignItems: 'center' },

    // viewer modal
    viewerOverlay: {
        flex: 1, backgroundColor: 'rgba(0,0,0,0.55)',
        justifyContent: 'center', alignItems: 'center', padding: spacing.lg,
    },
    viewerScrollContent: { flexGrow: 1, justifyContent: 'center', alignItems: 'center' },
    viewerContent: {
        backgroundColor: colors.card, borderRadius: borderRadius.xl,
        padding: spacing.lg, alignItems: 'center',
        borderWidth: 1, borderColor: colors.border,
    },
    viewerClose: {
        position: 'absolute', top: spacing.md, right: spacing.md, zIndex: 10,
        width: 38, height: 38, borderRadius: 19,
        backgroundColor: colors.card, alignItems: 'center', justifyContent: 'center',
        borderWidth: 1, borderColor: colors.border,
    },
    imageBox: {
        position: 'relative', borderRadius: borderRadius.lg,
        borderWidth: 1, borderColor: colors.border,
        backgroundColor: colors.surface, overflow: 'hidden',
        alignItems: 'center', justifyContent: 'center',
    },
    viewerRatingRow: {
        position: 'absolute', bottom: 10, right: 10,
        flexDirection: 'row', alignItems: 'center', gap: 6,
    },
    viewerRatingBadge: {
        fontSize: 14, fontWeight: '800', color: '#fff',
        textShadowColor: 'rgba(0,0,0,0.85)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 4,
    },
    viewerDeltaBadge: {
        fontSize: 12, fontWeight: '700',
        textShadowColor: 'rgba(0,0,0,0.6)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 3,
    },
    slideImage: { borderRadius: borderRadius.lg },
    dateText: { marginTop: spacing.lg, fontSize: 20, fontWeight: '600', color: colors.foreground },
    actionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginTop: spacing.md },
    actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
    actionBtnText: { fontSize: 14, fontWeight: '500', color: colors.foreground },
    navRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: spacing.lg },
    navButton: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
    navButtonDisabled: { opacity: 0.5 },
    navText: { fontSize: 15, fontWeight: '600', color: colors.foreground },
    navTextDisabled: { color: colors.textMuted },
    counterText: { fontSize: 14, color: colors.textMuted },

    // scan details
    scanStatsSection: { width: '100%', marginTop: spacing.sm },
    expandStatsBtn: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
        gap: 6, paddingVertical: spacing.sm, paddingHorizontal: spacing.md,
        borderRadius: borderRadius.full, borderWidth: 1,
        borderColor: colors.border, backgroundColor: colors.surface,
    },
    expandStatsBtnText: { fontSize: 13, fontWeight: '600', color: colors.foreground },
    scanStatsGrid: {
        width: '100%', marginTop: spacing.sm, backgroundColor: colors.surface,
        borderRadius: borderRadius.lg, borderWidth: 1, borderColor: colors.border,
        padding: spacing.md, gap: spacing.xs,
    },
    scanStatRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4 },
    scanStatLabel: { fontSize: 12, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.3 },
    scanStatValue: { fontSize: 13, fontWeight: '700', color: colors.foreground, flexShrink: 1, textAlign: 'right', maxWidth: '60%' },
    featureScoresHeader: {
        fontSize: 11, fontWeight: '700', color: colors.textMuted, letterSpacing: 0.6,
        marginTop: spacing.sm, marginBottom: 2, textTransform: 'uppercase',
    },
    featureRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 3 },
    featureLabel: { fontSize: 12, fontWeight: '500', color: colors.textMuted },
    featureRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    featureScore: { fontSize: 13, fontWeight: '700' },
    featureTag: { fontSize: 11, fontWeight: '500', color: colors.textMuted, maxWidth: 120 },

    // compare modal
    compareContent: {
        backgroundColor: colors.card, borderRadius: borderRadius.xl,
        padding: spacing.lg, paddingTop: spacing.xl + spacing.md,
        alignItems: 'center', maxWidth: '95%',
        borderWidth: 1, borderColor: colors.border,
    },
    compareTitle: { fontSize: 18, fontWeight: '700', color: colors.foreground, marginBottom: spacing.md },
    compareSideBySide: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
    compareSlot: { alignItems: 'center' },
    compareImageBox: { borderRadius: borderRadius.md, overflow: 'hidden', backgroundColor: colors.surface },
    compareDate: { marginTop: spacing.xs, fontSize: 12, fontWeight: '500', color: colors.textMuted },
    compareRating: { fontSize: 14, fontWeight: '700', color: colors.foreground, marginTop: 2 },
    compareDelta: { marginTop: spacing.md, fontSize: 15, fontWeight: '600' },
});
