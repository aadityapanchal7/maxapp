/**
 * Remote images with disk + memory cache (expo-image).
 * Use React Native Image for local `require()` assets.
 */
import React from 'react';
import { Image as ExpoImage, type ImageProps as ExpoImageProps } from 'expo-image';
import type { StyleProp, ImageStyle } from 'react-native';

type Props = Omit<ExpoImageProps, 'source'> & {
    uri?: string | null;
    style?: StyleProp<ImageStyle>;
    contentFit?: 'cover' | 'contain' | 'fill' | 'scale-down';
};

export function CachedImage({ uri, style, contentFit = 'cover', ...rest }: Props) {
    if (!uri) return null;
    return (
        <ExpoImage
            source={{ uri }}
            style={style}
            contentFit={contentFit}
            transition={150}
            cachePolicy="memory-disk"
            {...rest}
        />
    );
}
