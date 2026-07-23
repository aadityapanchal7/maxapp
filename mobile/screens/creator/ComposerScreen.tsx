/**
 * ComposerScreen — the frictionless post composer. Video or text in one screen:
 * pick/record a clip (or write text), add a caption, tap Post. The upload runs
 * with an inline "Posting…" state, then returns to the studio.
 */
import React, { useRef, useState } from 'react';
import {
    ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView,
    StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { fonts } from '../../theme/dark';
import CreatorVideo from '../../components/creator/CreatorVideo';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const MAX_SECONDS = 180;

export default function ComposerScreen() {
    const nav = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [mode, setMode] = useState<'video' | 'text'>('video');
    const [videoUri, setVideoUri] = useState<string | null>(null);
    const [durationS, setDurationS] = useState<number | null>(null);
    const [caption, setCaption] = useState('');
    const [posting, setPosting] = useState(false);
    // Set when the user taps Cancel mid-upload: the request keeps running
    // server-side, but its resolution must no longer navigate or alert (the
    // user has already left this screen).
    const cancelledRef = useRef(false);

    const pickVideo = async (fromCamera: boolean) => {
        try {
            const perm = fromCamera
                ? await ImagePicker.requestCameraPermissionsAsync()
                : await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (!perm.granted) {
                Alert.alert('Permission needed', fromCamera ? 'Enable camera access to record.' : 'Enable photo access to choose a clip.');
                return;
            }
            const opts: ImagePicker.ImagePickerOptions = {
                mediaTypes: ['videos'],
                videoMaxDuration: MAX_SECONDS,
                quality: 0.7,
            };
            const res = fromCamera
                ? await ImagePicker.launchCameraAsync(opts)
                : await ImagePicker.launchImageLibraryAsync(opts);
            if (res.canceled || !res.assets?.[0]) return;
            const a = res.assets[0];
            const secs = a.duration ? Math.round(a.duration / 1000) : null;
            if (secs && secs > MAX_SECONDS + 2) {
                Alert.alert('Too long', 'Keep it under 3 minutes.');
                return;
            }
            setVideoUri(a.uri);
            setDurationS(secs);
        } catch (e: any) {
            Alert.alert('Could not load video', e?.message || 'Try again.');
        }
    };

    const canPost = posting
        ? false
        : mode === 'text'
            ? caption.trim().length > 0
            : !!videoUri;

    const post = async () => {
        if (!canPost) return;
        setPosting(true);
        cancelledRef.current = false;
        try {
            await api.createCreatorPost({
                type: mode,
                body: caption.trim(),
                videoUri: mode === 'video' ? videoUri : null,
                durationS: mode === 'video' ? durationS : null,
            });
            if (cancelledRef.current) return; // user bailed mid-upload; don't navigate again
            nav.goBack();
        } catch (e: any) {
            if (cancelledRef.current) return; // user already left; no late error alert
            Alert.alert('Could not post', e?.response?.data?.detail || e?.message || 'Try again.');
            setPosting(false);
        }
    };

    return (
        <View style={[s.root, { paddingTop: insets.top + 6 }]}>
            <View style={s.topBar}>
                {/* Cancel stays tappable during the upload (a large clip can run
                    up to 2 minutes) — a frozen Cancel used to read as a locked
                    screen. Bailing mid-upload just abandons the result client-side
                    (cancelledRef guards the late resolve). */}
                <TouchableOpacity
                    onPress={() => {
                        if (posting) cancelledRef.current = true;
                        nav.goBack();
                    }}
                    hitSlop={12}
                    accessibilityLabel="Cancel"
                >
                    <Text style={s.cancel}>Cancel</Text>
                </TouchableOpacity>
                <Text style={s.topTitle}>New update</Text>
                <TouchableOpacity onPress={post} disabled={!canPost} hitSlop={12} accessibilityLabel="Post">
                    {posting ? <ActivityIndicator size="small" color={INK} /> : <Text style={[s.postBtn, !canPost && { opacity: 0.35 }]}>Post</Text>}
                </TouchableOpacity>
            </View>

            <View style={s.segment}>
                {(['video', 'text'] as const).map((m) => (
                    <TouchableOpacity key={m} style={[s.segItem, mode === m && s.segItemOn]} onPress={() => setMode(m)} activeOpacity={0.8} disabled={posting}>
                        <Ionicons name={m === 'video' ? 'videocam-outline' : 'text-outline'} size={16} color={mode === m ? '#FFFFFF' : INK} />
                        <Text style={[s.segText, mode === m && s.segTextOn]}>{m === 'video' ? 'Video' : 'Text'}</Text>
                    </TouchableOpacity>
                ))}
            </View>

            <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
                <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 30 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                    {mode === 'video' ? (
                        videoUri ? (
                            <View style={{ marginTop: 16 }}>
                                <CreatorVideo uri={videoUri} height={360} />
                                <TouchableOpacity style={s.retake} onPress={() => { setVideoUri(null); setDurationS(null); }} disabled={posting}>
                                    <Ionicons name="refresh" size={15} color={MUTE} />
                                    <Text style={s.retakeText}>Choose a different clip</Text>
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <View style={{ marginTop: 16, gap: 12 }}>
                                <TouchableOpacity style={s.pickBtn} onPress={() => pickVideo(true)} activeOpacity={0.85}>
                                    <Ionicons name="camera-outline" size={20} color={INK} />
                                    <Text style={s.pickText}>Record a clip</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={s.pickBtn} onPress={() => pickVideo(false)} activeOpacity={0.85}>
                                    <Ionicons name="albums-outline" size={20} color={INK} />
                                    <Text style={s.pickText}>Choose from library</Text>
                                </TouchableOpacity>
                                <Text style={s.hint}>Up to 3 minutes. Your subscribers get a push when you post.</Text>
                            </View>
                        )
                    ) : null}

                    <TextInput
                        style={[s.caption, mode === 'text' && s.captionBig]}
                        value={caption}
                        onChangeText={setCaption}
                        placeholder={mode === 'video' ? 'Add a caption…' : "What's on your mind?"}
                        placeholderTextColor={MUTE}
                        multiline
                        maxLength={2200}
                        editable={!posting}
                    />
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, height: 44 },
    cancel: { fontFamily: fonts.sansMedium, fontSize: 15, color: MUTE },
    topTitle: { fontFamily: fonts.sansSemiBold, fontSize: 16, color: INK },
    postBtn: { fontFamily: fonts.sansSemiBold, fontSize: 15.5, color: '#2C6BED' },
    segment: { flexDirection: 'row', gap: 6, marginHorizontal: 20, marginTop: 8, backgroundColor: 'rgba(0,0,0,0.05)', borderRadius: 12, padding: 4 },
    segItem: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 38, borderRadius: 9 },
    segItemOn: { backgroundColor: INK },
    segText: { fontFamily: fonts.sansMedium, fontSize: 14, color: INK },
    segTextOn: { color: '#FFFFFF', fontFamily: fonts.sansSemiBold },
    pickBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF', borderRadius: 14, paddingVertical: 16, paddingHorizontal: 16, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.08)' },
    pickText: { fontFamily: fonts.sansMedium, fontSize: 15.5, color: INK },
    hint: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 4, paddingHorizontal: 2 },
    retake: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 12 },
    retakeText: { fontFamily: fonts.sansMedium, fontSize: 13.5, color: MUTE },
    caption: { backgroundColor: '#FFFFFF', borderRadius: 14, padding: 14, marginTop: 16, minHeight: 80, fontFamily: fonts.sans, fontSize: 16, color: INK, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.08)' },
    captionBig: { minHeight: 200, fontSize: 18 },
});
