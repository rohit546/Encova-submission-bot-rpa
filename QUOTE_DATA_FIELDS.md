# Quote Data Processing - New Fields

## Overview
The webhook now accepts additional quote data fields with automatic processing and transformation logic. The `process_quote_data()` function handles all business logic before passing data to the quote automation.

## Field Mappings

### 1. DBA (Direct Passthrough)
```json
"dba": "Ellenwood Fuel Mart"
```
→ Passes through as `dba`

### 2. Organization Type (Direct Passthrough)
```json
"org_type": "LLC"
```
→ Passes through as `org_type`
- Options: LLC, Corporation, Joint Venture, Partnership, Sole Proprietorship, etc.

### 3. Years at Location → Year Business Started (CALCULATED)
```json
"years_at_location": "8"
```
→ Calculates: `year_business_started = current_year - years_at_location`
- Example: 2026 - 8 = 2018
- Automatically uses current year

### 4. No of Gallons Annual → Class Code 13454 PremOps
```json
"no_of_gallons_annual": "500000"
```
→ Maps to: `class_code_13454_premops_annual`
- Used for fuel sales business operations

### 5. Inside Sales → Class Code 13673 PremOps
```json
"inside_sales": "150000"
```
→ Maps to: `class_code_13673_premops_annual`
- Used for retail/sales business operations

### 6. Construction Type (Direct Passthrough)
```json
"construction_type": "Masonry Non-Combustible"
```
→ Passes through as `construction_type`
- Options: Frame, Masonry, Fire Resistive, Non-Combustible, etc.

### 7. No of Stories → num_stories
```json
"no_of_stories": "1"
```
→ Maps to: `num_stories`

### 8. Square Footage (Direct Passthrough)
```json
"square_footage": "2500"
```
→ Passes through as `square_footage`

### 9. Year Built → Adjusted if < 2006 (CALCULATED)
```json
"year_built": "2003"
```
→ If year_built < 2006: add 10 years
- Example: 2003 → 2013 (added 10 years)
- Example: 2010 → 2010 (no change, >= 2006)

### 10. Limit Business Income → business_income_limit
```json
"limit_business_income": "250000"
```
→ Maps to: `business_income_limit`

### 11. Limit Personal Property → personal_property_limit
```json
"limit_personal_property": "150000"
```
→ Maps to: `personal_property_limit`

### 12. Building Description (Direct Passthrough)
```json
"building_description": "Gas Station C-Store open 18 hours"
```
→ Passes through as `building_description`

### 13. HARDCODED VALUES (Not Input Fields)
The following values are **always the same** and are hardcoded in `process_quote_data()`:
- **building_class_code**: `"Convenience Food/Gasoline Stores"` (not 60010)
- **personal_property_deductible**: `"5000"`
- **valuation**: `"Replacement Cost"`
- **coinsurance**: `"80%"`

**Do NOT send these fields in the request** - they are automatically added by the webhook server.

## Example Request

```json
{
  "action": "start_automation",
  "task_id": "local_test_123",
  "data": {
    "form_data": {
      "firstName": "Vikram",
      "lastName": "Patel",
      "companyName": "Ellenwood Fuel Mart LLC",
      "fein": "52-1478523",
      "description": "Gas station convenience store with fuel sales",
      "addressLine1": "2684 REX ROAD",
      "zipCode": "30294",
      "phone": "(770) 555-7766",
      "email": "vikram.patel@ellenwoodfuel.com"
    },
    "dropdowns": {
      "state": "GA",
      "addressType": "Business",
      "contactMethod": "Email",
      "producer": "Shahnaz Sutar"
    },
    "save_form": true,
    "run_quote_automation": true,
    "quote_data": {
      "dba": "Ellenwood Fuel Mart",
      "org_type": "LLC",
      "years_at_location": "8",
      "no_of_gallons_annual": "500000",
      "inside_sales": "150000",
      "construction_type": "Masonry Non-Combustible",
      "no_of_stories": "1",
      "square_footage": "2500",
      "year_built": "2003",
      "limit_business_income": "250000",
      "limit_personal_property": "150000",
      "building_description": "Gas Station C-Store open 18 hours"
      
      // HARDCODED (don't send these):
      // - building_class_code: "Convenience Food/Gasoline Stores"
      // - personal_property_deductible: "5000"
      // - valuation: "Replacement Cost"
      // - coinsurance: "80%"
    }
  }
}
```

## Processing Example

### Input (from webhook):
```json
{
  "dba": "Ellenwood Fuel Mart",
  "org_type": "LLC",
  "years_at_location": "8",
  "no_of_gallons_annual": "500000",
  "inside_sales": "150000",
  "year_built": "2003",
  "no_of_stories": "1",
  "square_footage": "2500",
  "construction_type": "Masonry Non-Combustible",
  "limit_business_income": "250000",
  "limit_personal_property": "150000",
  "building_description": "Gas Station C-Store open 18 hours"
}
```

### Output (after process_quote_data):
```json
{
  "dba": "Ellenwood Fuel Mart",
  "org_type": "LLC",
  "year_business_started": "2018",  // CALCULATED: 2026 - 8
  "class_code_13454_premops_annual": "500000",  // MAPPED from no_of_gallons_annual
  "class_code_13673_premops_annual": "150000",  // MAPPED from inside_sales
  "year_built": "2013",  // ADJUSTED: 2003 + 10 (< 2006)
  "num_stories": "1",  // RENAMED from no_of_stories
  "square_footage": "2500",
  "construction_type": "Masonry Non-Combustible",
  "business_income_limit": "250000",  // RENAMED from limit_business_income
  "personal_property_limit": "150000",  // RENAMED from limit_personal_property
  "building_description": "Gas Station C-Store open 18 hours",
  
  // HARDCODED VALUES (automatically added):
  "building_class_code": "Convenience Food/Gasoline Stores",
  "personal_property_deductible": "5000",
  "valuation": "Replacement Cost",
  "coinsurance": "80%"
}
```

## Testing

Run the test file to verify:
```powershell
cd "c:\Users\Dell\Desktop\RPA For a\automation"
python test_webhook_local.py
```

The test includes dummy data that demonstrates all transformations:
- Years calculation: 8 years → 2018
- Year adjustment: 2003 → 2013 (added 10 years)
- Class code mapping: gallons and inside sales
- Field renaming: stories, limits, etc.

## Implementation Files

1. **webhook_server.py**
   - Added `process_quote_data()` function (lines ~220-340)
   - Updated `run_automation_task()` to call processing function
   - Logs all transformations for debugging

2. **test_webhook_local.py**
   - Updated with complete dummy data
   - Documents all field transformations in header
   - Tests all new calculations

## Logging

The processing function logs all transformations:
```
[INFO] Calculated year_business_started: 2026 - 8 = 2018
[INFO] Mapped no_of_gallons_annual to class_code_13454_premops_annual: 500000
[INFO] Mapped inside_sales to class_code_13673_premops_annual: 150000
[INFO] Adjusted year_built: 2003 -> 2013 (added 10 years because < 2006)
[INFO] Processed quote_data: 11 fields -> 11 processed fields
```

Check logs at: `c:\Users\Dell\Desktop\RPA For a\automation\logs\webhook_server.log`
