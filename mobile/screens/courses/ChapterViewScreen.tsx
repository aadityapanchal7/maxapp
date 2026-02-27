import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useVideoPlayer, VideoView } from 'expo-video';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function ChapterViewScreen() {
    const navigation = useNavigation();
    const route = useRoute<any>();
    const { chapter, courseId, moduleNumber, isCompleted: initialCompleted } = route.params;

    const [completed, setCompleted] = useState(initialCompleted);
    const [marking, setMarking] = useState(false);

    // Video Player Setup
    const player = useVideoPlayer(chapter.video_url || '', player => {
        player.loop = true;
        player.play();
    });

    const handleComplete = async () => {
        if (completed) return;
        setMarking(true);
        try {
            await api.completeChapter(courseId, chapter.chapter_id, moduleNumber);
            setCompleted(true);
            Alert.alert("Great job!", "Chapter marked as complete.", [
                { text: "Next", onPress: () => navigation.goBack() }
            ]);
        } catch (error) {
            Alert.alert("Error", "Could not mark complete");
        } finally {
            setMarking(false);
        }
    };

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                    <Ionicons name="close" size={24} color={colors.textPrimary} />
                </TouchableOpacity>
                <Text style={styles.headerTitle} numberOfLines={1}>{chapter.title}</Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView contentContainerStyle={styles.content}>
                {/* Content Rendering */}
                {chapter.type === 'video' && chapter.video_url ? (
                    <View style={styles.videoContainer}>
                        <VideoView
                            style={styles.video}
                            player={player}
                            allowsFullscreen
                            allowsPictureInPicture
                        />
                        <Text style={styles.caption}>Video Content</Text>
                    </View>
                ) : chapter.type === 'image' && chapter.image_url ? (
                    <View style={styles.imageContainer}>
                        <Image source={{ uri: chapter.image_url }} style={styles.contentImage} />
                    </View>
                ) : null}

                {/* Text Content */}
                <View style={styles.textContainer}>
                    <Text style={styles.chapterDesc}>{chapter.description}</Text>
                    {chapter.content && <Text style={styles.contentText}>{chapter.content}</Text>}

                    {/* Instructions - Legacy/Extra */}
                    {chapter.instructions && chapter.instructions.length > 0 && (
                        <View style={styles.section}>
                            <Text style={styles.sectionHeader}>Instructions</Text>
                            {chapter.instructions.map((inst: string, i: number) => (
                                <View key={i} style={styles.listItem}>
                                    <Text style={styles.bullet}>•</Text>
                                    <Text style={styles.listText}>{inst}</Text>
                                </View>
                            ))}
                        </View>
                    )}
                </View>
            </ScrollView>

            {/* Footer Action */}
            <View style={styles.footer}>
                <TouchableOpacity
                    style={[styles.completeButton, completed && styles.completedButton]}
                    onPress={handleComplete}
                    disabled={completed || marking}
                >
                    <Text style={styles.buttonText}>
                        {completed ? "Completed" : marking ? "Marking..." : "Mark as Complete"}
                    </Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.md, paddingTop: 60, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
    backButton: { padding: spacing.xs },
    headerTitle: { ...typography.h3, flex: 1, textAlign: 'center' },
    content: { paddingBottom: 100 },
    videoContainer: { width: '100%', height: 220, backgroundColor: '#000', marginBottom: spacing.md },
    video: { flex: 1 },
    caption: { textAlign: 'center', color: colors.textMuted, marginTop: 4, fontSize: 12 },
    imageContainer: { width: '100%', height: 250, marginBottom: spacing.md },
    contentImage: { width: '100%', height: '100%', resizeMode: 'contain' },
    textContainer: { padding: spacing.lg },
    chapterDesc: { ...typography.h3, marginBottom: spacing.md },
    contentText: { ...typography.body, lineHeight: 24, marginBottom: spacing.lg },
    section: { marginTop: spacing.lg },
    sectionHeader: { ...typography.h3, marginBottom: spacing.sm, color: colors.primary },
    listItem: { flexDirection: 'row', marginBottom: spacing.sm },
    bullet: { color: colors.primary, marginRight: spacing.sm, fontSize: 16 },
    listText: { ...typography.body, flex: 1 },
    footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: spacing.lg, backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.border },
    completeButton: { backgroundColor: colors.primary, paddingVertical: spacing.md, borderRadius: borderRadius.md, alignItems: 'center' },
    completedButton: { backgroundColor: colors.success },
    buttonText: { ...typography.button, color: '#000' }
});
