# Remote Debugging Setup Guide

This guide explains how to view the browser in real-time using Chrome Remote Debugging.

## What You Can See

- **Live Browser Window**: See exactly what Playwright is doing in real-time
- **Chrome DevTools**: Full access to console, network, elements, etc.
- **Debug Issues**: Inspect elements, check network requests, see JavaScript errors
- **No Control Required**: View-only mode, won't affect automation

## Setup Instructions

### 1. Enable Remote Debugging

In Railway dashboard, add these environment variables:

```
ENABLE_REMOTE_DEBUGGING=True
REMOTE_DEBUGGING_PORT=9222
```

### 2. Expose Port in Railway

1. Go to Railway dashboard → Your service → **Settings**
2. Click on **Networking** tab
3. Click **+ New** to add a new port
4. Set:
   - **Port**: `9222`
   - **Protocol**: `TCP`
   - **Public**: `Yes` (for external access)

### 3. Get Your Railway Service URL

After deploying, Railway will give you a URL like:
```
https://encova-submission-bot-rpa-production.up.railway.app
```

The remote debugging will be available at:
```
http://encova-submission-bot-rpa-production.up.railway.app:9222
```

**Note**: If Railway doesn't provide direct access, you may need to use Railway's port forwarding or a tunnel.

### 4. Connect with Chrome DevTools

#### Option A: Using Chrome Inspect (Recommended)

1. Open Chrome browser on your computer
2. Navigate to: `chrome://inspect`
3. Click **"Configure..."** button
4. Add your Railway debugging URL:
   ```
   http://encova-submission-bot-rpa-production.up.railway.app:9222
   ```
5. Click **"Done"**
6. Start a task in your automation
7. You'll see a browser appear under **"Remote Target"**
8. Click **"inspect"** to open DevTools

#### Option B: Direct DevTools URL

1. Get the WebSocket URL from Railway logs:
   ```
   ws://encova-submission-bot-rpa-production.up.railway.app:9222/devtools/browser/...
   ```
2. Or construct it manually:
   ```
   http://encova-submission-bot-rpa-production.up.railway.app:9222/json
   ```
   This returns JSON with WebSocket URLs for all browser tabs
3. Use a DevTools client to connect to the WebSocket URL

#### Option C: Using Browser Extension

1. Install a Chrome extension like "Remote Debugging"
2. Enter your Railway URL:port
3. Connect and view the browser

### 5. Using Railway CLI (Alternative)

If direct access doesn't work, use Railway CLI port forwarding:

```bash
# Install Railway CLI if not installed
npm i -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Forward the debugging port
railway connect 9222
```

This creates a local tunnel. Then use:
```
http://localhost:9222
```

### 6. Security Warning

⚠️ **IMPORTANT**: Remote debugging exposes full browser access!

- Only enable `ENABLE_REMOTE_DEBUGGING=True` when debugging
- Set it to `False` in production
- Anyone with the URL can access the browser
- Consider using Railway's private networking or VPN

### 7. Disable After Debugging

After debugging, always:
1. Set `ENABLE_REMOTE_DEBUGGING=False` in Railway
2. Remove or disable the exposed port 9222
3. Redeploy the service

## Troubleshooting

### Can't Connect to Port

- Check if port 9222 is properly exposed in Railway
- Verify `ENABLE_REMOTE_DEBUGGING=True` is set
- Check Railway logs for any errors
- Try using Railway CLI port forwarding as alternative

### Browser Not Appearing

- Make sure a task is running (browser only exists during automation)
- Check Railway logs for browser initialization
- Verify remote debugging args are in logs: `--remote-debugging-port=9222`

### Connection Refused

- Railway might block direct port access
- Use Railway CLI port forwarding instead
- Check firewall settings

## What You'll See

Once connected, you'll see:
- **Browser Tab**: The actual browser window Playwright is using
- **DevTools Panel**: Console, Network, Elements, Application tabs
- **Real-time Updates**: Watch actions happen live
- **Network Requests**: See all API calls, responses, errors
- **Console Logs**: See all JavaScript console output
- **DOM Inspection**: Inspect elements, see HTML structure

## Example Usage

1. Enable remote debugging in Railway
2. Start a webhook request
3. Open `chrome://inspect` in Chrome
4. See the browser appear under "Remote Target"
5. Click "inspect" to open DevTools
6. Watch the automation run in real-time!

