import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

/** White screen with black “max” — app boot / auth loading. */
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
        backgroundColor: '#FFFFFF',
    },
    word: {
        fontSize: 40,
        fontWeight: '600',
        color: '#000000',
        letterSpacing: -0.5,
    },
});
