# Playwright Tracing Guide

## Overview

Playwright tracing records a detailed timeline of all browser actions, network requests, console logs, and screenshots during automation. This is much better than remote debugging for debugging automation issues.

## How It Works

1. **Tracing is enabled by default** (`ENABLE_TRACING=True` in config)
2. Each automation task creates a trace file: `traces/{task_id}.zip`
3. Trace files are saved on the Railway server
4. You can download and view traces locally

## Viewing Traces

### Step 1: Download the Trace File

After a task completes, get the trace URL from the task status:

```bash
# Get task status
curl https://encova-submission-bot-rpa-production.up.railway.app/task/{task_id}/status

# Download trace
curl -O https://encova-submission-bot-rpa-production.up.railway.app/trace/{task_id}
```

Or use the test script:
```bash
python test_and_download_trace.py
```

Or download an existing trace:
```bash
python download_trace.py <task_id>
```

### Step 2: Install Playwright (if not already installed)

```bash
pip install playwright
playwright install chromium
```

### Step 3: View the Trace

```bash
playwright show-trace {task_id}.zip
```

This opens a web-based trace viewer showing:
- **Timeline**: All actions in chronological order
- **Screenshots**: Visual state at each step
- **Network**: All HTTP requests and responses
- **Console**: JavaScript console logs
- **DOM Snapshots**: Full page state at each action

## What You Can See in a Trace

1. **Every Click**: See exactly where and when clicks happened
2. **Every Navigation**: URL changes and page loads
3. **Network Requests**: All API calls, their timing, and responses
4. **Console Errors**: JavaScript errors that might affect automation
5. **Screenshots**: Visual state before/after each action
6. **DOM State**: Full HTML at each step

## Example: Debugging a Dropdown Issue

If a dropdown times out:

1. Open the trace file
2. Find the dropdown click action in the timeline
3. Check the screenshot - is the dropdown visible?
4. Check network requests - did the dropdown options load?
5. Check console - any JavaScript errors?
6. Inspect the DOM snapshot - what elements were present?

## Trace File Size

Trace files can be large (10-50MB) because they include:
- Full DOM snapshots
- Network request/response bodies
- Screenshots at each step

## Disabling Tracing

Set environment variable:
```bash
ENABLE_TRACING=False
```

## Trace Storage

Traces are stored in: `/app/traces/` on Railway

They persist until the container is redeployed. For long-term storage, download important traces.

## API Endpoints

- **Download trace**: `GET /trace/{task_id}`
- **Task status** (includes trace_path): `GET /task/{task_id}/status`

## Benefits Over Remote Debugging

✅ **Works reliably** - No proxy/network issues  
✅ **Complete history** - See everything that happened  
✅ **Offline viewing** - Download and view anytime  
✅ **Better UI** - Playwright's trace viewer is excellent  
✅ **No setup** - Just download and view  

