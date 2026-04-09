import React, { useEffect, useRef } from 'react';
import { View, Animated, StyleSheet, Easing } from 'react-native';

export default function MaxLoadingView() {
    const opacity = useRef(new Animated.Value(0)).current;
    const barWidth = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        Animated.timing(opacity, {
            toValue: 1,
            duration: 600,
            easing: Easing.out(Easing.cubic),
            useNativeDriver: true,
        }).start();

        Animated.loop(
            Animated.sequence([
                Animated.timing(barWidth, {
                    toValue: 1,
                    duration: 1400,
                    easing: Easing.inOut(Easing.cubic),
                    useNativeDriver: false,
                }),
                Animated.timing(barWidth, {
                    toValue: 0,
                    duration: 1400,
                    easing: Easing.inOut(Easing.cubic),
                    useNativeDriver: false,
                }),
            ]),
        ).start();
    }, [opacity, barWidth]);

    const animatedWidth = barWidth.interpolate({
        inputRange: [0, 1],
        outputRange: ['0%', '100%'],
    });

    return (
        <View style={s.root} accessibilityLabel="Loading">
            <Animated.Text style={[s.word, { opacity }]}>max</Animated.Text>
            <View style={s.trackWrap}>
                <Animated.View style={[s.track, { opacity }]}>
                    <Animated.View style={[s.fill, { width: animatedWidth }]} />
                </Animated.View>
            </View>
        </View>
    );
}

const s = StyleSheet.create({
    root: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#F5F5F3',
    },
    word: {
        fontFamily: 'PlayfairDisplay',
        fontSize: 32,
        fontWeight: '400',
        color: '#0A0A0A',
        letterSpacing: 6,
        textTransform: 'lowercase',
    },
    trackWrap: {
        marginTop: 20,
        width: 48,
        height: 1,
    },
    track: {
        width: '100%',
        height: 1,
        backgroundColor: '#E0DED8',
        overflow: 'hidden',
    },
    fill: {
        height: '100%',
        backgroundColor: '#0A0A0A',
    },
});
