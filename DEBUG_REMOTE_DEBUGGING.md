# Debugging Remote Debugging Issues

## What to Check

### 1. Check Railway Environment Variables

In Railway dashboard → Your service → Variables, verify:
- `ENABLE_REMOTE_DEBUGGING=True` (must be exactly "True", not "true" or "TRUE")
- `REMOTE_DEBUGGING_PORT=9222` (optional, defaults to 9222)

### 2. Check Railway Networking

In Railway dashboard → Your service → Settings → Networking:
- Port `9222` should be exposed
- Should show a TCP proxy URL like `hopper.proxy.rlwy.net:19118`

### 3. Check Browser Initialization Logs

Look for these logs when a task starts (at the beginning of the task, not after login):

**Expected logs:**
```
Remote debugging ENABLED - Port: 9222
Browser will be accessible at: http://localhost:9222
Connect via Chrome: chrome://inspect
Railway proxy URL: hopper.proxy.rlwy.net:19118
Headless mode: True (required for containerized environment)
Note: Remote debugging works with headless browsers
Browser initialized
```

**If you DON'T see these logs:**
- `ENABLE_REMOTE_DEBUGGING` is not set to `True`
- Or the environment variable isn't being read correctly

### 4. Check if Browser Starts Successfully

Look for:
- `Browser initialized` - means browser started
- `Timeout 180000ms exceeded` - means browser failed to start (this was the issue before)

### 5. Test Remote Debugging Connection

Run this to check if the browser is accessible:
```bash
python check_remote_debug.py
```

Or manually check:
```
http://hopper.proxy.rlwy.net:19118/json
```

If you get JSON back with browser tabs, it's working!
If you get connection refused, the browser isn't exposing remote debugging.

## Common Issues

### Issue 1: No "Remote debugging ENABLED" logs
**Solution:** Set `ENABLE_REMOTE_DEBUGGING=True` in Railway

### Issue 2: Browser times out
**Solution:** Already fixed - headless mode is now enabled

### Issue 3: Tabs don't appear in chrome://inspect
**Possible causes:**
- Browser hasn't navigated to a page yet (tabs only appear after navigation)
- Remote debugging port not exposed in Railway
- TCP proxy URL changed (check Railway networking settings)

### Issue 4: Connection refused
**Solution:** 
- Make sure port 9222 is exposed in Railway
- Make sure a task is currently running (browser only exists during tasks)
- Check Railway logs for any errors

