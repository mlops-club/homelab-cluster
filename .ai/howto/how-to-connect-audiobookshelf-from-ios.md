# How-To: Connect to Audiobookshelf from iOS

**Purpose**: Guide for connecting an iOS device to the self-hosted Audiobookshelf server using the AudioBooth app

**Scope**: iOS app installation, server connection, user account creation, and playback

**Overview**: Audiobookshelf can be accessed from iOS using AudioBooth, a free third-party client. The app
    connects to the server at `books.mlops-club.org` (publicly accessible via Cloudflare Tunnel),
    syncs listening progress across devices, and supports offline downloads. This guide covers the
    full setup from app install to streaming an audiobook.

**Dependencies**: Audiobookshelf deployed on K3s (`apps/audiobookshelf/`), an Audiobookshelf user account

**Exports**: A working iOS audiobook player connected to the self-hosted library

**Related**: how-to-add-audiobooks-to-audiobookshelf.md, how-to-deploy-a-new-app.md

**Difficulty**: beginner

---

## Prerequisites

- **Audiobookshelf** is deployed and accessible at `https://books.mlops-club.org`
- **An Audiobookshelf user account** exists (created via the web UI)

## Steps

### Step 1: Create a User Account in Audiobookshelf (Web UI)

Before connecting from iOS, create a user account via the web UI:

1. Open `https://books.mlops-club.org` in a browser
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

### Step 3: Add Server in AudioBooth

1. Open AudioBooth
2. On the server connection screen, enter the server URL: `https://books.mlops-club.org`
3. Enter your Audiobookshelf username and password (the account created in Step 1)
4. Tap **Connect**

The app loads your library and displays audiobook covers.

### Step 4: Stream or Download Audiobooks

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

1. Try loading `https://books.mlops-club.org` in Safari — if Safari fails, the server may be down
2. Force-close AudioBooth and reopen it

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
- [ ] AudioBooth connects to `https://books.mlops-club.org`
- [ ] Library loads with audiobook covers
- [ ] Audio playback works (stream or offline)
- [ ] Listening progress syncs to the web UI
