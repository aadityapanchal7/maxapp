import React, { Suspense, lazy } from 'react';
import { Platform, View, ActivityIndicator, StyleProp, ViewStyle } from 'react-native';

export type FaceGuide3DProps = {
    timer: number;
    active?: boolean;
    style?: StyleProp<ViewStyle>;
    width?: number;
    height?: number;
};

const FaceGuide3DInner = lazy(() =>
    Platform.OS === 'web' ? import('./FaceGuide3D.web') : import('./FaceGuide3D.native'),
);

export default function FaceGuide3D(props: FaceGuide3DProps) {
    const h = props.height ?? 320;
    return (
        <Suspense
            fallback={
                <View style={[props.style, { minHeight: h, justifyContent: 'center', alignItems: 'center' }]}>
                    <ActivityIndicator />
                </View>
            }
        >
            <FaceGuide3DInner {...props} />
        </Suspense>
    );
}
