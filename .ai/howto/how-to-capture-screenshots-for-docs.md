# How-To: Capture Screenshots for Documentation

**Purpose**: Guide AI agents through capturing clean, professional screenshots for documentation

**Scope**: Any documentation that needs screenshots of web UIs (Jellyfin, Audiobookshelf, Grafana, etc.)

**Overview**: Covers how to take clean browser screenshots without UI artifacts like extension banners,
    debug toolbars, or tab chrome. Includes best practices for file naming, sizing, and placement.

**Dependencies**: Chrome browser with Claude extension, `mcp__claude-in-chrome__*` tools

**Exports**: Clean PNG screenshots saved to the appropriate `docs/images/` directory

**Related**: apps/jellyfin/docs/connecting-to-jellyfin.md

**Difficulty**: beginner

---

## Before Taking Screenshots

### Dismiss the "Claude is active in this tab group" banner

The Claude browser extension shows a notification banner at the bottom of the page:
**"Claude is active in this tab group"**. This banner will appear in screenshots if not dismissed.

**Always dismiss it before capturing:**

```javascript
// Run via mcp__claude-in-chrome__javascript_tool
document.querySelector('[class*="claude-banner"]')?.remove();
// Or click the X button on the banner manually
```

If the banner reappears after navigation, dismiss it again before each screenshot.

### Hide Chrome debugging banners

When Claude controls the browser, Chrome may show an infobar:
**'"Claude" started debugging this browser'**. This also appears in screenshots taken via
`screencapture` or other OS-level tools.

To avoid this:
- **Preferred**: Use `mcp__claude-in-chrome__computer` with `action: "screenshot"` — this captures
  only the viewport content, not Chrome UI chrome (tabs, URL bar, infobars).
- **Avoid**: macOS `screencapture` captures the full window including Chrome tabs, URL bar, and
  debug banners.

### General checklist before capturing

- [ ] "Claude is active in this tab group" banner is dismissed
- [ ] No Chrome debug infobars visible
- [ ] Page is fully loaded (no spinners, skeleton screens)
- [ ] The relevant content is visible in the viewport (scroll if needed)
- [ ] Dark mode / light mode matches the rest of the documentation
- [ ] No sensitive data visible (API keys, tokens, passwords)

---

## Taking Screenshots

### Method 1: Browser automation tool (recommended)

Use `mcp__claude-in-chrome__computer` with `action: "screenshot"`. This captures only the
browser viewport — no tabs, URL bar, or OS window chrome.

```
mcp__claude-in-chrome__computer:
  action: screenshot
  tabId: <tab_id>
```

The screenshot is returned as an image in the tool result. Save it to disk using the JavaScript
tool with a canvas download, or use it directly.

### Method 2: JavaScript html2canvas (fallback)

If the browser tool screenshot has issues, use html2canvas to render the page to a canvas
and trigger a download:

```javascript
// Run via mcp__claude-in-chrome__javascript_tool
const script = document.createElement('script');
script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
document.head.appendChild(script);

// Wait for load, then:
html2canvas(document.body).then(canvas => {
  const link = document.createElement('a');
  link.download = 'screenshot.png';
  link.href = canvas.toDataURL();
  link.click();
});
```

**Note**: Chrome may block auto-downloads after the first one. If this happens, the download
will silently fail. Check `~/Downloads/` to confirm the file was saved.

### Method 3: macOS screencapture (last resort)

```bash
screencapture -l$(osascript -e 'tell app "Google Chrome" to id of window 1') screenshot.png
```

**Warning**: This captures the full Chrome window including tabs, URL bar, and any debug
banners. Only use this if the browser automation tools are unavailable. You may need to crop
the result afterward.

---

## File Naming and Placement

- Save screenshots to `apps/<app-name>/docs/images/`
- Use lowercase kebab-case: `jellyfin-home.png`, `jellyfin-dashboard.png`
- Name files descriptively by what they show, not by sequence number
- Use PNG format for UI screenshots (not JPEG — text gets blurry with JPEG compression)

---

## Common Pitfalls

| Pitfall | Prevention |
|---------|-----------|
| "Claude is active in this tab group" banner in screenshot | Dismiss the banner before every capture |
| Chrome debug infobar visible | Use viewport-only screenshot method, not OS screencapture |
| Chrome tabs/URL bar visible | Use `mcp__claude-in-chrome__computer` screenshot, not macOS screencapture |
| Page not fully loaded | Wait for network idle or use `mcp__claude-in-chrome__computer` wait action |
| html2canvas download blocked | Chrome blocks repeated auto-downloads; check ~/Downloads/ or use a different method |
| Screenshot shows wrong window | Activate Chrome window with AppleScript before OS screencapture |
| Stale screenshot from previous session | Always verify screenshots with Read tool after capturing |
