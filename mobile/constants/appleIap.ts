import Constants from 'expo-constants';

type Extra = {
    appleIapBasicProductId?: string;
    appleIapPremiumProductId?: string;
};

const extra = (Constants.expoConfig?.extra ?? {}) as Extra;

/** Must match App Store Connect + backend `apple_iap_product_id_*`. */
export const APPLE_IAP_BASIC_SKU =
    process.env.EXPO_PUBLIC_APPLE_IAP_BASIC_PRODUCT_ID?.trim() ||
    extra.appleIapBasicProductId ||
    'com.cannon.mobile.subscribe.basic.weekly';

export const APPLE_IAP_PREMIUM_SKU =
    process.env.EXPO_PUBLIC_APPLE_IAP_PREMIUM_PRODUCT_ID?.trim() ||
    extra.appleIapPremiumProductId ||
    'com.cannon.mobile.subscribe.premium.weekly';

export const APPLE_IAP_PRODUCT_IDS = [APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU] as const;
