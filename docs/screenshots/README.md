# Screenshots Directory

This directory contains UI screenshots for documentation.

## Required Screenshots

Please capture the following tabs at 192.168.88.55:8080 for README documentation:

1. **overview.png** - Overview dashboard with system health indicators
2. **camera.png** - Camera tab with live MJPEG stream
3. **ph_control.png** - pH control tab with dosing controls and history
4. **ec_control.png** - EC/nutrient control tab with mix ratios
5. **temperature.png** - Temperature control tab with chiller management
6. **circulation.png** - Circulation tab with pump runtime charts
7. **lights.png** - Lights schedule tab with activity timeline
8. **schedule.png** - Schedule tab with scheduler management
9. **settings.png** - Settings tab with system configuration

## Screenshot Guidelines

- **Resolution**: 1920×1080 or higher
- **Format**: PNG (lossless, good for UI)
- **Naming**: Use lowercase with underscores (e.g., `ph_control.png`)
- **Browser**: Latest Chrome/Firefox with cache cleared (Ctrl+Shift+R)
- **Timing**: Capture when system has live data (sensors online, charts populated)
- **Privacy**: Ensure no sensitive information (IP addresses OK for local network)

## How to Capture

1. Navigate to http://192.168.88.55:8080
2. Clear browser cache (Ctrl+Shift+R) to ensure latest UI
3. Click on each tab to activate
4. Wait for data to load (~5 seconds)
5. Use Windows Snipping Tool or browser DevTools screenshot feature
6. Save with descriptive filename in this directory

## Usage in README

Screenshots will be embedded in README.md using relative paths:
```markdown
![Overview Dashboard](docs/screenshots/overview.png)
```
