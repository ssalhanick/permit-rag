# Capacitor Implementation Overview

A high-level guide for wrapping an existing React app with Capacitor to deploy on the Apple App Store and Google Play.

## What Capacitor Actually Does

Capacitor takes your built web app (static HTML/JS/CSS output) and loads it inside a native WebView, wrapped in a real native project (Xcode project for iOS, Android Studio/Gradle project for Android). It then gives you a JavaScript bridge to call native device APIs — camera, push notifications, biometrics, filesystem, etc. — from your existing React code.

Your React app's logic, components, and state management stay the same. What changes is the shell around it and the presence of native plugin code you call into.

## High-Level Architecture

```
┌─────────────────────────────┐
│   Your React App (as-is)    │
│   (built to static assets)  │
└──────────────┬───────────────┘
               │
               ▼
┌─────────────────────────────┐
│      Capacitor Bridge        │
│  (JS <-> Native messaging)   │
└──────────────┬───────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐   ┌─────────────┐
│  iOS Native  │   │Android Native│
│  (Xcode/     │   │(Android      │
│  WKWebView)  │   │Studio/       │
│              │   │WebView)      │
└─────────────┘   └─────────────┘
```

## Implementation Steps (High Level)

### 1. Add Capacitor to the project
Install core packages and run `cap init` to set the app ID and app name. The app ID (reverse-domain format) is what ties your app to its store listing — choose it deliberately.

### 2. Point Capacitor at your build output
Capacitor doesn't serve your dev server; it packages your production build folder (`dist` for Vite, `build` for CRA). This is set once in `capacitor.config.ts`.

### 3. Generate native projects
`cap add ios` and `cap add android` scaffold full native projects into your repo. These become part of your codebase — they're not disposable generated artifacts, you configure and commit them like any native project.

### 4. Sync on every change
`cap sync` copies your latest web build into the native projects and updates any native plugin dependencies. This runs before every native build, similar to a build step in a CI pipeline.

### 5. Build and run natively
`cap open ios` / `cap open android` opens the real native IDEs, where you run on simulators/emulators or physical devices, and eventually handle signing, provisioning, and store builds using normal native tooling.

### 6. Layer in native functionality via plugins
This is the most important step for **iOS specifically**. Official and community plugins expose native capabilities to your React code as simple JS calls:
- Push notifications
- Camera / file access
- Biometric auth (Face ID / Touch ID)
- Native storage
- Splash screen / status bar control

Each plugin install requires a `cap sync` to wire it into the native side.

## Why Step 6 Matters More Than It Looks

Apple's App Review Guideline 4.2 (Minimum Functionality) specifically targets apps that are just a website in a WebView shell. A Capacitor app that doesn't add native capability is at real risk of rejection. Practical mitigations:

- Push notifications (the single biggest differentiator, since Safari on iOS has no web push)
- A native tab bar / navigation shell instead of your web app's own in-page router as the only navigation
- Offline handling so a lost connection doesn't show a blank screen
- Biometric login if you have auth

Google Play has no equivalent hard rule — a wrapped web app in reasonable shape clears review without these additions, though they're still good UX regardless of platform.

## Ongoing Dev Loop

Once set up, the day-to-day cycle is:

```bash
npm run build
npx cap sync
npx cap open ios     # or android
```

Everything past that point (running on device, submitting builds, managing certificates) is standard native app development, just with your React app as the content layer inside it.

## Summary

| Concern | Capacitor's Role |
|---|---|
| UI/business logic | Untouched — stays in React |
| Native device access | Provided via plugins + JS bridge |
| App Store packaging | Generates real Xcode/Android Studio projects |
| iOS review risk | Requires added native-feeling features to pass Guideline 4.2 |
| Android review risk | Minimal — wrapped web content is an accepted pattern |
