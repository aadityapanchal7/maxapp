import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import api from '../services/api';

// Open the Google Calendar OAuth consent flow.
//
// Primary: openAuthSessionAsync — the native "<App> Wants to Use google.com to
// Sign In" sheet (ASWebAuthenticationSession on iOS / Chrome Custom Tab on
// Android) that AUTO-CLOSES the moment the backend callback redirects to our app
// scheme (cannon://google-connected, per app.json).
//
// Fallback: on some builds / OS states openAuthSessionAsync can throw or fail to
// present (returns 'locked'). In that case we open a plain in-app browser sheet
// (SFSafariViewController), which reliably opens; the caller's status poll then
// detects the connection. Either way the button always DOES something rather
// than silently no-op-ing.
// `includeWrite` additionally requests permission to create a "Max" calendar
// and put the routine in it. Existing users linked before routine-sync existed
// and hold a read-only grant, so enabling it re-runs consent — Google always
// re-prompts here (the backend sends prompt=consent), and the extra scope is
// calendar.app.created: write access to calendars WE make, never the user's own.
export async function openGoogleCalendarAuth(
    includeGmail = false,
    includeWrite = false,
): Promise<void> {
    const returnUrl = Linking.createURL('google-connected');
    const { auth_url } = await api.getGoogleAuthUrl(includeGmail, returnUrl, includeWrite);
    if (!auth_url) {
        throw new Error('The server did not return a Google sign-in URL.');
    }

    try {
        const res = await WebBrowser.openAuthSessionAsync(auth_url, returnUrl);
        // 'locked' = another auth session is already in progress and this one
        // never presented — fall back so the user isn't stuck on nothing.
        if (res.type === 'locked') {
            await WebBrowser.openBrowserAsync(auth_url);
        }
    } catch {
        // openAuthSessionAsync threw (couldn't present the native sheet). Open a
        // regular browser sheet instead — it always opens; the poll finishes it.
        await WebBrowser.openBrowserAsync(auth_url);
    }
}
