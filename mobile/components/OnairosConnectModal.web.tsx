/**
 * OnairosConnectModal — web no-op stub.
 *
 * The native modal pulls in @onairos/react-native which transitively imports
 * @react-native-google-signin/google-signin. That dependency has no web
 * implementation, and the static import chain breaks Metro's web bundle even
 * though the modal's runtime guard would have skipped rendering on web.
 *
 * This `.web.tsx` extension makes Expo's bundler pick this stub on the web
 * platform target instead of the native module — same exported shape, zero
 * native deps, zero render. Onairos consent stays mobile-only by design.
 */

import React from 'react';

export type OnairosConnectModalProps = {
    visible: boolean;
    onClose: () => void;
    onConnected?: (result: { initialTraits?: any }) => void;
};

export default function OnairosConnectModal(_props: OnairosConnectModalProps): React.ReactElement | null {
    return null;
}
