# How-To: Capture Screenshots for Documentation

**Purpose**: Guide AI agents through capturing clean, accurate screenshots from live web applications for use in documentation

**Scope**: Screenshot capture using macOS `screencapture` and `sips` with the Claude-in-Chrome MCP extension

**Overview**: Describes the correct workflow for taking documentation screenshots from live web
    applications running in Chrome. Covers avoiding common pitfalls like extension overlays,
    wrong file formats, and using stock images instead of real ones.

**Dependencies**: macOS `screencapture`, `sips`, Chrome browser with Claude-in-Chrome MCP extension

**Exports**: Clean JPEG screenshots suitable for committing to the repository

**Related**: prek.toml (500KB max file size), how-to-deploy-a-new-app.md

**Difficulty**: easy

---

## Rules

1. **Use real screenshots from the live instance, not stock images.** Never download promotional
   images from a project's GitHub repository and present them as documentation of our deployment.
   They show outdated UIs, fake data, and someone else's setup.

2. **Never use GIF format for static screenshots.** The gif_creator tool always produces GIF files
   regardless of the filename extension. Do not use it for screenshots. GIF is only appropriate
   for recording multi-step interactions.

3. **Always exclude browser chrome and extension artifacts.** The "Claude is active in this tab
   group" banner and other extension UI elements must not appear in screenshots. Crop the capture
   region to exclude them.

4. **Do not show other tabs.** Screenshots should show only the application content, not browser
   tabs, bookmarks bars, or other open pages.

## Method: macOS `screencapture` + `sips`

This is the reliable method for producing clean JPEG screenshots from Chrome.

### Step 1: Determine the browser content area

```javascript
// Run in the Chrome tab via javascript_tool
JSON.stringify({
  screenX: window.screenX,
  screenY: window.screenY,
  outerWidth: window.outerWidth,
  outerHeight: window.outerHeight
})
```

The content area starts below the browser chrome (tabs + address bar), which is approximately
80px on macOS Chrome. So the content area top is roughly `screenY + 82`.

### Step 2: Navigate and wait

Use the Chrome MCP tools to navigate to the target page. Wait 3-4 seconds for the page to
fully render (images, maps, ML-generated content).

```
navigate → wait 3s → verify with screenshot tool
```

### Step 3: Capture with screencapture

Use macOS `screencapture -x` (silent) with `-R x,y,w,h` to capture only the content area.
Crop 100pt off the bottom to exclude the "Claude is active" tab group banner.

```bash
# Example for a Chrome window at y=120, full width 1728px
# Content starts at y=202 (120 + 82px browser chrome)
# Height = 815px (leaving 100px bottom margin to exclude extension banner)
screencapture -x -R 0,202,1728,815 raw.png
```

### Step 4: Resize and convert to JPEG

Raw Retina captures are 2x resolution and very large. Resize to ~1400px wide and convert
to JPEG at 75% quality to stay under the 500KB prek limit.

```bash
sips -Z 1400 raw.png --out screenshot.jpg -s format jpeg -s formatOptions 75
```

### Step 5: Verify

Read the resulting file to confirm:
- No "Claude is active" banner visible
- No browser tabs or address bar visible
- Page content is fully loaded (no spinners, no blank areas)
- File size is under 500KB

```bash
ls -lh screenshot.jpg   # Verify size
```

### Step 6: Clean up

Remove the raw capture file.

```bash
rm raw.png
```

## Common Mistakes

| Mistake | Why It's Wrong | What to Do Instead |
|---------|---------------|-------------------|
| Using gif_creator for static screenshots | Always produces GIF format regardless of filename | Use `screencapture` + `sips` |
| Downloading images from a project's GitHub | Shows outdated UI, fake data, wrong version | Capture from the live instance |
| Not waiting for page load | Captures spinners or partially-loaded content | Wait 3-4 seconds after navigation |
| Including the "Claude is active" banner | Exposes tooling artifacts in documentation | Crop bottom 100px from capture region |
| Leaving files as PNG | PNGs of photo-heavy pages are 1-5MB (over 500KB limit) | Convert to JPEG at 75% quality |
| Not verifying the screenshot | May contain artifacts you didn't notice | Always `Read` the file to inspect it |

## File Naming Convention

Use descriptive kebab-case names prefixed with the app name:

```
<app>-<feature>.jpg

Examples:
  immich-timeline.jpg
  immich-explore.jpg
  immich-map.jpg
  jellyfin-library.jpg
  audiobookshelf-player.jpg
```

## Checklist

Before committing screenshots:

- [ ] All images are from the live instance (not stock/promotional)
- [ ] All images are JPEG format (not GIF, not oversized PNG)
- [ ] All images are under 500KB
- [ ] No browser chrome visible (tabs, address bar, bookmarks)
- [ ] No extension artifacts visible ("Claude is active", debugging banners)
- [ ] No other tabs or windows visible
- [ ] Pages are fully loaded (no spinners or blank areas)
- [ ] File names are descriptive and follow the naming convention
