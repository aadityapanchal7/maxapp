import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Image, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { ChatTypingIndicator } from '../../components/ChatTypingIndicator';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { parseFitmaxMessageUi } from './fitmax';
import { FitmaxInlineCard } from './types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
  attachment_url?: string;
  attachment_type?: string;
  isTyping?: boolean;
}

interface Props {
  onOpenPlan: () => void;
  onOpenCalorieLog: () => void;
  onOpenProgress: () => void;
  onOpenWorkout: () => void;
  onOpenModule: (moduleId?: number) => void;
}

const FITMAX_GREETING =
  "hey, welcome to fitmax. before we build your plan, i need to know a bit about you ù this takes about 3 minutes and everything we create depends on it. what's your main goal right now? losing fat, building muscle, recomp, or something else?";

export default function FitmaxChatPanel({ onOpenPlan, onOpenCalorieLog, onOpenProgress, onOpenWorkout, onOpenModule }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const listRef = useRef<FlatList>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const { messages: history } = await api.getChatHistory();
      const msgs = (history || []).filter((m: Message) => !!m.content?.trim());
      const hasFitmaxContext = msgs.some((m: Message) => (m.content || '').toLowerCase().includes('fitmax'));
      if (!msgs.length || !hasFitmaxContext) {
        setMessages([{ role: 'assistant', content: FITMAX_GREETING, created_at: new Date().toISOString() }]);
      } else {
        setMessages(msgs);
      }
    } catch (e) {
      console.error(e);
      setMessages([{ role: 'assistant', content: FITMAX_GREETING }]);
    } finally {
      setBootstrapped(true);
    }
  };

  const withTyping = () => setMessages(prev => [...prev.filter(m => !m.isTyping), { role: 'assistant', content: '', isTyping: true }]);
  const clearTyping = () => setMessages(prev => prev.filter(m => !m.isTyping));

  const sendMessage = async (textOverride?: string) => {
    const msg = (textOverride ?? input).trim();
    if (!msg || loading) return;

    setLoading(true);
    if (!textOverride) setInput('');

    const userMessage: Message = { role: 'user', content: msg, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, userMessage]);
    withTyping();

    try {
      const { response } = await api.sendChatMessage(msg, undefined, undefined, 'fitmax');
      clearTyping();
      setMessages(prev => [...prev, { role: 'assistant', content: response, created_at: new Date().toISOString() }]);
    } catch (e) {
      console.error(e);
      clearTyping();
      setMessages(prev => [...prev, { role: 'assistant', content: 'sorry ù i hit an issue. send that again and i got you.' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleCardPress = (card: FitmaxInlineCard) => {
    if (card.type === 'plan') return onOpenPlan();
    if (card.type === 'calorie_log') return onOpenCalorieLog();
    if (card.type === 'progress') return onOpenProgress();
    if (card.type === 'workout') return onOpenWorkout();
    if (card.type === 'module') return onOpenModule(card.payload?.moduleId);
  };

  const renderCard = (card: FitmaxInlineCard) => (
    <TouchableOpacity key={card.id} style={styles.inlineCard} onPress={() => handleCardPress(card)} activeOpacity={0.75}>
      <View style={styles.inlineCardTop}>
        <Text style={styles.inlineTitle}>{card.title}</Text>
        <Ionicons name="chevron-forward" size={18} color={colors.foreground} />
      </View>
      {card.subtitle ? <Text style={styles.inlineSubtitle}>{card.subtitle}</Text> : null}
      <Text style={styles.inlineCta}>{card.cta}</Text>
    </TouchableOpacity>
  );

  const renderMessage = ({ item }: { item: Message }) => {
    if (item.isTyping) {
      return (
        <View style={styles.row}>
          <View style={[styles.bubble, styles.aiBubble]}>
            <ChatTypingIndicator mode="schedule" style={styles.typing} />
          </View>
        </View>
      );
    }

    const ui = parseFitmaxMessageUi(item.content || '');

    return (
      <View style={[styles.row, item.role === 'user' && styles.userRow]}>
        <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.aiBubble, ui.kind === 'coaching_insight' && item.role === 'assistant' ? styles.coachingBubble : null]}>
          {!!item.content && <Text style={[styles.messageText, item.role === 'user' && styles.userText]}>{item.content}</Text>}
          {item.attachment_url && item.attachment_type === 'image' ? (
            <Image source={{ uri: api.resolveAttachmentUrl(item.attachment_url) }} style={styles.image} />
          ) : null}
          {item.role === 'assistant' && ui.cards.length > 0 ? <View style={styles.cardStack}>{ui.cards.map(renderCard)}</View> : null}
        </View>
      </View>
    );
  };

  const quickActions = useMemo(
    () => [
      { id: 'plan', label: 'show me my plan' },
      { id: 'calories', label: 'show my calories today' },
      { id: 'progress', label: 'show my progress' },
      { id: 'workout', label: 'start my workout' },
    ],
    []
  );

  if (!bootstrapped) {
    return (
      <View style={styles.loadingWrap}>
        <ActivityIndicator color={colors.foreground} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(_, i) => String(i)}
        renderItem={renderMessage}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        showsVerticalScrollIndicator={false}
      />

      <View style={styles.quickRow}>
        {quickActions.map(action => (
          <TouchableOpacity key={action.id} style={styles.quickChip} onPress={() => sendMessage(action.label)} activeOpacity={0.75}>
            <Text style={styles.quickChipText}>{action.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.inputWrap}>
        <TextInput
          style={styles.input}
          placeholder="Message Fitmax coach..."
          placeholderTextColor={colors.textMuted}
          value={input}
          onChangeText={setInput}
          multiline
        />
        <TouchableOpacity style={[styles.send, !input.trim() && styles.sendDisabled]} onPress={() => sendMessage()} disabled={!input.trim() || loading}>
          {loading ? <ActivityIndicator color={colors.buttonText} size="small" /> : <Ionicons name="send" size={16} color={colors.buttonText} />}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  listContent: { padding: spacing.md, paddingBottom: spacing.sm },
  row: { marginBottom: spacing.sm, alignItems: 'flex-start' },
  userRow: { alignItems: 'flex-end' },
  bubble: {
    maxWidth: '90%',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    ...shadows.sm,
  },
  aiBubble: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
  userBubble: { backgroundColor: colors.foreground },
  coachingBubble: { borderLeftWidth: 3, borderLeftColor: '#0f766e' },
  messageText: { ...typography.bodySmall, color: colors.foreground },
  userText: { color: colors.buttonText },
  typing: { ...typography.caption, color: colors.textMuted },
  image: { width: 180, height: 140, borderRadius: 12, marginTop: spacing.sm },
  cardStack: { marginTop: spacing.sm, gap: spacing.sm },
  inlineCard: {
    borderRadius: 14,
    padding: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  inlineCardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  inlineTitle: { fontSize: 13, fontWeight: '700', color: colors.foreground },
  inlineSubtitle: { ...typography.caption, marginTop: 4 },
  inlineCta: { marginTop: 6, fontSize: 12, fontWeight: '600', color: '#0f766e' },
  quickRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  quickChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  quickChipText: { fontSize: 11, color: colors.textSecondary },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    margin: spacing.md,
    marginTop: 0,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  input: { flex: 1, fontSize: 14, color: colors.textPrimary, maxHeight: 90, paddingHorizontal: 8 },
  send: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.foreground, alignItems: 'center', justifyContent: 'center' },
  sendDisabled: { opacity: 0.45 },
});
