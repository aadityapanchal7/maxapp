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
    Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';
import api from '../../services/api';
import { CachedImage } from '../../components/CachedImage';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';
import { formatFaceRatingLabel } from '../../utils/faceRatingLabel';

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

const getImageWidth = (width: number) =>
    Platform.OS === 'web' && width > 600
        ? Math.min(width - 96, 480)
        : Math.min(width - 48, 340);

function getScoreColor(score: number) {
    if (score >= 7) return colors.foreground;
    if (score >= 5) return colors.warning;
    return colors.error;
}

export default function ProgressArchiveScreen() {
    const navigation = useNavigation<any>();
    const { width: winWidth } = useWindowDimensions();

    const [photos, setPhotos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [viewerVisible, setViewerVisible] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [sortNewest, setSortNewest] = useState(true);

    const [compareMode, setCompareMode] = useState(false);
    const [comparePicks, setComparePicks] = useState<[number | null, number | null]>([null, null]);
    const [compareVisible, setCompareVisible] = useState(false);

    const [scanHistory, setScanHistory] = useState<any[]>([]);
    const [expandedScan, setExpandedScan] = useState<any>(null);
    const [statsExpanded, setStatsExpanded] = useState(false);
    const [loadingScan, setLoadingScan] = useState(false);

    const imageWidth = getImageWidth(winWidth);
    const compareImageWidth = Math.floor((winWidth - 64) / 2);
    const isDesktop = Platform.OS === 'web' && winWidth > 480;
    const gridColumns = isDesktop ? 5 : 3;
    const gridItemPadding = isDesktop ? 6 : 2;

    useEffect(() => {
        loadPhotos();
    }, []);

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

    const photoScanMap = useMemo(() => {
        const map: Record<string, string> = {};
        if (!scanHistory.length) return map;
        for (const photo of photos) {
            const pTime = new Date(photo.created_at).getTime();
            let bestScan: any = null;
            let bestDiff = Infinity;
            for (const scan of scanHistory) {
                const diff = Math.abs(new Date(scan.created_at).getTime() - pTime);
                if (diff < bestDiff) { bestDiff = diff; bestScan = scan; }
            }
            if (bestScan && bestDiff < 5 * 60 * 1000) {
                map[photo.id] = bestScan.id;
            }
        }
        return map;
    }, [photos, scanHistory]);

    const fetchScanDetails = useCallback(async (scanId: string) => {
        setLoadingScan(true);
        try {
            const data = await api.getScanById(scanId);
            setExpandedScan(data);
        } catch (e) {
            console.error('Failed to load scan details', e);
            setExpandedScan(null);
        } finally {
            setLoadingScan(false);
        }
    }, []);

    const displayPhotos = useMemo(() => {
        if (!photos.length) return photos;
        const sorted = [...photos].sort((a, b) => {
            const da = new Date(a.created_at).getTime();
            const db = new Date(b.created_at).getTime();
            return sortNewest ? db - da : da - db;
        });
        return sorted;
    }, [photos, sortNewest]);

    const openViewer = (index: number) => {
        setSelectedIndex(index);
        setStatsExpanded(false);
        setExpandedScan(null);
        setViewerVisible(true);
    };

    const handleGridPress = useCallback((index: number) => {
        if (!compareMode) {
            openViewer(index);
            return;
        }
        const photoId = displayPhotos[index]?.id;
        if (!photoId) return;

        setComparePicks(prev => {
            if (prev[0] === index) return [null, prev[1]];
            if (prev[1] === index) return [prev[0], null];
            if (prev[0] === null) return [index, prev[1]];
            if (prev[1] === null) {
                return [prev[0], index];
            }
            return [prev[0], index];
        });
    }, [compareMode, displayPhotos]);

    useEffect(() => {
        if (comparePicks[0] !== null && comparePicks[1] !== null) {
            setCompareVisible(true);
        }
    }, [comparePicks]);

    const exitCompare = () => {
        setCompareMode(false);
        setComparePicks([null, null]);
        setCompareVisible(false);
    };

    const getRatingDelta = useCallback((currentPhoto: any): { text: string; color: string } | null => {
        if (currentPhoto?.face_rating == null || !Number.isFinite(Number(currentPhoto.face_rating))) return null;
        const currentDate = new Date(currentPhoto.created_at).getTime();
        const earlier = photos
            .filter(p => p.id !== currentPhoto.id && p.face_rating != null && Number.isFinite(Number(p.face_rating)) && new Date(p.created_at).getTime() < currentDate)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        if (!earlier.length) return null;
        const prev = earlier[0];
        const delta = Number(currentPhoto.face_rating) - Number(prev.face_rating);
        if (delta > 0) return { text: `+${delta.toFixed(1)}`, color: colors.success };
        if (delta < 0) return { text: delta.toFixed(1), color: colors.error };
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
                } else {
                    Alert.alert('Share', 'Copy the link to share this photo.');
                }
                return;
            }
            const dest = new FileSystem.File(FileSystem.Paths.cache, `progress_${photo.id}.jpg`);
            const downloaded = await FileSystem.File.downloadFileAsync(url, dest, { idempotent: true });
            const canShare = await Sharing.isAvailableAsync();
            if (canShare) {
                await Sharing.shareAsync(downloaded.uri);
            } else {
                Alert.alert('Sharing not available on this device');
            }
        } catch (e) {
            console.error('Share error', e);
            Alert.alert('Error', 'Could not share photo.');
        }
    };

    const deletePhoto = (index: number) => {
        const photo = displayPhotos[index];
        if (!photo) return;
        Alert.alert('Delete photo', 'Are you sure you want to delete this progress photo?', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Delete',
                style: 'destructive',
                onPress: async () => {
                    try {
                        await api.deleteProgressPhoto(photo.id);
                        const updated = photos.filter(p => p.id !== photo.id);
                        setPhotos(updated);
                        if (updated.length === 0) {
                            setViewerVisible(false);
                        } else {
                            setSelectedIndex(prev => Math.min(prev, updated.length - 1));
                        }
                    } catch (e) {
                        console.error(e);
                        Alert.alert('Error', 'Could not delete photo. Please try again.');
                    }
                },
            },
        ]);
    };

    const headerTitle = loading ? 'Progress Archive' : `Progress Archive (${photos.length})`;

    if (loading) {
        return (
            <View style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{headerTitle}</Text>
                    <View style={{ width: 40 }} />
                </View>
                <View style={styles.loadingContainer}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            </View>
        );
    }

    if (photos.length === 0) {
        return (
            <View style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{headerTitle}</Text>
                    <View style={{ width: 40 }} />
                </View>
                <View style={styles.emptyContainer}>
                    <Ionicons name="images-outline" size={48} color={colors.textMuted} />
                    <Text style={styles.emptyText}>No progress photos yet</Text>
                </View>
            </View>
        );
    }

    const currentViewerPhoto = displayPhotos[selectedIndex];
    const delta = currentViewerPhoto ? getRatingDelta(currentViewerPhoto) : null;

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => { if (compareMode) exitCompare(); else navigation.goBack(); }} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name={compareMode ? 'close' : 'arrow-back'} size={24} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.headerTitle} numberOfLines={1}>
                    {compareMode ? 'Select 2 photos' : headerTitle}
                </Text>
                <View style={styles.headerActions}>
                    {!compareMode && (
                        <TouchableOpacity
                            onPress={() => setSortNewest(prev => !prev)}
                            style={styles.headerIconBtn}
                            activeOpacity={0.7}
                            accessibilityLabel={sortNewest ? 'Sort oldest first' : 'Sort newest first'}
                        >
                            <Ionicons name={sortNewest ? 'arrow-down-outline' : 'arrow-up-outline'} size={20} color={colors.foreground} />
                        </TouchableOpacity>
                    )}
                    {!compareMode && photos.length >= 2 && (
                        <TouchableOpacity
                            onPress={() => setCompareMode(true)}
                            style={styles.headerIconBtn}
                            activeOpacity={0.7}
                            accessibilityLabel="Compare photos"
                        >
                            <Ionicons name="git-compare-outline" size={20} color={colors.foreground} />
                        </TouchableOpacity>
                    )}
                    {compareMode && (
                        <TouchableOpacity onPress={exitCompare} style={styles.headerIconBtn} activeOpacity={0.7}>
                            <Text style={styles.cancelText}>Cancel</Text>
                        </TouchableOpacity>
                    )}
                </View>
            </View>

            <ScrollView
                style={styles.gridScroll}
                contentContainerStyle={[styles.gridContent, isDesktop && styles.gridContentDesktop]}
                showsVerticalScrollIndicator={false}
            >
                {!compareMode && (
                    <Text style={styles.sortHint}>
                        {sortNewest ? 'Newest first' : 'Oldest first'}
                    </Text>
                )}
                <View style={[styles.grid, { paddingHorizontal: spacing.lg, marginHorizontal: isDesktop ? -gridItemPadding : -2 }]}>
                    {displayPhotos.map((item, index) => {
                        const isPick1 = comparePicks[0] === index;
                        const isPick2 = comparePicks[1] === index;
                        const isSelected = isPick1 || isPick2;
                        return (
                            <TouchableOpacity
                                key={item.id}
                                style={[styles.gridItem, { width: `${100 / gridColumns}%`, padding: gridItemPadding }]}
                                onPress={() => handleGridPress(index)}
                                activeOpacity={0.9}
                            >
                                <View style={[styles.gridThumbWrap, isSelected && styles.gridThumbSelected]}>
                                    <CachedImage
                                        uri={api.resolveAttachmentUrl(item.image_url)}
                                        style={styles.gridImage}
                                        contentFit="cover"
                                    />
                                    {item.face_rating != null && Number.isFinite(Number(item.face_rating)) ? (
                                        <Text style={styles.gridRatingBadge}>
                                            {formatFaceRatingLabel(Number(item.face_rating))}
                                        </Text>
                                    ) : null}
                                    {isSelected && (
                                        <View style={styles.compareBadge}>
                                            <Text style={styles.compareBadgeText}>{isPick1 ? '1' : '2'}</Text>
                                        </View>
                                    )}
                                </View>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            </ScrollView>

            {/* Full-screen viewer modal */}
            <Modal animationType="fade" transparent visible={viewerVisible} onRequestClose={() => setViewerVisible(false)}>
                <Pressable style={styles.viewerOverlay} onPress={() => setViewerVisible(false)}>
                    <ScrollView contentContainerStyle={styles.viewerScrollContent} showsVerticalScrollIndicator={false}>
                    <Pressable style={[styles.viewerContent, { width: imageWidth + spacing.lg * 2 }]} onPress={() => {}}>
                        <TouchableOpacity style={styles.viewerClose} onPress={() => setViewerVisible(false)} activeOpacity={0.7}>
                            <Ionicons name="close" size={24} color={colors.foreground} />
                        </TouchableOpacity>
                        {currentViewerPhoto && (
                            <View style={[styles.imageBox, { width: imageWidth, height: imageWidth * (4 / 3) }]}>
                                <CachedImage
                                    uri={api.resolveAttachmentUrl(currentViewerPhoto.image_url)}
                                    style={[styles.slideImage, { width: imageWidth, height: imageWidth * (4 / 3) }]}
                                    contentFit="contain"
                                />
                                {currentViewerPhoto.face_rating != null && Number.isFinite(Number(currentViewerPhoto.face_rating)) ? (
                                    <View style={styles.viewerRatingRow}>
                                        <Text style={styles.viewerRatingBadge}>
                                            {formatFaceRatingLabel(Number(currentViewerPhoto.face_rating))}
                                        </Text>
                                        {delta && (
                                            <Text style={[styles.viewerDeltaBadge, { color: delta.color }]}>
                                                ({delta.text})
                                            </Text>
                                        )}
                                    </View>
                                ) : null}
                            </View>
                        )}
                        {currentViewerPhoto && (
                            <Text style={styles.dateText}>
                                {formatProgressDate(currentViewerPhoto.created_at)}
                            </Text>
                        )}

                        {currentViewerPhoto && photoScanMap[currentViewerPhoto.id] && (
                            <View style={styles.scanStatsSection}>
                                <TouchableOpacity
                                    style={styles.expandStatsBtn}
                                    activeOpacity={0.7}
                                    onPress={() => {
                                        if (statsExpanded) {
                                            setStatsExpanded(false);
                                            return;
                                        }
                                        const scanId = photoScanMap[currentViewerPhoto.id];
                                        if (expandedScan?.id === scanId) {
                                            setStatsExpanded(true);
                                            return;
                                        }
                                        setStatsExpanded(true);
                                        fetchScanDetails(scanId);
                                    }}
                                >
                                    <Ionicons
                                        name={statsExpanded ? 'chevron-up' : 'analytics-outline'}
                                        size={16}
                                        color={colors.foreground}
                                    />
                                    <Text style={styles.expandStatsBtnText}>
                                        {statsExpanded ? 'Hide scan details' : 'View scan details'}
                                    </Text>
                                </TouchableOpacity>

                                {statsExpanded && (
                                    loadingScan ? (
                                        <ActivityIndicator color={colors.foreground} style={{ marginTop: spacing.sm }} />
                                    ) : expandedScan?.analysis ? (
                                        <View style={styles.scanStatsGrid}>
                                            {(() => {
                                                const pr = expandedScan.analysis?.psl_rating || {};
                                                const pi = expandedScan.analysis?.profile_insights;
                                                const tier = typeof pr.psl_tier === 'string' ? pr.psl_tier.trim() : '';
                                                const appeal = typeof pr.appeal === 'number' ? pr.appeal : parseFloat(String(pr.appeal || ''));
                                                const arch = (typeof pr.archetype === 'string' ? pr.archetype.trim() : '') ||
                                                             (typeof pi?.archetype === 'string' ? pi.archetype.trim() : '');
                                                const ascMonths = typeof pr.ascension_time_months === 'number' ? pr.ascension_time_months :
                                                    parseInt(String(pr.ascension_time_months || '0'), 10) || 0;
                                                const ageSc = typeof pr.age_score === 'number' ? pr.age_score :
                                                    parseInt(String(pr.age_score || '0'), 10) || 0;
                                                const potential = typeof pr.potential === 'number' ? pr.potential :
                                                    parseFloat(String(pr.potential || ''));
                                                const mogPct = typeof pr.mog_percentile === 'number' ? pr.mog_percentile : null;
                                                const glowUp = typeof pr.glow_up_potential === 'number' ? pr.glow_up_potential : null;
                                                const weakest = typeof pr.weakest_link === 'string' ? pr.weakest_link.trim() : '';
                                                const auraTags: string[] = Array.isArray(pr.aura_tags) ? pr.aura_tags : [];
                                                const featureScores = pr.feature_scores || {};

                                                return (
                                                    <>
                                                        <View style={styles.scanStatRow}>
                                                            <Text style={styles.scanStatLabel}>Tier</Text>
                                                            <Text style={styles.scanStatValue}>{tier || '—'}</Text>
                                                        </View>
                                                        {!Number.isNaN(appeal) && (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Appeal</Text>
                                                                <Text style={[styles.scanStatValue, { color: getScoreColor(appeal) }]}>
                                                                    {appeal.toFixed(1)}/10
                                                                </Text>
                                                            </View>
                                                        )}
                                                        {!Number.isNaN(potential) && (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Potential</Text>
                                                                <Text style={[styles.scanStatValue, { color: getScoreColor(potential) }]}>
                                                                    {potential.toFixed(1)}/10
                                                                </Text>
                                                            </View>
                                                        )}
                                                        <View style={styles.scanStatRow}>
                                                            <Text style={styles.scanStatLabel}>Archetype</Text>
                                                            <Text style={styles.scanStatValue}>{arch || '—'}</Text>
                                                        </View>
                                                        <View style={styles.scanStatRow}>
                                                            <Text style={styles.scanStatLabel}>Ascension time</Text>
                                                            <Text style={styles.scanStatValue}>
                                                                {ascMonths > 0 ? `${ascMonths} months` : '—'}
                                                            </Text>
                                                        </View>
                                                        <View style={styles.scanStatRow}>
                                                            <Text style={styles.scanStatLabel}>Facial age</Text>
                                                            <Text style={styles.scanStatValue}>{ageSc > 0 ? `${ageSc}` : '—'}</Text>
                                                        </View>
                                                        {mogPct !== null && (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Mog percentile</Text>
                                                                <Text style={styles.scanStatValue}>{mogPct}%</Text>
                                                            </View>
                                                        )}
                                                        {glowUp !== null && (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Glow-up potential</Text>
                                                                <Text style={[styles.scanStatValue, { color: getScoreColor(glowUp) }]}>
                                                                    {glowUp.toFixed(1)}/10
                                                                </Text>
                                                            </View>
                                                        )}
                                                        {weakest ? (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Weakest link</Text>
                                                                <Text style={styles.scanStatValue}>{weakest}</Text>
                                                            </View>
                                                        ) : null}
                                                        {auraTags.length > 0 && (
                                                            <View style={styles.scanStatRow}>
                                                                <Text style={styles.scanStatLabel}>Aura tags</Text>
                                                                <Text style={styles.scanStatValue}>{auraTags.join(', ')}</Text>
                                                            </View>
                                                        )}

                                                        {Object.keys(featureScores).length > 0 && (
                                                            <>
                                                                <Text style={styles.featureScoresHeader}>Feature Scores</Text>
                                                                {Object.entries(featureScores).map(([key, val]: [string, any]) => {
                                                                    const score = typeof val?.score === 'number' ? val.score : null;
                                                                    const tag = typeof val?.tag === 'string' ? val.tag : '';
                                                                    const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                                                                    return (
                                                                        <View key={key} style={styles.featureRow}>
                                                                            <Text style={styles.featureLabel}>{label}</Text>
                                                                            <View style={styles.featureRight}>
                                                                                {score !== null && (
                                                                                    <Text style={[styles.featureScore, { color: getScoreColor(score) }]}>
                                                                                        {score.toFixed(1)}
                                                                                    </Text>
                                                                                )}
                                                                                {tag ? <Text style={styles.featureTag}>{tag}</Text> : null}
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

                        <View style={styles.actionRow}>
                            <TouchableOpacity style={styles.actionBtn} onPress={() => handleShare(currentViewerPhoto)} activeOpacity={0.7}>
                                <Ionicons name="share-outline" size={18} color={colors.foreground} />
                                <Text style={styles.actionBtnText}>Share</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.actionBtn} onPress={() => deletePhoto(selectedIndex)} activeOpacity={0.7}>
                                <Ionicons name="trash-outline" size={18} color={colors.error} />
                                <Text style={[styles.actionBtnText, { color: colors.error }]}>Delete</Text>
                            </TouchableOpacity>
                        </View>
                        {displayPhotos.length > 1 && (
                            <View style={[styles.navRow, { width: imageWidth }]}>
                                <TouchableOpacity
                                    style={[styles.navButton, selectedIndex === 0 && styles.navButtonDisabled]}
                                    onPress={() => { setSelectedIndex(prev => Math.max(0, prev - 1)); setStatsExpanded(false); setExpandedScan(null); }}
                                    disabled={selectedIndex === 0}
                                    activeOpacity={0.7}
                                >
                                    <Ionicons name="chevron-back" size={22} color={selectedIndex === 0 ? colors.textMuted : colors.foreground} />
                                    <Text style={[styles.navText, selectedIndex === 0 && styles.navTextDisabled]}>Prev</Text>
                                </TouchableOpacity>
                                <Text style={styles.counterText}>
                                    {selectedIndex + 1} / {displayPhotos.length}
                                </Text>
                                <TouchableOpacity
                                    style={[styles.navButton, selectedIndex >= displayPhotos.length - 1 && styles.navButtonDisabled]}
                                    onPress={() => { setSelectedIndex(prev => Math.min(displayPhotos.length - 1, prev + 1)); setStatsExpanded(false); setExpandedScan(null); }}
                                    disabled={selectedIndex >= displayPhotos.length - 1}
                                    activeOpacity={0.7}
                                >
                                    <Text style={[styles.navText, selectedIndex >= displayPhotos.length - 1 && styles.navTextDisabled]}>Next</Text>
                                    <Ionicons name="chevron-forward" size={22} color={selectedIndex >= displayPhotos.length - 1 ? colors.textMuted : colors.foreground} />
                                </TouchableOpacity>
                            </View>
                        )}
                    </Pressable>
                    </ScrollView>
                </Pressable>
            </Modal>

            {/* Compare modal */}
            <Modal animationType="fade" transparent visible={compareVisible} onRequestClose={() => setCompareVisible(false)}>
                <Pressable style={styles.viewerOverlay} onPress={() => setCompareVisible(false)}>
                    <Pressable style={styles.compareContent} onPress={() => {}}>
                        <TouchableOpacity style={styles.viewerClose} onPress={() => { setCompareVisible(false); exitCompare(); }} activeOpacity={0.7}>
                            <Ionicons name="close" size={24} color={colors.foreground} />
                        </TouchableOpacity>
                        <Text style={styles.compareTitle}>Compare</Text>
                        <View style={styles.compareSideBySide}>
                            {[comparePicks[0], comparePicks[1]].map((pickIdx, i) => {
                                const photo = pickIdx !== null ? displayPhotos[pickIdx] : null;
                                if (!photo) return <View key={i} style={[styles.compareSlot, { width: compareImageWidth }]} />;
                                const hasRating = photo.face_rating != null && Number.isFinite(Number(photo.face_rating));
                                return (
                                    <View key={i} style={[styles.compareSlot, { width: compareImageWidth }]}>
                                        <View style={[styles.compareImageBox, { width: compareImageWidth, height: compareImageWidth * (4 / 3) }]}>
                                            <CachedImage
                                                uri={api.resolveAttachmentUrl(photo.image_url)}
                                                style={{ width: compareImageWidth, height: compareImageWidth * (4 / 3) }}
                                                contentFit="cover"
                                            />
                                        </View>
                                        <Text style={styles.compareDate}>{formatShortDate(photo.created_at)}</Text>
                                        {hasRating && (
                                            <Text style={styles.compareRating}>{formatFaceRatingLabel(Number(photo.face_rating))}</Text>
                                        )}
                                    </View>
                                );
                            })}
                        </View>
                        {comparePicks[0] !== null && comparePicks[1] !== null && (() => {
                            const p1 = displayPhotos[comparePicks[0]!];
                            const p2 = displayPhotos[comparePicks[1]!];
                            if (!p1 || !p2) return null;
                            const r1 = Number(p1.face_rating);
                            const r2 = Number(p2.face_rating);
                            if (!Number.isFinite(r1) || !Number.isFinite(r2)) return null;
                            const diff = r2 - r1;
                            const diffColor = diff > 0 ? colors.success : diff < 0 ? colors.error : colors.textMuted;
                            return (
                                <Text style={[styles.compareDelta, { color: diffColor }]}>
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

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 56,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
    },
    backButton: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.card,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.sm,
    },
    headerTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground, flex: 1, textAlign: 'center' },
    headerActions: { flexDirection: 'row', alignItems: 'center', gap: 4, minWidth: 40 },
    headerIconBtn: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cancelText: { fontSize: 14, fontWeight: '500', color: colors.error },
    sortHint: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textMuted,
        paddingHorizontal: spacing.lg,
        marginBottom: spacing.xs,
    },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.md },
    emptyText: { fontSize: 16, color: colors.textMuted },
    gridScroll: { flex: 1 },
    gridContent: { paddingTop: spacing.md, paddingBottom: spacing.xxl },
    gridContentDesktop: { maxWidth: 720, alignSelf: 'center', width: '100%' },
    grid: { flexDirection: 'row', flexWrap: 'wrap' },
    gridItem: { aspectRatio: 1 },
    gridThumbWrap: {
        flex: 1,
        width: '100%',
        borderRadius: 4,
        overflow: 'hidden',
        position: 'relative',
        backgroundColor: colors.surface,
    },
    gridThumbSelected: {
        borderWidth: 2,
        borderColor: colors.info,
        borderRadius: 6,
    },
    gridImage: {
        width: '100%',
        height: '100%',
        borderRadius: 4,
        backgroundColor: colors.surface,
    },
    gridRatingBadge: {
        position: 'absolute',
        bottom: 5,
        right: 5,
        fontSize: 11,
        fontWeight: '800',
        color: '#FFFFFF',
        textShadowColor: 'rgba(0,0,0,0.85)',
        textShadowOffset: { width: 0, height: 1 },
        textShadowRadius: 4,
    },
    compareBadge: {
        position: 'absolute',
        top: 4,
        left: 4,
        width: 22,
        height: 22,
        borderRadius: 11,
        backgroundColor: colors.info,
        alignItems: 'center',
        justifyContent: 'center',
    },
    compareBadgeText: { fontSize: 12, fontWeight: '700', color: '#fff' },
    viewerOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    viewerScrollContent: {
        flexGrow: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    viewerContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        alignItems: 'center',
        ...shadows.lg,
    },
    viewerClose: {
        position: 'absolute',
        top: spacing.md,
        right: spacing.md,
        zIndex: 10,
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.card,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.md,
    },
    imageBox: {
        position: 'relative',
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border || colors.surfaceLight,
        backgroundColor: colors.surface,
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
    },
    viewerRatingRow: {
        position: 'absolute',
        bottom: 10,
        right: 10,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
    },
    viewerRatingBadge: {
        fontSize: 14,
        fontWeight: '800',
        color: '#FFFFFF',
        textShadowColor: 'rgba(0,0,0,0.85)',
        textShadowOffset: { width: 0, height: 1 },
        textShadowRadius: 4,
    },
    viewerDeltaBadge: {
        fontSize: 12,
        fontWeight: '700',
        textShadowColor: 'rgba(0,0,0,0.6)',
        textShadowOffset: { width: 0, height: 1 },
        textShadowRadius: 3,
    },
    slideImage: { borderRadius: borderRadius.lg },
    dateText: {
        marginTop: spacing.lg,
        fontSize: 20,
        fontWeight: '600',
        color: colors.foreground,
    },
    actionRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.lg,
        marginTop: spacing.md,
    },
    actionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
    },
    actionBtnText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.foreground,
    },
    navRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: spacing.lg,
        width: '100%',
        maxWidth: 320,
    },
    navButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
    },
    navButtonDisabled: { opacity: 0.5 },
    navText: { fontSize: 15, fontWeight: '600', color: colors.foreground },
    navTextDisabled: { color: colors.textMuted },
    counterText: { fontSize: 14, color: colors.textMuted },
    compareContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        paddingTop: spacing.xl + spacing.md,
        alignItems: 'center',
        maxWidth: '95%',
        ...shadows.lg,
    },
    compareTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: colors.foreground,
        marginBottom: spacing.md,
    },
    compareSideBySide: {
        flexDirection: 'row',
        gap: spacing.sm,
        alignItems: 'flex-start',
    },
    compareSlot: { alignItems: 'center' },
    compareImageBox: {
        borderRadius: borderRadius.md,
        overflow: 'hidden',
        backgroundColor: colors.surface,
    },
    compareDate: {
        marginTop: spacing.xs,
        fontSize: 12,
        fontWeight: '500',
        color: colors.textSecondary,
    },
    compareRating: {
        fontSize: 14,
        fontWeight: '700',
        color: colors.foreground,
        marginTop: 2,
    },
    compareDelta: {
        marginTop: spacing.md,
        fontSize: 15,
        fontWeight: '600',
    },
    scanStatsSection: {
        width: '100%',
        marginTop: spacing.sm,
    },
    expandStatsBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    expandStatsBtnText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.foreground,
    },
    scanStatsGrid: {
        width: '100%',
        marginTop: spacing.sm,
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border,
        padding: spacing.md,
        gap: spacing.xs,
    },
    scanStatRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 4,
    },
    scanStatLabel: {
        fontSize: 12,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 0.3,
    },
    scanStatValue: {
        fontSize: 13,
        fontWeight: '700',
        color: colors.foreground,
        flexShrink: 1,
        textAlign: 'right',
        maxWidth: '60%',
    },
    featureScoresHeader: {
        fontSize: 11,
        fontWeight: '700',
        color: colors.textMuted,
        letterSpacing: 0.6,
        marginTop: spacing.sm,
        marginBottom: 2,
        textTransform: 'uppercase',
    },
    featureRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 3,
    },
    featureLabel: {
        fontSize: 12,
        fontWeight: '500',
        color: colors.textSecondary,
    },
    featureRight: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
    },
    featureScore: {
        fontSize: 13,
        fontWeight: '700',
    },
    featureTag: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textMuted,
        maxWidth: 120,
    },
});
