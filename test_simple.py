"""
Simple test script - Complete form automation
"""
import asyncio
from encova_login import EncovaLogin
from config import WAIT_MEDIUM

async def test_simple_form():
    """Test login and fill simple text fields"""
    
    # Credentials
    username = "shahnaz@mckinneyandco.com"
    password = "October#2025"
    
    print("\n" + "="*60)
    print("SIMPLE FORM FILLING TEST")
    print("="*60)
    
    # Initialize
    login_handler = EncovaLogin(username=username, password=password)
    
    try:
        # Step 1: Login and navigate to form
        print("\n[1/3] Logging in and opening form...")
        success = await login_handler.login()
        
        if not success:
            print("  [ERROR] Login failed!")
            return False
        
        print("  [OK] Login successful and form is open!")
        
        # Step 2: Fill simple text fields
        print("\n[2/3] Filling text fields...")
        
        # Define the text fields we want to fill (BEFORE address validation)
        # Fill in correct order: Company Name first, then Description in separate field
        initial_fields = {
            'input[name="contactFirstName"]': 'John',
            'input[name="contactLastName"]': 'Doe',
            'input[id="inputCtrl0"]': 'Test Company Inc',  # Company Name - id="inputCtrl0" (screenshot 1)
            'input[id="inputCtrl1"]': '12-3456789',  # FEIN ID - id="inputCtrl1" (screenshot 4)
        }
        
        # Fill initial fields first
        filled_count = 0
        for selector, value in initial_fields.items():
            success = await login_handler._fill_field(selector, value)
            if success:
                filled_count += 1
                field_name = selector.split('[')[-1].replace(']', '').replace('"', '').split('=')[-1]
                print(f"  [OK] Filled: {field_name}")
            else:
                print(f"  [FAIL] Failed: {selector}")
        
        # Fill Description field separately (after company name)
        # Wait a bit to ensure Company Name field is done
        await asyncio.sleep(WAIT_MEDIUM)
        print(f"\n  Filling Description field...")
        # Use more specific selector - Description field should be after Company field
        description_success = await login_handler._fill_field(
            'input[ng-model="model.value"][ng-trim="true"]', 
            'C-Store with 18 hours operation',
            field_label="Description of Business"
        )
        if description_success:
            filled_count += 1
            print(f"  [OK] Filled: Description")
        else:
            print(f"  [FAIL] Failed: Description field")
        
        # Now fill address fields that will trigger validation
        address_fields = {
            'input[ng-model="addressOwner.addressLine1.value"]': '280 Griffin',
            'input[ng-model="addressOwner.postalCode.value"]': '30253',  # McDonough, GA zip code
        }
        
        print(f"\n  Filling address fields (will trigger validation)...")
        for selector, value in address_fields.items():
            success = await login_handler._fill_field(selector, value)
            if success:
                filled_count += 1
                field_name = selector.split('[')[-1].replace(']', '').replace('"', '').split('=')[-1]
                print(f"  [OK] Filled: {field_name}")
            else:
                print(f"  [FAIL] Failed: {selector}")
        
        # Wait and click "Use Recommended" button to auto-fill City, County, State
        print(f"\n  [WAIT] Waiting for Address Validation modal...")
        use_recommended_success = await login_handler.click_use_recommended_address()
        
        if use_recommended_success:
            print(f"  [OK] Clicked 'Use Recommended' - City, County, State auto-filled!")
            filled_count += 3  # Count city, county, state as filled
        else:
            print(f"  [WARN] Address validation modal not found - filling manually...")
            # Fallback: fill manually
            manual_fields = {
                'input[ng-model="addressOwner.city.value"]': 'McDonough',
                'input[ng-model="addressOwner.county.value"]': 'Henry',
            }
            for selector, value in manual_fields.items():
                success = await login_handler._fill_field(selector, value)
                if success:
                    filled_count += 1
        
        # Fill remaining fields
        print(f"\n  Filling remaining fields...")
        
        # Office Phone - id="inputCtrl13" (screenshot 2)
        await asyncio.sleep(WAIT_MEDIUM)
        phone_success = await login_handler._fill_field(
            'input[id="inputCtrl13"]', 
            '(404) 555-1234',
            field_label="Office Phone"
        )
        if phone_success:
            filled_count += 1
            print(f"  [OK] Filled: Office Phone")
        else:
            print(f"  [FAIL] Failed: Office Phone")
        
        # Email Address - id="inputCtrl14" (from screenshot)
        await asyncio.sleep(WAIT_MEDIUM)
        email_success = await login_handler._fill_field(
            'input[id="inputCtrl14"]', 
            'test@email.com',
            field_label="Email Address"
        )
        if email_success:
            filled_count += 1
            print(f"  [OK] Filled: Email Address")
        else:
            print(f"  [FAIL] Failed: Email Address")
        
        text_fields = {**initial_fields, **address_fields}
        
        print(f"\n  Total: {filled_count}/{len(text_fields)} fields filled (with auto-fill)")
        
        # Step 3: Select MIG Radio Button (No)
        print("\n[3/8] Selecting MIG Customer radio (No)...")
        mig_success = await login_handler.select_mig_radio_yes()
        
        if mig_success:
            print("  [OK] MIG radio button selected: No")
        else:
            print("  [FAIL] MIG radio button failed")
        
        # Step 4: Fill State dropdown
        print("\n[4/8] Filling State dropdown...")
        state_success = await login_handler.fill_state_dropdown("GA")  # Georgia
        
        if state_success:
            print("  [OK] State dropdown filled with: GA")
        else:
            print("  [FAIL] State dropdown failed")
        
        # Step 5: Fill Address Type dropdown
        print("\n[5/8] Filling Address Type dropdown...")
        address_type_success = await login_handler.fill_address_type_dropdown("Business")
        
        if address_type_success:
            print("  [OK] Address Type dropdown filled with: Business")
        else:
            print("  [FAIL] Address Type dropdown failed")
        
        # Step 6: Fill Preferred Contact Method dropdown
        print("\n[6/8] Filling Preferred Contact Method dropdown...")
        contact_success = await login_handler.fill_preferred_contact_dropdown("Email")
        
        if contact_success:
            print("  [OK] Preferred Contact Method dropdown filled with: Email")
        else:
            print("  [FAIL] Preferred Contact Method dropdown failed")
        
        # Step 7: Fill Producer dropdown
        print("\n[7/8] Filling Producer dropdown...")
        # Use "Shahnaz" or "AO479-1001" or any text that appears in the producer option
        producer_success = await login_handler.fill_producer_dropdown("Shahnaz")
        
        if producer_success:
            print("  [OK] Producer dropdown filled with: Shahnaz")
        else:
            print("  [FAIL] Producer dropdown failed")
        
        # Step 8: Click Save & Close button
        print("\n[8/9] Clicking 'Save & Close' button to save the form...")
        save_success = await login_handler.click_save_and_close_button()
        
        if save_success:
            print("  [OK] Successfully clicked 'Save & Close' - form saved!")
        else:
            print("  [FAIL] Could not click 'Save & Close' button")
        
        # Step 9: Keep browser open for verification
        print("\n[9/9] Browser will stay open for 30 seconds for verification...")
        print("="*60)
        await asyncio.sleep(30)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {e}")
        return False
        
    finally:
        await login_handler.close()
        print("\n[INFO] Browser closed.")

if __name__ == "__main__":
    asyncio.run(test_simple_form())

