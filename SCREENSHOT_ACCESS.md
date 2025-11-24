# Screenshot Access Guide

Screenshots are automatically taken during automation tasks and stored on the Railway server. Here's how to access them:

## Screenshot Storage Location

**On Railway Server:** `/app/logs/screenshots/{task_id}/`

**Example:** `/app/logs/screenshots/test_screenshots_20251125_032707/`

## API Endpoints

### 1. List All Screenshots for a Task

**Endpoint:** `GET /screenshots/{task_id}`

**Example:**
```bash
curl https://encova-submission-bot-rpa-production.up.railway.app/screenshots/test_screenshots_20251125_032707
```

**Response:**
```json
{
  "task_id": "test_screenshots_20251125_032707",
  "total": 2,
  "screenshots": [
    {
      "name": "01_browser_initialized",
      "filename": "01_browser_initialized.png",
      "size_bytes": 10592,
      "size_kb": 10.34,
      "created_at": "2025-11-24T22:28:37.123456",
      "url": "/screenshot/test_screenshots_20251125_032707/01_browser_initialized.png"
    },
    {
      "name": "04_login_failed",
      "filename": "04_login_failed.png",
      "size_bytes": 10592,
      "size_kb": 10.34,
      "created_at": "2025-11-24T22:29:24.123456",
      "url": "/screenshot/test_screenshots_20251125_032707/04_login_failed.png"
    }
  ]
}
```

### 2. Download a Specific Screenshot

**Endpoint:** `GET /screenshot/{task_id}/{filename}`

**Example:**
```bash
# Direct download
curl -O https://encova-submission-bot-rpa-production.up.railway.app/screenshot/test_screenshots_20251125_032707/01_browser_initialized.png

# Or open in browser
https://encova-submission-bot-rpa-production.up.railway.app/screenshot/test_screenshots_20251125_032707/01_browser_initialized.png
```

### 3. Get Task Status (Includes Screenshot Info)

**Endpoint:** `GET /task/{task_id}/status`

**Example:**
```bash
curl https://encova-submission-bot-rpa-production.up.railway.app/task/test_screenshots_20251125_032707/status
```

**Response includes:**
```json
{
  "status": "failed",
  "task_id": "test_screenshots_20251125_032707",
  "screenshots": [...],
  "screenshot_count": 2,
  "screenshot_urls": [
    {
      "name": "01_browser_initialized",
      "filename": "01_browser_initialized.png",
      "url": "https://encova-submission-bot-rpa-production.up.railway.app/screenshot/test_screenshots_20251125_032707/01_browser_initialized.png"
    }
  ]
}
```

## Screenshot Naming Convention

Screenshots are named sequentially to show the automation flow:

- `01_browser_initialized.png` - Browser started
- `02_auto_login_success.png` - Auto-login successful (if cookies exist)
- `03_before_login.png` - Before login attempt
- `04_after_login.png` - After successful login
- `04_login_failed.png` - Login failed
- `05_before_navigation.png` - Before navigating to form
- `06_after_navigation.png` - After navigation
- `07_form_opened.png` - Form page loaded
- `08_before_filling_form.png` - Before filling form fields
- `09_after_filling_form.png` - After filling form fields
- `10_after_dropdowns.png` - After filling dropdowns
- `11_before_save.png` - Before clicking save
- `12_after_save_success.png` - After successful save
- `12_after_save_failed.png` - After failed save
- `error_*.png` - Error screenshots

## Accessing Screenshots from Your Next.js App

```javascript
// Get task status (includes screenshots)
const response = await fetch(
  `https://encova-submission-bot-rpa-production.up.railway.app/task/${taskId}/status`
);
const status = await response.json();

// Display screenshots
if (status.screenshot_urls && status.screenshot_urls.length > 0) {
  status.screenshot_urls.forEach(screenshot => {
    console.log(`Screenshot: ${screenshot.name}`);
    console.log(`URL: ${screenshot.url}`);
    // Use screenshot.url in an <img> tag
  });
}
```

## Quick Access URLs

For task `test_screenshots_20251125_032707`:

1. **List screenshots:**
   ```
   https://encova-submission-bot-rpa-production.up.railway.app/screenshots/test_screenshots_20251125_032707
   ```

2. **Download screenshots:**
   ```
   https://encova-submission-bot-rpa-production.up.railway.app/screenshot/test_screenshots_20251125_032707/01_browser_initialized.png
   https://encova-submission-bot-rpa-production.up.railway.app/screenshot/test_screenshots_20251125_032707/04_login_failed.png
   ```

## Notes

- Screenshots are stored on the Railway server filesystem
- Screenshots persist until the container is redeployed or files are manually deleted
- Each task gets its own directory: `screenshots/{task_id}/`
- Screenshots are PNG format, full-page captures
- Screenshot URLs are included in the task status response for easy access

