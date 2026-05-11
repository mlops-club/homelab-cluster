# How-To: Connect to Audiobookshelf from iOS

**Purpose**: Guide for connecting an iOS device to the self-hosted Audiobookshelf server using the AudioBooth app

**Scope**: iOS app installation, server connection via Tailscale, user account creation, and playback

**Overview**: Audiobookshelf can be accessed from iOS using AudioBooth, a free third-party client. The app
    connects to the server over Tailscale VPN, syncs listening progress across devices, and supports
    offline downloads. This guide covers the full setup from app install to streaming an audiobook.

**Dependencies**: Audiobookshelf deployed on K3s (`apps/audiobookshelf/`), Tailscale installed on the iOS device, an Audiobookshelf user account

**Exports**: A working iOS audiobook player connected to the self-hosted library

**Related**: how-to-add-audiobooks-to-audiobookshelf.md, how-to-deploy-a-new-app.md

**Difficulty**: beginner

---

## Prerequisites

- **Audiobookshelf** is deployed and accessible at `https://abs.priv.mlops-club.org`
- **Tailscale** is installed and connected on your iPhone ([App Store](https://apps.apple.com/us/app/tailscale/id1470499037))
- **An Audiobookshelf user account** exists (created via the web UI)

## Steps

### Step 1: Create a User Account in Audiobookshelf (Web UI)

Before connecting from iOS, create a user account via the web UI:

1. Open `https://abs.priv.mlops-club.org` in a browser (requires Tailscale)
2. Log in with the admin account
3. Navigate to **Settings** (gear icon, top right) → **Users**
4. Click **Add User**
5. Set a username, password, and select the libraries the user can access
6. Save the user

### Step 2: Install AudioBooth on iOS

Install **AudioBooth: Audiobooks Player** from the App Store:

- [AudioBooth on the App Store](https://apps.apple.com/us/app/audiobooth-audiobooks-player/id6753017503)
- Free, no in-app purchases required
- Source code: [github.com/AudioBooth/AudioBooth](https://github.com/AudioBooth/AudioBooth)

### Step 3: Connect Tailscale on iPhone

Open the Tailscale app on your iPhone and verify it shows **Connected**. The Audiobookshelf server is only reachable over the Tailscale VPN.

**Tip**: iOS aggressively suspends background VPN connections to save battery. If AudioBooth reports a connection error, open the Tailscale app first and confirm it is connected before retrying.

### Step 4: Add Server in AudioBooth

1. Open AudioBooth
2. On the server connection screen, enter the server URL: `https://abs.priv.mlops-club.org`
3. Enter your Audiobookshelf username and password (the account created in Step 1)
4. Tap **Connect**

The app loads your library and displays audiobook covers.

### Step 5: Configure Alternative URL (Optional)

AudioBooth supports an **alternative/fallback URL**. If you access the server from both your home LAN and remotely via Tailscale, you can configure:

- **Primary URL**: Your LAN address (faster when at home)
- **Alternative URL**: The Tailscale address (`https://abs.priv.mlops-club.org`)

The app automatically falls back to the alternative URL when the primary is unreachable.

### Step 6: Stream or Download Audiobooks

- **Stream**: Tap any audiobook to begin playback immediately. Progress syncs to the server automatically.
- **Download**: Tap the download icon on an audiobook to save it for offline listening. Downloaded books are available without a network connection.

## Key Features

| Feature | Details |
|---------|---------|
| Progress sync | Listening position syncs across all devices (iOS, web, Android) |
| Offline downloads | Download audiobooks for listening without internet |
| Variable speed | Adjust playback speed |
| Sleep timer | Auto-stop with fade out |
| CarPlay | Full CarPlay integration for in-car listening |
| Apple Watch | Playback controls on Apple Watch |
| Chapters | Navigate by chapter |
| eBook reader | Built-in EPUB/PDF reader for companion books |

## Troubleshooting

### "Connection Error" or "No Internet"

1. Open the Tailscale app and verify it shows **Connected**
2. Try loading `https://abs.priv.mlops-club.org` in Safari — if Safari fails, Tailscale is the issue
3. Force-close AudioBooth and reopen it after confirming Tailscale connectivity

### Playback Stops in Background

iOS may suspend the app if it detects low battery or high resource usage. Downloading audiobooks for offline playback avoids this issue entirely.

### Alternative iOS Clients

If AudioBooth does not meet your needs:

| App | Price | Notes |
|-----|-------|-------|
| [ShelfPlayer](https://apps.apple.com/us/app/shelfplayer/id6475221163) | $5 | Swift-native, feature-rich |
| [Still: for Audiobookshelf](https://apps.apple.com/us/app/still-for-audiobookshelf/id6754208326) | Free | Clean native client |

## Success Criteria

- [ ] AudioBooth installed on iPhone
- [ ] Tailscale connected on iPhone
- [ ] AudioBooth connects to `https://abs.priv.mlops-club.org`
- [ ] Library loads with audiobook covers
- [ ] Audio playback works (stream or offline)
- [ ] Listening progress syncs to the web UI
