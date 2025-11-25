"""
Test automation locally on PC (not via Railway webhook)
Uses the same mapping logic as webhook_server.py
"""
import os
# Disable tracing for local testing - MUST be set before any imports
os.environ['ENABLE_TRACING'] = 'False'

import asyncio
import sys
import time
from pathlib import Path
from encova_login import EncovaLogin

# Import mapping functions from webhook_server
from webhook_server import map_form_data, map_dropdowns

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

async def test_local_automation():
    """Run automation locally and generate trace"""
    print("=" * 80)
    print("LOCAL AUTOMATION TEST")
    print("=" * 80)
    
    # Test data - same format as Railway webhook (simple field names)
    task_id = f"local_test_{int(time.time())}"
    simple_form_data = {
        "firstName": "Michael",
        "lastName": "Johnson",
        "companyName": "Rincon Business Solutions",
        "fein": "98-7654321",
        "description": "Retail store with customer service",
        "addressLine1": "332 Saint Andrews Rd",
        "zipCode": "31326",
        "phone": "(912) 555-9876",
        "email": "test.rincon@example.com"
    }
    
    simple_dropdowns = {
        "state": "GA",
        "addressType": "Business",
        "contactMethod": "Email"
    }
    
    print(f"\n📋 Task ID: {task_id}")
    print(f"📝 Address: 332 Saint Andrews Rd, Rincon, GA, 31326, USA")
    print(f"📊 Form fields: {len(simple_form_data)}")
    print(f"📊 Dropdowns: {len(simple_dropdowns)}")
    
    # Map simple field names to CSS selectors (same as webhook_server)
    form_data = map_form_data(simple_form_data)
    dropdowns = map_dropdowns(simple_dropdowns)
    
    print(f"\n✅ Mapped {len(form_data)} form fields to CSS selectors")
    print(f"✅ Mapped {len(dropdowns)} dropdowns")
    
    # Initialize automation
    login_handler = None
    try:
        print(f"\n🚀 Starting local automation...")
        login_handler = EncovaLogin(task_id=task_id)
        
        # Login
        print(f"\n🔐 Attempting login...")
        login_success = await login_handler.login()
        
        if not login_success:
            print(f"\n❌ Login failed!")
            return
        
        print(f"\n✅ Login successful!")
        
        # Navigate to form
        print(f"\n📄 Navigating to form...")
        await login_handler.navigate_to_new_quote_search()
        
        # Fill form using _fill_field method (same as webhook_server)
        print(f"\n✍️  Filling form fields...")
        filled_count = 0
        address_validation_used = False
        address_line1_filled = False
        zip_code_filled = False
        
        for field_selector, value in form_data.items():
            try:
                success = await login_handler._fill_field(field_selector, value)
                if success:
                    filled_count += 1
                    print(f"   ✅ Filled: {field_selector[:50]}...")
                    
                    # Check if we filled address fields
                    if 'addressLine1' in field_selector or 'addressOwner.addressLine1' in field_selector:
                        address_line1_filled = True
                    if 'postalCode' in field_selector or 'zipCode' in field_selector or 'addressOwner.postalCode' in field_selector:
                        zip_code_filled = True
                    
                    # If both address line 1 and zip code are filled, check for address validation popup
                    if address_line1_filled and zip_code_filled and not address_validation_used:
                        print(f"\n   🔍 Checking for Address Validation popup...")
                        address_validation_used = await login_handler.click_use_recommended_address()
                        if address_validation_used:
                            print(f"   ✅ Address Validation used - State will be auto-filled")
                else:
                    print(f"   ❌ Failed: {field_selector[:50]}...")
            except Exception as e:
                print(f"   ❌ Error: {field_selector[:50]}... - {e}")
        
        print(f"\n✅ Filled {filled_count}/{len(form_data)} fields")
        
        # Fill dropdowns using select_dropdown method (same as webhook_server)
        # Skip state dropdown if address validation was used
        print(f"\n📋 Filling dropdowns...")
        for i, dropdown in enumerate(dropdowns, 1):
            selector = dropdown.get('selector')
            value = dropdown.get('value')
            if selector and value:
                # Skip state dropdown (focusser-2) if address validation was used
                if address_validation_used and selector == 'focusser-2':
                    print(f"   ⏭️  Skipping state dropdown (focusser-2) - auto-filled by Address Validation")
                    continue
                
                try:
                    await login_handler.select_dropdown(selector, value)
                    print(f"   ✅ Dropdown {i}/{len(dropdowns)}: {selector} = {value}")
                except Exception as e:
                    print(f"   ❌ Dropdown {i}/{len(dropdowns)} failed: {e}")
        
        # Save form using click_save_and_close_button method
        print(f"\n💾 Saving form...")
        save_success = await login_handler.click_save_and_close_button()
        
        if save_success:
            print(f"\n✅ Form saved successfully!")
        else:
            print(f"\n⚠️  Save button click may have failed")
        
        print(f"\n{'=' * 80}")
        print(f"✅ AUTOMATION COMPLETED")
        print(f"{'=' * 80}")
        
        # Trace is disabled for local testing
        print(f"\n📦 Tracing: Disabled for local testing")
        
        # Show screenshots
        screenshots = login_handler.list_screenshots()
        if screenshots:
            print(f"\n📸 Screenshots: {len(screenshots)} taken")
            print(f"   📁 Directory: {login_handler.get_screenshot_dir()}")
        
    except Exception as e:
        print(f"\n❌ Error during automation: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Close browser
        if login_handler:
            print(f"\n🔒 Closing browser...")
            await login_handler.close()
            print(f"✅ Browser closed")
    
    print(f"\n{'=' * 80}")

if __name__ == "__main__":
    asyncio.run(test_local_automation())

