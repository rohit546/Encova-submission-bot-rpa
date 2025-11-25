# Encova RPA Automation - Debugging Journey

## Overview
This document chronicles the debugging journey of getting the Encova Submission Bot RPA to work correctly via the webhook server. The automation fills insurance forms on the Encova Edge portal.

**Date:** November 26, 2025  
**Project:** Carrier-Submission-Tracker-System-For-insurance-agency

---

## Initial Problem Statement
The user wanted to test the Encova RPA automation locally via a webhook server. When running `python encova_login.py` directly, it worked perfectly. But when triggered via `python webhook_server.py` → `python test_webhook_local.py`, it got stuck.

---

## Issue #1: Navigation Timeout (Page Stuck at "Loading application")

### Symptom
```
2025-11-26 01:40:26,158 - encova_login - ERROR - Error checking auto-login: Timeout 90000ms exceeded.
```
The browser navigated to `agent.encova.com` but got stuck at "Loading application" screen when using webhook, while direct run worked fine.

### Root Cause
Each webhook task created a **NEW browser data directory**:
```python
user_data_dir = SESSION_DIR / f"browser_data_{self.task_id}"  # e.g., browser_data_local_test_1764103130
```

This meant:
- Direct run used `browser_data_default` (warm Angular app cache)
- Webhook used `browser_data_local_test_xxx` (cold cache, slow loading)

### Solution
Changed `webhook_server.py` to use `"default"` as task_id for browser data:
```python
# Before
login_handler = EncovaLogin(username=username, password=password, task_id=task_id)

# After
login_handler = EncovaLogin(username=username, password=password, task_id="default")
```

**File Changed:** `webhook_server.py` (line ~450)

---

## Issue #2: Form Not Filling (Duplicate Navigation)

### Symptom
After login, the automation kept clicking "Create a new one" button repeatedly instead of filling the form.

### Root Cause
The `run_full_automation()` method had redundant navigation:
1. Step 1 (login) → called `navigate_to_new_quote_search()` → opened form
2. Step 2 → checked if on page → called `click_create_new_account()` again (form already open!)

### Solution
Updated Step 2 to check if form is already open before trying to open it:
```python
# Step 2: Verify form is ready (login already navigated and opened form)
logger.info("Step 2: Verifying form is open...")
current_url = self.page.url
if "new-quote-account-search" not in current_url:
    if not await self.navigate_to_new_quote_search():
        logger.error("Navigation failed")
        return False
else:
    # Already on the page - check if form is already open
    form_visible = await self.page.query_selector('input[name="contactFirstName"]')
    if not form_visible:
        logger.info("Form not open yet, opening it...")
        await self.click_create_new_account()
        await self.select_commercial_radio()
        await self.wait_for_form()
    else:
        logger.info("Form already open, proceeding to fill...")
```

**File Changed:** `encova_login.py` (lines ~800-820)

---

## Issue #3: Description Field Not Filling

### Symptom
```
2025-11-26 02:11:30,691 - encova_login - WARNING - Could not fill field: textarea#inputCtrl2
```

### Root Cause
The description field was mapped as `textarea#inputCtrl2`, but inspection revealed it's actually an **input field**, not a textarea:
```html
<input type="text" id="inputCtrl2" ng-model="model.value" aria-label="ce-pl-currency-input">
```

### Solution
Updated the field mapping in `webhook_server.py`:
```python
# Before
"description": 'textarea#inputCtrl2',

# After  
"description": 'input#inputCtrl2',
```

Also added special handling for description field in `_fill_field()`:
```python
if 'inputCtrl2' in field_selector or 'description' in field_selector.lower():
    # Try input field directly with fallback to JavaScript
```

**Files Changed:** `webhook_server.py`, `encova_login.py`

---

## Issue #4: Address Validation Modal Not Detected

### Symptom
```
2025-11-26 02:11:37,722 - encova_login - INFO - Address Validation modal not visible, skipping...
```
The "Use Recommended" button wasn't being clicked even though the modal appeared.

### Root Cause
1. Modal detection checked too early (before modal appeared)
2. Wrong selectors - looking for generic `.modal-dialog` instead of specific `nbs-modal-secondary`
3. Button had class `primary-btn`, not the selectors being tried

### HTML Structure (from inspection)
```html
<div class="modal fade nbs-modal-secondary in">
  <div id="address">
    <div class="modal-header">...</div>
    <div class="modal-body">...</div>
    <div class="modal-footer">
      <button class="primary-btn" ng-click="select(recommendedAddresses[selectedAddressIndex])">
        Use Recommended
      </button>
    </div>
  </div>
</div>
```

### Solution
1. **Reordered form filling** - Fill zip code LAST (it triggers the modal)
2. **Added polling** - Check for modal up to 10 times (5 seconds)
3. **Fixed selectors** - Look for `.nbs-modal-secondary`, `#address`, `button.primary-btn`

```python
# Step 4: Fill form fields (except zip code - fill last to trigger modal)
zip_selector = None
zip_value = None
if form_data:
    for field_selector, value in form_data.items():
        if 'postalCode' in field_selector or 'zipCode' in field_selector.lower():
            zip_selector = field_selector
            zip_value = value
            continue
        await self._fill_field(field_selector, value)

# Step 5: Fill zip code (triggers address validation)
if zip_selector and zip_value:
    await self._fill_field(zip_selector, zip_value)
    await self.page.keyboard.press('Tab')  # Trigger blur
    await asyncio.sleep(2)  # Wait for modal

# Step 6: Handle modal
await self.click_use_recommended_address()
```

Modal detection with polling:
```python
for attempt in range(10):
    modal_visible = await self.page.evaluate('''
        () => {
            const addressModal = document.querySelector('.nbs-modal-secondary #address');
            if (addressModal && addressModal.offsetParent !== null) return true;
            const buttons = document.querySelectorAll('button.primary-btn');
            for (let btn of buttons) {
                if (btn.textContent.includes('Use Recommended')) return true;
            }
            return false;
        }
    ''')
    if modal_visible: break
    await asyncio.sleep(0.5)
```

**File Changed:** `encova_login.py`

---

## Issue #5: Producer Dropdown Not Filling

### Symptom
Producer dropdown opened but value wasn't selected.

### Root Cause
1. `run_full_automation()` called `_fill_searchable_dropdown()` directly
2. Should have called `select_dropdown()` which routes to `fill_producer_dropdown()` for focusser-1
3. Test data had wrong value (`"001759"` instead of `"Shahnaz Sutar"`)

### Solution
1. Updated `run_full_automation()` to use `select_dropdown()`:
```python
# Step 7: Fill dropdowns
for dropdown in dropdowns:
    selector = dropdown.get('selector')
    value = dropdown.get('value')
    if selector and value:
        await self.select_dropdown(selector, value)  # Routes to correct method
```

2. Updated `select_dropdown()` to route producer to specialized method:
```python
async def select_dropdown(self, focusser_id: str, value: str) -> bool:
    if focusser_id == "focusser-1":
        return await self.fill_producer_dropdown(value)
    return await self._fill_searchable_dropdown(focusser_id, value)
```

3. Rewrote `fill_producer_dropdown()` to search like other dropdowns:
```python
async def fill_producer_dropdown(self, producer_value: str) -> bool:
    # Open dropdown
    focusser = await self.page.wait_for_selector('input#focusser-1')
    await self._click_dropdown_toggle(focusser)
    
    # Find search input and type
    search_input = # find visible input[ng-model="$select.search"]
    await search_input.fill(producer_value)
    await search_input.press('Enter')
```

4. Updated test data:
```python
"dropdowns": {
    "state": "GA",
    "addressType": "Business",
    "contactMethod": "Email",
    "producer": "Shahnaz Sutar"  # Correct producer name
}
```

**Files Changed:** `encova_login.py`, `test_webhook_local.py`

---

## Field Mapping Reference

### Form Fields (webhook_server.py)
| Simple Name | CSS Selector |
|-------------|--------------|
| firstName | `input[name="contactFirstName"]` |
| lastName | `input[name="contactLastName"]` |
| companyName | `input[id="inputCtrl0"]` |
| fein | `input[id="inputCtrl1"]` |
| description | `input#inputCtrl2` |
| addressLine1 | `input[ng-model="addressOwner.addressLine1.value"]` |
| zipCode | `input[ng-model="addressOwner.postalCode.value"]` |
| phone | `input[id="inputCtrl13"]` |
| email | `input[id="inputCtrl14"]` |

### Dropdown Mappings
| Simple Name | Focusser ID |
|-------------|-------------|
| state | focusser-2 |
| addressType | focusser-3 |
| contactMethod | focusser-0 |
| producer | focusser-1 |

---

## Automation Flow (Final)

```
Step 1: Authenticating...
  ├── Init browser with shared browser_data_default
  ├── Load cookies
  ├── Check auto-login
  └── Navigate to new-quote-account-search

Step 2: Verifying form is open...
  └── Check if form already open, skip if yes

Step 3: Selecting MIG Customer (No)...
  └── Click md-radio-button[value="false"]

Step 4: Filling form fields (except zip)...
  ├── firstName → input[name="contactFirstName"]
  ├── lastName → input[name="contactLastName"]
  ├── companyName → input[id="inputCtrl0"]
  ├── fein → input[id="inputCtrl1"]
  ├── description → input#inputCtrl2
  ├── addressLine1 → input[ng-model="addressOwner.addressLine1.value"]
  ├── phone → input[id="inputCtrl13"]
  └── email → input[id="inputCtrl14"]

Step 5: Filling zip code (triggers address validation)...
  ├── zipCode → input[ng-model="addressOwner.postalCode.value"]
  ├── Press Tab (trigger blur)
  └── Wait 2 seconds for modal

Step 6: Handling address validation modal...
  ├── Poll for modal (up to 5 seconds)
  └── Click button.primary-btn "Use Recommended"

Step 7: Filling dropdowns...
  ├── state (focusser-2) → "GA"
  ├── addressType (focusser-3) → "Business"
  ├── contactMethod (focusser-0) → "Email"
  └── producer (focusser-1) → "Shahnaz Sutar"

Step 8: Saving form...
  └── Click button "SAVE & CLOSE"
```

---

## Key Learnings

1. **Browser Data Directory Matters** - Using a shared browser data directory preserves Angular app cache, making subsequent loads faster.

2. **Inspect the Actual HTML** - Don't assume element types (textarea vs input). Always inspect to see the actual structure.

3. **Modal Timing** - Modals triggered by blur events need time to appear. Poll for them instead of single check.

4. **Angular Dropdowns** - These searchable dropdowns need:
   - Click toggle button to open
   - Find visible search input
   - Type value
   - Press Enter to select

5. **Order of Operations** - Fill fields that trigger side effects (like zip code → address validation modal) LAST.

6. **Unique Selectors** - Use specific classes/attributes from the actual HTML rather than generic ones.

---

## Files Modified

| File | Changes |
|------|---------|
| `webhook_server.py` | Fixed task_id to "default", updated description selector |
| `encova_login.py` | Fixed navigation logic, form verification, modal detection, producer dropdown |
| `test_webhook_local.py` | Added producer to test data with correct name |

---

## Testing Commands

```powershell
# Terminal 1: Start webhook server
python webhook_server.py

# Terminal 2: Run test
python test_webhook_local.py
```

---

## Success Log Example

```
Step 1: Authenticating...
Auto-login successful - already authenticated
Step 2: Verifying form is open...
Form already open, proceeding to fill...
Step 3: Selecting MIG Customer (No)...
Successfully selected 'No' for MIG Customer
Step 4: Filling 9 form fields...
Successfully filled field using JavaScript: input[name="contactFirstName"]
...
Step 5: Filling zip code (triggers address validation)...
Step 6: Handling address validation modal...
Address Validation modal detected (attempt 3)
Successfully clicked 'Use Recommended' button
Step 7: Filling 4 dropdowns...
Successfully filled dropdown focusser-2 with: GA
Successfully filled dropdown focusser-3 with: Business
Successfully filled dropdown focusser-0 with: Email
Successfully filled Producer dropdown with: Shahnaz Sutar
Step 8: Saving form...
Successfully clicked 'Save & Close' button
Full automation completed successfully!
```

---

*Document created: November 26, 2025*
