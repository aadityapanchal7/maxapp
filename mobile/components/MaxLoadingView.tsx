import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function MaxLoadingView() {
    return (
        <View style={styles.root} accessibilityLabel="Loading">
            <Text style={styles.word}>max</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    root: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#F5F5F3',
    },
    word: {
        fontSize: 44,
        fontWeight: '300',
        color: '#0A0A0A',
        letterSpacing: -1,
    },
});
