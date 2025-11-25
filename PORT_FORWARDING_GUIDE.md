# Port Forwarding Guide for Remote Debugging

## What is Port Forwarding?

**Port forwarding** creates a secure tunnel from your computer to Railway's server. Instead of accessing `hopper.proxy.rlwy.net:19118`, you access `localhost:9222` on your computer, and it automatically connects to Railway's port 9222.

**Think of it like:**
- Railway's server has the browser on port 9222
- Port forwarding creates a "tunnel" from your computer's localhost:9222 → Railway's port 9222
- Now you can use `localhost:9222` like the browser is running on your own computer

## Step-by-Step Setup

### 1. Install Railway CLI

**Windows (PowerShell):**
```powershell
# Using winget (Windows Package Manager)
winget install Railway.CLI

# OR using npm (if you have Node.js)
npm install -g @railway/cli
```

**Alternative - Download directly:**
1. Go to: https://railway.app/cli
2. Download the Windows installer
3. Run the installer

**Verify installation:**
```powershell
railway --version
```

### 2. Login to Railway

```powershell
railway login
```

This will open your browser to authenticate with Railway.

### 3. Link to Your Project

```powershell
# Navigate to your project directory (optional, but helps)
cd "C:\Users\Dell\Desktop\RPA For a\automation"

# Link to your Railway project
railway link
```

If you have multiple projects, select the one that matches your deployment (encova-submission-bot-rpa).

### 4. Forward Port 9222

```powershell
railway connect 9222
```

This will:
- Create a tunnel from `localhost:9222` to Railway's port 9222
- Keep running until you press Ctrl+C
- Show connection status

**You should see something like:**
```
✓ Forwarding localhost:9222 → railway:9222
[Press Ctrl+C to stop]
```

**Keep this terminal open!** The port forwarding only works while this command is running.

### 5. Configure Chrome

1. Open Chrome
2. Go to: `chrome://inspect`
3. Click **"Configure..."** under "Discover network targets"
4. Add: `localhost:9222`
5. Click **"Done"**

### 6. Test It!

1. Make sure Railway CLI port forwarding is still running (step 4)
2. Trigger a new automation task
3. Wait 5-10 seconds
4. Go to `chrome://inspect`
5. Look under **"Remote Target"** → `localhost:9222`
6. You should see browser tabs appear!
7. Click **"inspect"** to open DevTools

## Troubleshooting

### Port forwarding command fails:
- Make sure you're logged in: `railway login`
- Make sure you've linked your project: `railway link`
- Check that port 9222 is exposed in Railway settings

### Chrome doesn't show browser:
- Make sure port forwarding is still running (keep terminal open)
- Wait a few seconds after task starts for browser to initialize
- Refresh `chrome://inspect` (F5)
- Make sure `ENABLE_REMOTE_DEBUGGING=True` in Railway

### Connection reset:
- Restart the port forwarding: Stop (Ctrl+C) and run `railway connect 9222` again
- Check Railway logs to ensure browser started with remote debugging

## Quick Commands Reference

```powershell
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link project
railway link

# Forward port 9222
railway connect 9222

# Stop forwarding: Press Ctrl+C in the terminal
```

## Important Notes

- **Keep the port forwarding terminal open** - It only works while running
- **Use `localhost:9222`** - Not the Railway proxy URL
- **Browser must be running** - Start a task first, then check Chrome
- **Wait a few seconds** - Browser needs time to initialize after task starts

