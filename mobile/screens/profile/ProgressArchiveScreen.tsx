import React, { useEffect, useState, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Image,
    useWindowDimensions,
    Platform,
    ActivityIndicator,
    ScrollView,
    Modal,
    Pressable,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

function formatProgressDate(dateStr: string): string {
    const d = new Date(dateStr);
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const day = d.getDate();
    const suffix = day === 1 || day === 21 || day === 31 ? 'st' : day === 2 || day === 22 ? 'nd' : day === 3 || day === 23 ? 'rd' : 'th';
    return `${months[d.getMonth()]} ${day}${suffix} ${d.getFullYear()}`;
}

const getImageWidth = (width: number) =>
    Platform.OS === 'web' && width > 600
        ? Math.min(width - 96, 480)
        : Math.min(width - 48, 340);

export default function ProgressArchiveScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { width: winWidth } = useWindowDimensions();

    const [photos, setPhotos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [viewerVisible, setViewerVisible] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);

    const imageWidth = getImageWidth(winWidth);
    const isDesktop = Platform.OS === 'web' && winWidth > 480;
    const gridColumns = isDesktop ? 5 : 3;
    const gridItemPadding = isDesktop ? 6 : 2;

    useEffect(() => {
        loadPhotos();
    }, []);

    const loadPhotos = async () => {
        try {
            const res = await api.getProgressPhotos().catch(() => ({ photos: [] }));
            setPhotos(res.photos || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const openViewer = (index: number) => {
        setSelectedIndex(index);
        setViewerVisible(true);
    };

    if (loading) {
        return (
            <View style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Progress Archive</Text>
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
                    <Text style={styles.headerTitle}>Progress Archive</Text>
                    <View style={{ width: 40 }} />
                </View>
                <View style={styles.emptyContainer}>
                    <Ionicons name="images-outline" size={48} color={colors.textMuted} />
                    <Text style={styles.emptyText}>No progress photos yet</Text>
                </View>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Progress Archive</Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView
                style={styles.gridScroll}
                contentContainerStyle={[styles.gridContent, isDesktop && styles.gridContentDesktop]}
                showsVerticalScrollIndicator={false}
            >
                <View style={[styles.grid, { paddingHorizontal: spacing.lg, marginHorizontal: isDesktop ? -gridItemPadding : -2 }]}>
                    {photos.map((item, index) => (
                        <TouchableOpacity
                            key={item.id}
                            style={[styles.gridItem, { width: `${100 / gridColumns}%`, padding: gridItemPadding }]}
                            onPress={() => openViewer(index)}
                            activeOpacity={0.9}
                        >
                            <Image
                                source={{ uri: api.resolveAttachmentUrl(item.image_url) }}
                                style={styles.gridImage}
                                resizeMode="cover"
                            />
                        </TouchableOpacity>
                    ))}
                </View>
            </ScrollView>

            {/* Full-screen viewer modal */}
            <Modal
                animationType="fade"
                transparent
                visible={viewerVisible}
                onRequestClose={() => setViewerVisible(false)}
            >
                <Pressable style={styles.viewerOverlay} onPress={() => setViewerVisible(false)}>
                    <Pressable style={[styles.viewerContent, { width: imageWidth + spacing.lg * 2 }]} onPress={() => {}}>
                        <TouchableOpacity
                            style={styles.viewerClose}
                            onPress={() => setViewerVisible(false)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name="close" size={24} color={colors.foreground} />
                        </TouchableOpacity>
                        {photos[selectedIndex] && (
                            <View style={[styles.imageBox, { width: imageWidth, height: imageWidth * (4 / 3) }]}>
                                <Image
                                    source={{ uri: api.resolveAttachmentUrl(photos[selectedIndex].image_url) }}
                                    style={[styles.slideImage, { width: imageWidth, height: imageWidth * (4 / 3) }]}
                                    resizeMode="contain"
                                />
                            </View>
                        )}
                        {photos[selectedIndex] && (
                            <Text style={styles.dateText}>
                                {formatProgressDate(photos[selectedIndex].created_at)}
                            </Text>
                        )}
                        {photos.length > 1 && (
                            <View style={[styles.navRow, { width: imageWidth }]}>
                                <TouchableOpacity
                                    style={[styles.navButton, selectedIndex === 0 && styles.navButtonDisabled]}
                                    onPress={() => setSelectedIndex(prev => Math.max(0, prev - 1))}
                                    disabled={selectedIndex === 0}
                                    activeOpacity={0.7}
                                >
                                    <Ionicons name="chevron-back" size={22} color={selectedIndex === 0 ? colors.textMuted : colors.foreground} />
                                    <Text style={[styles.navText, selectedIndex === 0 && styles.navTextDisabled]}>Prev</Text>
                                </TouchableOpacity>
                                <Text style={styles.counterText}>
                                    {selectedIndex + 1} / {photos.length}
                                </Text>
                                <TouchableOpacity
                                    style={[styles.navButton, selectedIndex >= photos.length - 1 && styles.navButtonDisabled]}
                                    onPress={() => setSelectedIndex(prev => Math.min(photos.length - 1, prev + 1))}
                                    disabled={selectedIndex >= photos.length - 1}
                                    activeOpacity={0.7}
                                >
                                    <Text style={[styles.navText, selectedIndex >= photos.length - 1 && styles.navTextDisabled]}>Next</Text>
                                    <Ionicons name="chevron-forward" size={22} color={selectedIndex >= photos.length - 1 ? colors.textMuted : colors.foreground} />
                                </TouchableOpacity>
                            </View>
                        )}
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
    headerTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.md },
    emptyText: { fontSize: 16, color: colors.textMuted },
    gridScroll: { flex: 1 },
    gridContent: { paddingTop: spacing.md, paddingBottom: spacing.xxl },
    gridContentDesktop: { maxWidth: 720, alignSelf: 'center', width: '100%' },
    grid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
    },
    gridItem: {
        aspectRatio: 1,
    },
    gridImage: {
        width: '100%',
        height: '100%',
        borderRadius: 4,
        backgroundColor: colors.surface,
    },
    viewerOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    viewerContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        alignItems: 'center',
        maxHeight: '90%',
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
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border || colors.surfaceLight,
        backgroundColor: colors.surface,
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
    },
    slideImage: {
        borderRadius: borderRadius.lg,
    },
    dateText: {
        marginTop: spacing.lg,
        fontSize: 20,
        fontWeight: '600',
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
});
