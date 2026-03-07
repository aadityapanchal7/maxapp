import { Platform } from 'react-native';

// TypeScript doesn't resolve Expo's platform extensions (e.g. .native/.web) by default.
// We use a tiny runtime switch so both web + native builds pick the right implementation.
const FaceGuide3D =
    Platform.OS === 'web'
        ? // eslint-disable-next-line @typescript-eslint/no-require-imports
          require('./FaceGuide3D.web').default
        : // eslint-disable-next-line @typescript-eslint/no-require-imports
          require('./FaceGuide3D.native').default;

export default FaceGuide3D as typeof import('./FaceGuide3D.native').default;

