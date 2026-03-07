import React, { useMemo, useRef } from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

type Props = {
    timer: number;
    active?: boolean;
    style?: ViewStyle;
    width?: number;
    height?: number;
};

function getTargetRotationDeg(timer: number) {
    if (timer >= 0 && timer < 4) return 0; // front
    if (timer >= 4 && timer < 8) return 40; // left
    if (timer >= 8 && timer < 11) return 0; // back to front
    return -40; // right
}

function HeadGuide({ targetYRad, active }: { targetYRad: number; active: boolean }) {
    const meshRef = useRef<THREE.Mesh>(null);
    const opacity = active ? 0.35 : 0.18;

    useFrame((_, delta) => {
        const mesh = meshRef.current;
        if (!mesh) return;
        mesh.rotation.y = THREE.MathUtils.damp(mesh.rotation.y, targetYRad, 8, delta);
    });

    return (
        <mesh ref={meshRef} position={[0, -0.08, 0]} scale={[0.92, 1.18, 0.9]}>
            <sphereGeometry args={[1.0, 36, 36]} />
            <meshStandardMaterial
                color="#ffffff"
                transparent
                opacity={opacity}
                wireframe
                depthWrite={false}
            />
        </mesh>
    );
}

export default function FaceGuide3D({
    timer,
    active = true,
    style,
    width = 250,
    height = 320,
}: Props) {
    const targetYRad = useMemo(() => (getTargetRotationDeg(timer) * Math.PI) / 180, [timer]);

    return (
        <View style={[styles.container, style]} pointerEvents="none">
            <View style={[styles.stage, { width, height }]}>
                <Canvas
                    style={StyleSheet.absoluteFill as any}
                    dpr={[1, 2]}
                    gl={{ alpha: true, antialias: true }}
                    camera={{ position: [0, 0, 4], fov: 45 }}
                >
                    <ambientLight intensity={0.9} />
                    <directionalLight position={[2, 3, 6]} intensity={1.2} />
                    <pointLight position={[-3, -2, 3]} intensity={0.6} />
                    <HeadGuide targetYRad={targetYRad} active={active} />
                </Canvas>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'center',
        alignItems: 'center',
    },
    stage: {
        position: 'relative',
        backgroundColor: 'transparent',
    },
});

