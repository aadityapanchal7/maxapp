import type { LegalBlock } from './legalTypes';
import { APPLE_APP_REVIEW_BUSINESS, APPLE_APP_REVIEW_LEGAL, APPLE_APP_REVIEW_SAFETY } from './legalConstants';

/** Privacy policy — March 23, 2026 (in-app; cross-page HTML links removed). */
export const privacyBlocks: LegalBlock[] = [
    {
        type: 'meta',
        text: 'Effective March 23, 2026 · Last updated April 21, 2026 · App: Max (iOS/Android bundle: com.cannon.mobile)',
    },
    {
        type: 'p',
        text:
            'This Privacy Policy describes how the operator of Max (“Max,” “we,” “us,” or “our”) collects, uses, discloses, stores, and protects personal information when you use our mobile applications, websites, APIs, and related services (collectively, the “Services”). By using the Services, you acknowledge this policy. If you do not agree, do not use the Services.',
    },
    {
        type: 'callout',
        title: 'App Store alignment',
        text:
            'This policy is published and linked inside the Max app and should match the Privacy Policy URL you provide in App Store Connect. If your app supports account creation, Max provides in-app account deletion (see Account deletion below).',
    },
    { type: 'external', label: 'App Review Guidelines — Legal (Apple)', url: APPLE_APP_REVIEW_LEGAL },

    { type: 'h2', text: '1. Who we are (data controller)' },
    {
        type: 'p',
        text:
            'The data controller responsible for personal information processed through the Services is Amma Health Inc., with its principal place of business at 1481 Peralta Boulevard, Fremont, California, USA.',
    },
    { type: 'mailtoLine', before: 'You can contact us about privacy at ', after: '.' },
    {
        type: 'p',
        text:
            'We will respond to verified requests within a reasonable time and as required by applicable law. We may need to verify your identity before fulfilling certain requests.',
    },

    { type: 'h2', text: '2. Scope' },
    { type: 'p', text: 'This policy applies to:' },
    {
        type: 'bullets',
        items: [
            'The Max mobile app (iOS and Android).',
            'Our websites and web-hosted legal or marketing pages.',
            'Backend services that power accounts, subscriptions, community features, coaching or AI-assisted features, uploads, and support.',
        ],
    },
    {
        type: 'p',
        text: 'It does not apply to third-party sites or services that we link to; their policies govern those services.',
    },

    { type: 'h2', text: '3. Information we collect' },
    { type: 'p', text: 'We collect information in the categories below. The exact data depends on which features you use.' },

    { type: 'h3', text: '3.1 You provide directly' },
    {
        type: 'bullets',
        items: [
            'Account and profile: email address; password (stored using one-way hashing—we do not store your plain-text password); first and last name; username; optional bio; phone number where required for account or SMS features; profile and progress photos you choose to upload.',
            'Community and messaging: text, images, and other content you post in channels, chat, or similar features.',
            'Camera and media: when you use camera, photo library, or microphone permissions, you may submit images, video, or audio for features such as face scans, progress tracking, or attachments. Submission is voluntary except where a feature cannot function without it.',
            'Payments: when you pay through Apple, Google, or our card processor, we receive transaction-related identifiers and status from the payment provider—not your full card number on our servers.',
            'Support: information you include in emails, forms, or in-app support requests.',
            'Onboarding and preferences: answers or settings you provide in questionnaires (for example goals, experience level, lifestyle fields) where the product collects them.',
        ],
    },

    { type: 'h3', text: '3.2 Automatically collected' },
    {
        type: 'bullets',
        items: [
            'Device and technical data: device type, operating system, app version, language, IP address, timestamps, crash or diagnostic logs, and security-related events.',
            'Usage data: interactions with features, session information, and aggregated analytics where enabled.',
            'Authentication tokens: tokens or cookies used to keep you signed in on web, where applicable.',
        ],
    },

    { type: 'h3', text: '3.3 From third parties' },
    {
        type: 'bullets',
        items: [
            'App stores: Apple and Google may provide limited purchase, refund, or subscription status information according to their terms.',
            'Payment processors: Stripe or similar may share payment outcome and fraud signals.',
            'When you sign in through a third party (if offered): basic profile details as authorized by that provider.',
        ],
    },

    { type: 'h3', text: '3.4 Sensitive or special categories' },
    {
        type: 'p',
        text:
            'Max may process photos or wellness-related information you choose to provide. We do not use the app to provide regulated medical diagnosis or treatment. Do not submit information you consider highly sensitive if you are uncomfortable with processing described here and in the app’s permission prompts.',
    },

    { type: 'h2', text: '4. How we use information (purposes)' },
    { type: 'p', text: 'We use personal information to:' },
    {
        type: 'bullets',
        items: [
            'Create and maintain your account, authenticate you, and provide core app functionality.',
            'Operate community features, including moderation, safety, reporting, and enforcement of our Terms of Service and Community Guidelines.',
            'Process purchases and subscriptions, prevent fraud, and comply with tax or accounting obligations.',
            'Provide AI-assisted or automated features (for example coaching, scan-related insights, or content suggestions) where enabled, including by sending necessary inputs to subprocessors described below.',
            'Store and deliver files you upload (for example images) using cloud storage.',
            'Send service-related messages (for example security alerts, receipts, or important policy updates) and, where you opt in, marketing or product updates.',
            'Improve reliability, security, and performance of the Services; conduct analytics in aggregated or de-identified form where permitted.',
            'Comply with law, respond to lawful requests, and enforce our agreements.',
        ],
    },
    {
        type: 'callout',
        title: 'Not medical advice',
        text:
            'Outputs in Max are for general wellness and education only, not a substitute for professional medical advice, diagnosis, or treatment.',
    },
    { type: 'external', label: 'App Review Guidelines — Legal (Apple, health-related expectations)', url: APPLE_APP_REVIEW_LEGAL },

    { type: 'h2', text: '5. Legal bases (EEA, UK, Switzerland, and similar)' },
    {
        type: 'p',
        text:
            'Where GDPR or similar laws apply, we rely on: performance of a contract (providing the Services); legitimate interests (security, fraud prevention, product improvement, balanced against your rights); consent where required (for example optional marketing or non-essential cookies on web); and legal obligation where applicable.',
    },

    { type: 'h2', text: '6. How we share information and subprocessors' },
    {
        type: 'p',
        text:
            'We share personal information with service providers (“subprocessors”) who process data on our behalf under contracts that require appropriate security and use only for our instructions. We require that they protect personal information consistently with this policy and applicable law.',
    },
    { type: 'p', text: 'Categories of recipients may include:' },
    {
        type: 'bullets',
        items: [
            'Cloud databases and hosting: for example PostgreSQL providers (such as Supabase) and related infrastructure for user accounts and app data.',
            'Additional data stores: for example shared or forum-related data on separate database infrastructure (such as AWS RDS) where the product architecture uses it.',
            'File storage: for example Amazon S3 or comparable object storage for uploads (avatars, progress photos, attachments).',
            'Payments: Apple App Store / Google Play billing for in-app purchases; Stripe (or similar) for web or non-store payments where used.',
            'Messaging: Twilio or similar SMS providers for verification, password reset, or notifications where enabled.',
            'AI and analysis: Google (Gemini) or other model providers for generating or processing text; separate facial or image analysis services where you use scan features that depend on an external API.',
            'Analytics, logging, and security: tools used to monitor errors, performance, or abuse, subject to configuration and consent where required.',
        ],
    },
    {
        type: 'p',
        text:
            'We may also share information: (a) with other users as part of community features you use; (b) if required by law or to protect rights, safety, and security; (c) with professional advisers under confidentiality; (d) in connection with a merger, acquisition, or asset transfer, with notice where required by law.',
    },
    {
        type: 'p',
        text:
            'Sale / sharing (U.S. state laws): We do not sell personal information for money in the traditional sense. Where state laws define “sale” or “sharing” to include certain advertising or analytics disclosures, we honor applicable opt-out rights and describe choices below.',
    },

    { type: 'h2', text: '7. Face scans, images, and AI processing' },
    {
        type: 'p',
        text:
            'This section explains, in detail, how Max handles face data. It applies whenever you use the in-app face-scan feature (front, left, and right photos of your face) or otherwise upload facial images. It is intended to address Apple App Review Guideline 2.1 and 5.1.1 requirements for transparency about face data.',
    },
    { type: 'h3', text: '7.1 What face data we collect' },
    {
        type: 'p',
        text:
            'When you initiate a face scan, the app captures three still photographs of your face (front, left profile, and right profile). These photographs are uploaded to our servers. From those photographs we derive numerical facial landmark coordinates (using Google’s on-server MediaPipe Face Landmarker model — up to 478 non-identifying (x, y, z) coordinate points per image) and a set of derived geometric measurements (for example proportions, symmetry, and angle scores). We do not compute or store a biometric “faceprint,” template, or other unique identifier intended to identify a specific individual from the image, and we do not use Apple’s Face ID, the TrueDepth API, or any Apple biometric framework. The face-scan feature is entirely optional; you can use the rest of the app without submitting any face images.',
    },
    { type: 'h3', text: '7.2 How we use face data' },
    {
        type: 'p',
        text:
            'We use face photographs and the derived landmark and measurement data solely to generate the wellness, aesthetic, and coaching feedback you request inside Max — for example symmetry scores, proportion feedback, posture or facial-training suggestions, and AI-generated coaching content about your own scan. We do not use face data to identify, authenticate, track, or recognize you across services; we do not use it for advertising, marketing, or profiling; we do not sell it; and we do not use it to train general-purpose machine-learning models for third parties.',
    },
    { type: 'h3', text: '7.3 Third parties and where face data is stored' },
    {
        type: 'p',
        text:
            'Face images are stored as private objects in Amazon Web Services S3 (Amazon S3) under our account, accessible only to Max backend services and authenticated administrative access. The derived landmark coordinates and measurement scores are stored alongside your user record in our primary application database (PostgreSQL, hosted with Supabase; some shared or forum data on AWS RDS). Face landmark detection runs server-side on our own infrastructure using the MediaPipe Face Landmarker model. To produce natural-language feedback about a scan, we may send the face image and/or its derived measurement values to a large language model provider (currently Google Gemini; where configured, OpenAI) strictly for per-request inference; those providers act as subprocessors under their published terms and do not receive the data for training general models on our behalf. Face data is not shared with any advertising network, data broker, or analytics provider.',
    },
    { type: 'h3', text: '7.4 Retention of face data' },
    {
        type: 'p',
        text:
            'Face images and the derived landmark and measurement data are retained only while your account is active and the scan remains in your history. You can delete an individual scan at any time from within the app; deletion removes the associated images from our storage and the scan record from our database (subject to limited backup retention described in section 8 Retention). When you delete your Max account, all face images, landmark data, and derived scan measurements associated with your account are deleted or anonymized, subject to the same limited backup and legal-retention exceptions.',
    },
    { type: 'h3', text: '7.5 Consent, disclosure, and user control' },
    {
        type: 'p',
        text:
            'Before you take a face scan, Max requests camera permission with a clear on-device prompt that explains the data will be used for face analysis and wellness feedback, and the scan flow in the app shows what will be submitted. You can revoke camera access at any time in your device settings, delete individual scans from the app, and delete your account and all face data as described in section 9.1 Account deletion. We do not use HealthKit or Apple health APIs for the face-scan feature.',
    },
    {
        type: 'p',
        text:
            'Max does not provide medical diagnosis or treatment. Outputs from face scans are general wellness and aesthetic feedback only and must not be relied on for medical purposes. Do not use the Services to obtain regulated medical measurements that the app does not support.',
    },

    { type: 'h2', text: '8. Retention' },
    {
        type: 'p',
        text:
            'We retain personal information for as long as your account is active, as needed to provide the Services, and as required by law (for example tax, fraud prevention, or dispute resolution). When you delete your account, we delete or anonymize personal information unless a limited exception applies (for example backups for a short period, financial records, or information we must retain to comply with law or enforce our terms). Community content may be removed or anonymized as described in-app (for example posts may show as deleted).',
    },

    { type: 'h2', text: '9. Your choices and rights' },
    { type: 'p', text: 'Depending on your location, you may have the right to:' },
    {
        type: 'bullets',
        items: [
            'Access, correct, or update your information (many edits are available in-app).',
            'Delete your account or request deletion of personal information, subject to exceptions above.',
            'Object to or restrict certain processing, or withdraw consent where processing is consent-based.',
            'Data portability where applicable.',
            'Opt out of certain analytics or targeted advertising, including via device settings (iOS App Tracking Transparency where applicable) and cookie choices on web.',
            'Lodge a complaint with a supervisory authority in your country.',
        ],
    },
    { type: 'mailtoLine', before: 'To exercise rights, use in-app settings where available or email ', after: '. We may verify your identity before responding.' },

    { type: 'h3', text: '9.1 Account deletion' },
    {
        type: 'p',
        text:
            'If the app offers account deletion, you can initiate deletion from the in-app profile or account settings. Deletion is permanent for the account and associated personal data except where we must retain limited information as described in Retention above. If you cannot complete deletion in-app (for example a technical error), contact us using the email below with the email address on your account.',
    },
    { type: 'external', label: 'App Review Guidelines — Guideline 5.1.1 (Apple)', url: APPLE_APP_REVIEW_LEGAL },

    { type: 'h3', text: '9.2 U.S. state privacy rights (summary)' },
    {
        type: 'p',
        text:
            'Residents of certain U.S. states (including California, Colorado, Virginia, and others as laws evolve) may have additional rights to know, delete, correct, and opt out of certain “sales” or “sharing” of personal information. Submit requests via the email above. We will not discriminate against you for exercising privacy rights where prohibited by law.',
    },

    { type: 'h2', text: '10. Children' },
    {
        type: 'p',
        text:
            'The Services are not directed to children under 13 (or the minimum digital consent age in your jurisdiction). We do not knowingly collect personal information from children. If you believe a child has provided us personal information, contact us and we will take steps to delete it.',
    },

    { type: 'h2', text: '11. International transfers' },
    {
        type: 'p',
        text:
            'We may process and store information in the United States and other countries. Where required, we use appropriate safeguards (such as Standard Contractual Clauses) for transfers from the EEA, UK, or Switzerland.',
    },

    { type: 'h2', text: '12. Security' },
    {
        type: 'p',
        text:
            'We implement technical and organizational measures designed to protect personal information against unauthorized access, loss, or alteration. No method of transmission or storage is completely secure; we cannot guarantee absolute security.',
    },

    { type: 'h2', text: '13. User-generated content and safety (UGC)' },
    {
        type: 'p',
        text:
            'Where the Services include user-generated content, we provide mechanisms to report content and block users, and we apply moderation and enforcement measures consistent with our Community Guidelines.',
    },
    { type: 'external', label: 'App Review Guidelines — Guideline 1.2 (Apple)', url: APPLE_APP_REVIEW_LEGAL },
    {
        type: 'p',
        text: 'We may use automated or human review to help detect policy violations; false positives can be appealed via support.',
    },

    { type: 'h2', text: '14. Third-party links' },
    {
        type: 'p',
        text: 'Links to third-party websites or services are governed by those parties’ policies. Review them before providing personal information.',
    },

    { type: 'h2', text: '15. Changes to this policy' },
    {
        type: 'p',
        text:
            'We may update this Privacy Policy. We will post the revised policy with a new effective date. If changes are material, we will provide additional notice as required by law or through the app. Continued use after the effective date may constitute acceptance where permitted by law.',
    },

    { type: 'h2', text: '16. Contact' },
    { type: 'p', text: 'Privacy questions and requests:' },
    { type: 'mailtoLine', before: '', after: '' },
];

export const termsBlocks: LegalBlock[] = [
    { type: 'meta', text: 'Effective March 23, 2026 · App: Max (com.cannon.mobile)' },
    {
        type: 'p',
        text:
            'These Terms of Service (“Terms”) govern your access to and use of Max’s mobile applications, websites, and related services (the “Services”). By creating an account, accessing, or using the Services, you agree to these Terms. If you do not agree, do not use the Services.',
    },
    {
        type: 'p',
        text: 'The Services are operated by Amma Health Inc., 1481 Peralta Boulevard, Fremont, California, USA.',
    },
    {
        type: 'callout',
        title: 'Account controls',
        text:
            'Max includes in-app controls for support, legal documents, and account deletion. If deletion is unavailable due to a temporary issue, email us using the address below.',
    },
    { type: 'mailtoLine', before: '', after: '' },

    { type: 'h2', text: '1. Eligibility' },
    {
        type: 'p',
        text:
            'You must be old enough to form a binding contract in your jurisdiction and meet any minimum age we specify in the app or app store listing. If you use the Services on behalf of an organization, you represent that you have authority to bind that organization.',
    },

    { type: 'h2', text: '2. Accounts and security' },
    {
        type: 'p',
        text:
            'You are responsible for your account credentials and for all activity under your account. Notify us promptly if you suspect unauthorized access. We may suspend or terminate accounts that violate these Terms or create risk.',
    },
    { type: 'mailtoLine', before: 'Contact: ', after: '' },

    { type: 'h2', text: '3. The Services' },
    {
        type: 'p',
        text:
            'Max provides software, content, and community features aimed at general wellness, education, and engagement. We may modify, suspend, or discontinue features with reasonable notice where practicable.',
    },
    {
        type: 'callout',
        title: 'Medical disclaimer',
        text:
            'The Services are not medical devices and do not provide medical advice, diagnosis, or treatment. Always seek the advice of a qualified health provider with any questions about a medical condition. Never disregard professional advice because of something you read or see in Max.',
    },

    { type: 'h2', text: '4. App Store and Play Store distribution' },
    {
        type: 'p',
        text:
            'If you download Max from the Apple App Store, you acknowledge that these Terms are between you and Max, not Apple. Apple is not responsible for the Services or their content. Apple has no obligation to furnish maintenance or support for Max. To the maximum extent permitted by law, Apple has no warranty obligation regarding Max. Apple is not responsible for addressing claims by you or third parties relating to Max (including product liability, legal or regulatory failure, or consumer protection claims). In the event of a third-party claim that Max infringes intellectual property rights, Max (not Apple) is responsible for investigation, defense, settlement, and discharge of that claim. Apple and its subsidiaries are third-party beneficiaries of these Terms solely as they relate to your use of the iOS version obtained through the App Store, and Apple may enforce those provisions. You must also comply with applicable third-party terms when using the Services (for example store rules and payment terms).',
    },
    {
        type: 'p',
        text:
            'If you obtain Max from Google Play, Google may apply additional terms; where those terms address distribution, billing, or refunds through Google Play, they may govern those specific topics.',
    },

    { type: 'h2', text: '5. Subscriptions and payments' },
    {
        type: 'p',
        text:
            'Some features may require a paid subscription or one-time purchase. Prices, billing cycles, and taxes are shown at checkout or in the app store. On iPhone, Max’s subscription is purchased through Apple’s In-App Purchase system; on Android, subscriptions may be billed through Stripe or Google Play depending on how you subscribe. Their terms also apply. Unless stated otherwise or required by law, fees are non-refundable. You may cancel or change subscriptions in your Apple ID Subscriptions (iOS), Google Play (Android), or through Stripe where that flow is offered.',
    },
    {
        type: 'p',
        text:
            'Auto-renewable subscriptions continue until you cancel in your Apple ID or Google Play account settings (or end a Stripe-billed plan where applicable). Before you subscribe, the app and store checkout should show what you receive each period, the price, and how to cancel. On iOS, if you reinstall Max or use a new device, use Restore Purchases where the app offers it to reconnect an existing App Store subscription to your Max account.',
    },
    { type: 'external', label: 'App Review Guidelines — Subscriptions (Apple)', url: APPLE_APP_REVIEW_BUSINESS },

    { type: 'h2', text: '6. User content and license' },
    {
        type: 'p',
        text:
            'You retain rights to content you submit (“User Content”). You grant Max a worldwide, non-exclusive, royalty-free license to host, store, reproduce, display, and distribute User Content solely to operate, improve, promote, and secure the Services, including moderation and safety. You represent that you have the rights needed to grant this license.',
    },
    {
        type: 'p',
        text:
            'You are responsible for your User Content. We may remove or restrict content that violates these Terms, our Community Guidelines, or applicable law.',
    },

    { type: 'h2', text: '7. Community and safety' },
    {
        type: 'p',
        text:
            'Community channels, chat, and similar features must be used lawfully and respectfully. You agree to follow our Community Guidelines. We provide tools such as reporting and blocking where available; we do not guarantee monitoring of all content.',
    },

    { type: 'h2', text: '8. Prohibited conduct' },
    { type: 'p', text: 'You agree not to:' },
    {
        type: 'bullets',
        items: [
            'Violate law or infringe others’ rights (including intellectual property and privacy).',
            'Harass, threaten, defraud, or harm others; post hate speech or illegal content.',
            'Spam, scrape, overload, or attempt unauthorized access to our systems or other users’ accounts.',
            'Reverse engineer, circumvent security, or misuse the Services or APIs.',
            'Use the Services to build a competing product using our data or interfaces without permission.',
            'Misrepresent your identity or affiliation.',
        ],
    },

    { type: 'h2', text: '9. Intellectual property' },
    {
        type: 'p',
        text:
            'Max and its licensors own the Services, branding, and content we create, subject to the licenses we expressly grant you. Except as allowed by law or these Terms, you may not copy, modify, or distribute our proprietary materials without consent.',
    },

    { type: 'h2', text: '10. Copyright / DMCA' },
    {
        type: 'p',
        text:
            'If you believe content on the Services infringes your copyright, send a notice with the information required by applicable law (for example, identification of the work, the material, and your contact details). We may remove or disable access to allegedly infringing material and terminate repeat infringers where appropriate.',
    },
    { type: 'mailtoLine', before: 'Send notices to: ', after: '' },

    { type: 'h2', text: '11. Third-party services' },
    {
        type: 'p',
        text:
            'The Services may integrate third-party services (analytics, maps, auth, etc.). Their terms and privacy policies govern those services.',
    },

    { type: 'h2', text: '12. Disclaimers' },
    {
        type: 'p',
        text:
            'THE SERVICES ARE PROVIDED “AS IS” AND “AS AVAILABLE.” TO THE MAXIMUM EXTENT PERMITTED BY LAW, MAX DISCLAIMS ALL WARRANTIES, WHETHER EXPRESS, IMPLIED, OR STATUTORY, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT. WE DO NOT WARRANT UNINTERRUPTED OR ERROR-FREE OPERATION.',
    },

    { type: 'h2', text: '13. Limitation of liability' },
    {
        type: 'p',
        text:
            'TO THE MAXIMUM EXTENT PERMITTED BY LAW, MAX AND ITS AFFILIATES, OFFICERS, DIRECTORS, EMPLOYEES, AND AGENTS WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS, DATA, GOODWILL, OR OTHER INTANGIBLE LOSSES, ARISING FROM YOUR USE OF THE SERVICES. OUR AGGREGATE LIABILITY FOR CLAIMS RELATING TO THE SERVICES WILL NOT EXCEED THE GREATER OF (A) THE AMOUNTS YOU PAID TO MAX FOR THE SERVICES IN THE TWELVE MONTHS BEFORE THE CLAIM OR (B) ONE HUNDRED U.S. DOLLARS (US$100), EXCEPT WHERE PROHIBITED BY LAW.',
    },

    { type: 'h2', text: '14. Indemnity' },
    {
        type: 'p',
        text:
            'You will defend and indemnify Max and its affiliates against claims, damages, losses, and expenses (including reasonable attorneys’ fees) arising from your User Content, your use of the Services, or your violation of these Terms or law.',
    },

    { type: 'h2', text: '15. Termination' },
    {
        type: 'p',
        text:
            'You may stop using the Services at any time. We may suspend or terminate access for violations, risk, or operational reasons. Provisions that by their nature should survive (including intellectual property, disclaimers, limitations, indemnity, and governing law) will survive termination. Where the app offers account deletion, use those controls or contact support; some information may be retained as described in our Privacy Policy.',
    },

    { type: 'h2', text: '16. Governing law and disputes' },
    {
        type: 'p',
        text:
            'These Terms are governed by the laws of the United States and the State of Delaware, excluding conflict-of-law rules, unless mandatory local law requires otherwise. Courts in Delaware (or another forum we specify in writing) have exclusive jurisdiction, except where consumer protection law gives you the right to bring claims in your home jurisdiction. If you are in the EU, UK, or other regions with mandatory rights, nothing in these Terms limits those rights.',
    },

    { type: 'h2', text: '17. Changes' },
    {
        type: 'p',
        text:
            'We may update these Terms. We will post the new Terms and update the effective date. Continued use after the effective date constitutes acceptance, except where stricter notice is required by law.',
    },

    { type: 'h2', text: '18. Contact' },
    { type: 'mailtoLine', before: '', after: '' },
];

export const communityBlocks: LegalBlock[] = [
    { type: 'meta', text: 'Effective March 23, 2026 · Channels, chat, and user-generated content in Max' },
    {
        type: 'p',
        text:
            'Max includes community areas where users can share text and media. These guidelines (“Guidelines”) work together with our Terms of Service and Privacy Policy. Violations may result in content removal, account restrictions, or termination.',
    },
    {
        type: 'callout',
        title: 'Safety tools',
        text:
            'Max provides mechanisms to report content, block abusive users, and contact support. We review reports and take action according to policy and law.',
    },
    { type: 'external', label: 'App Review Guideline 1.2 — Safety (Apple)', url: APPLE_APP_REVIEW_SAFETY },

    { type: 'h2', text: '1. Be respectful' },
    {
        type: 'p',
        text:
            'Treat others with respect. Disagreement is fine; harassment, bullying, threats, hate speech, slurs, or targeting individuals or groups is not allowed.',
    },

    { type: 'h2', text: '2. Keep it legal' },
    {
        type: 'p',
        text:
            'Do not post or solicit content that is illegal where you or others are located. This includes child sexual abuse material, non-consensual intimate imagery, trafficking, fraud, sale of illegal goods, or instructions for serious harm.',
    },

    { type: 'h2', text: '3. No spam or manipulation' },
    {
        type: 'p',
        text:
            'Do not spam, run scams, impersonate Max staff or other users, artificially manipulate engagement, or distribute malware or phishing links.',
    },

    { type: 'h2', text: '4. Privacy of others' },
    {
        type: 'p',
        text: 'Do not share others’ private information (doxxing) without consent. Do not use the Services to stalk or monitor people.',
    },

    { type: 'h2', text: '5. Sexual content and safety' },
    {
        type: 'p',
        text:
            'Do not post pornographic content, sexual services, or content that sexualizes minors. Content involving minors must be strictly non-sexual and appropriate; when in doubt, do not post.',
    },

    { type: 'h2', text: '6. Health and dangerous behavior' },
    {
        type: 'p',
        text:
            'Do not encourage eating disorders, self-harm, suicide, or misuse of drugs or supplements. Max is not a substitute for professional care; crisis resources should be sought through qualified services in your region.',
    },

    { type: 'h2', text: '7. Intellectual property' },
    {
        type: 'p',
        text: 'Share only content you have the right to share. Respect copyrights, trademarks, and others’ creative work.',
    },

    { type: 'h2', text: '8. Filtering and objectionable content' },
    {
        type: 'p',
        text:
            'We use a combination of technical measures (for example automated detection, rate limits, spam prevention, and account signals) and human review to reduce objectionable content and abuse. No system is perfect; some policy-violating content may appear before it is removed. Your reports help us respond quickly.',
    },

    { type: 'h2', text: '9. Reporting and blocking' },
    {
        type: 'p',
        text:
            'Use in-app reporting tools on messages or content where available. You can also block users to control your experience. Reports are reviewed by our team; not every report results in public action. False or abusive reporting may affect your account.',
    },

    { type: 'h2', text: '10. Moderation' },
    {
        type: 'p',
        text:
            'We may remove content, hide it, limit distribution, or take account action at our discretion, with or without notice, to protect users and comply with law. We are not obligated to pre-screen all content. If you believe action was taken in error, contact:',
    },
    { type: 'mailtoLine', before: '', after: '' },

    { type: 'h2', text: '11. Updates' },
    {
        type: 'p',
        text: 'We may update these Guidelines. Continued use of community features after updates means you accept the revised Guidelines.',
    },
];

export const cookiesBlocks: LegalBlock[] = [
    { type: 'meta', text: 'Effective March 23, 2026 · Websites and web properties' },
    {
        type: 'p',
        text:
            'This notice describes how Max and our partners use cookies and similar technologies on websites and web properties we operate. Mobile app privacy and data handling are described in more detail in the Privacy Policy in this app.',
    },
    {
        type: 'callout',
        title: 'Scope',
        text:
            'This Cookie Notice is for Max websites and web pages. For App Store distribution, ensure App Privacy details (data types collected, linked to user, used for tracking) match what you actually collect—this notice, the Privacy Policy, and your product behavior should be consistent.',
    },

    { type: 'h2', text: 'What are cookies?' },
    {
        type: 'p',
        text:
            'Cookies are small text files stored on your device. Similar technologies include pixels, local storage, and SDKs in apps. They help sites function, remember preferences, measure performance, and—where allowed—support marketing.',
    },

    { type: 'h2', text: 'How we use them' },
    {
        type: 'bullets',
        items: [
            'Strictly necessary: required for security, load balancing, authentication on web, and basic functionality.',
            'Preferences: remember settings such as language or display options.',
            'Analytics: understand how visitors use our sites so we can improve them.',
            'Marketing: only where permitted, to measure campaigns or deliver relevant ads on third-party platforms.',
        ],
    },

    { type: 'h2', text: 'Your choices' },
    {
        type: 'p',
        text:
            'Browser settings let you block or delete cookies. Blocking some cookies may break parts of a site. For advertising choices, use industry opt-out tools where available in your region (for example, aboutads.info or your device settings). In the European Economic Area, UK, and similar regions, we provide consent tools where required.',
    },

    { type: 'h2', text: 'Third parties' },
    {
        type: 'p',
        text:
            'Third-party services linked from our sites (analytics, video embeds, social widgets) may set their own cookies governed by their policies.',
    },

    { type: 'h2', text: 'Updates' },
    {
        type: 'p',
        text: 'We may update this notice. Check the effective date when you visit.',
    },

    { type: 'h2', text: 'Contact' },
    { type: 'mailtoLine', before: '', after: '' },
];

export type LegalDocId = 'privacy' | 'terms' | 'community' | 'cookies';

export function getLegalBlocks(id: LegalDocId): LegalBlock[] {
    switch (id) {
        case 'privacy':
            return privacyBlocks;
        case 'terms':
            return termsBlocks;
        case 'community':
            return communityBlocks;
        case 'cookies':
            return cookiesBlocks;
        default:
            return [];
    }
}
