# DeepGuard Shield - Chrome Extension

A powerful Chrome extension for real-time deepfake detection on social media platforms.

## Features

- 🎯 **Real-time Video Analysis** - Automatically detects and analyzes videos on social media
- 🛡️ **Visual Overlays** - Shows authenticity indicators directly on videos
- 🔔 **Instant Notifications** - Alerts you when deepfakes are detected
- 📊 **Statistics Dashboard** - Track your detection history
- ⚡ **Smart Caching** - Remembers previously analyzed videos

## Supported Platforms

- Twitter/X
- YouTube
- Facebook
- Instagram
- TikTok
- Reddit
- LinkedIn

## Installation

### Development Mode

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" in the top right corner
3. Click "Load unpacked"
4. Select the `extension` folder from this project
5. The extension icon should appear in your toolbar

### Prerequisites

Make sure the backend server is running:

```bash
cd web
python app.py --port 5001
```

## Usage

1. **Click the extension icon** to open the popup dashboard
2. **Browse social media** - Videos are automatically detected
3. **Watch for overlays** - Green = Authentic, Red = Potential Deepfake
4. **Click video overlays** for detailed analysis

## Extension Structure

```
extension/
├── manifest.json          # Extension configuration
├── background.js          # Service worker for API calls
├── content/
│   ├── content.js         # Video detection on pages
│   └── overlay.css        # Overlay styling
├── popup/
│   ├── popup.html         # Extension popup UI
│   ├── popup.css          # Popup styling
│   └── popup.js           # Popup functionality
└── icons/
    ├── icon-16.png        # Toolbar icon
    ├── icon-32.png        # Menu icon
    ├── icon-48.png        # Extensions page icon
    └── icon-128.png       # Chrome Web Store icon
```

## API Endpoints

The extension communicates with these backend endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extension/analyze-url` | POST | Analyze video from URL |
| `/api/extension/check-hash` | POST | Check if video is cached |
| `/api/extension/stats` | GET | Get analysis statistics |
| `/api/extension/report` | POST | Report a detected deepfake |

## Configuration

Open the extension popup and click the settings icon to configure:

- **Auto-scan** - Enable/disable automatic video detection
- **Notifications** - Enable/disable deepfake alerts
- **Confidence threshold** - Minimum confidence to show alerts

## How It Works

1. **Video Detection** - Content script monitors the page for video elements
2. **Hash Generation** - Unique hash created for each video
3. **Cache Check** - First checks if video was previously analyzed
4. **API Analysis** - Sends video URL to backend for AI analysis
5. **Overlay Display** - Shows results as a visual overlay on the video

## Privacy

- Only video URLs are sent to the backend server (localhost by default)
- No personal data is collected
- Analysis results are cached locally in IndexedDB
- All communication stays on your local machine

## Development

### Building

The extension doesn't require a build step. Just load the `extension` folder in Chrome.

### Testing

1. Load the extension in Chrome
2. Navigate to a supported platform (e.g., twitter.com)
3. Videos should show a scanning overlay
4. Check the popup for statistics

### Debugging

- Open Chrome DevTools on any page
- Go to the "Console" tab
- Filter by "[DeepGuard]" to see extension logs
- For background script: go to `chrome://extensions/` > "Service Worker" > "Inspect"

## Troubleshooting

### "Backend Offline" Status

Make sure the Flask server is running:

```bash
cd web
python app.py --port 5001
```

### Videos Not Being Detected

- Check if the extension is enabled
- Ensure "Auto-scan" is turned on in settings
- Some platforms use dynamic loading - try scrolling to trigger detection

### Overlay Not Showing

- The video might still be loading
- Check browser console for errors
- Verify the backend is responding

## License

Part of the Deepfake Detection Hackathon Project.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
