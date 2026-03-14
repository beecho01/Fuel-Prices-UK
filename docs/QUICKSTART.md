# Quick Start Guide - Fuel Prices UK Integration

## Installation Steps

### Step 1: Install the Integration

Choose one of these methods:

#### Option A: Via HACS (Recommended)
1. Open HACS in Home Assistant
2. Go to "Integrations"  
3. Click the three dots (⋮) → "Custom repositories"
4. Add repository URL: `https://github.com/beecho01/Fuel-Prices-UK`
5. Category: "Integration"
6. Click "Add"
7. Find "Fuel Prices UK" and click "Download"
8. Restart Home Assistant

#### Option B: Manual Installation
1. Download this repository as a ZIP file
2. Extract it
3. Copy the `custom_components/fuel_prices_uk` folder to your Home Assistant `custom_components` directory
4. Restart Home Assistant

### Step 2: Create Fuel Finder API Credentials

1. Go to the [Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk/public-api)
2. Sign in with GOV.UK One Login
3. Create an Information Recipient application
4. Copy your `client_id` and `client_secret`

Keep these secure. You will enter them in Home Assistant during setup.

### Step 3: Add the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Fuel Prices UK"
4. Click on it to start configuration

### Step 4: Configure

1. **Fuel Finder API Client ID**
2. **Fuel Finder API Client Secret**
3. **Location Input Method**: map or address/postcode
4. **Update Interval**: Enter how often to check prices in seconds
   - Minimum: 300 (5 minutes)
   - Recommended: 3600 (1 hour)
   - Maximum: 86400 (24 hours)

5. **Location**: Click on the map (or enter address/postcode)
   - Defaults to your Home Assistant location
   - You can select any location in the UK

6. **Radius**: Enter search radius in miles (0.5-31)
   - Recommended: 3-6 miles for urban areas
   - Larger radius for rural areas

7. **Fuel Types**: Select which fuel types to monitor
   - E10 (Standard unleaded)
   - E5 (Super unleaded)
   - B7 (Diesel)
   - SDV (Super diesel)

8. Click **Submit**

### Step 5: View Your Sensors

After setup, sensors will be created:
- `sensor.fuel_price_uk_[location]_cheapest_e10`
- `sensor.fuel_price_uk_[location]_cheapest_b7`
- `sensor.fuel_price_uk_[location]_cheapest_e5`
- `sensor.fuel_price_uk_[location]_cheapest_sdv`

Each sensor shows:
- **State**: Cheapest price in £/L
- **Attributes**: Station name, address, brand, distance, etc.

## Example Lovelace Card

Add this to your dashboard to see prices:

```yaml
type: entities
title: Cheapest Fuel Prices
entities:
   - entity: sensor.fuel_price_uk_home_3_mi_cheapest_e10
    name: Unleaded (E10)
    icon: mdi:gas-station
    secondary_info: last-updated
   - entity: sensor.fuel_price_uk_home_3_mi_cheapest_b7
    name: Diesel (B7)
    icon: mdi:gas-station
    secondary_info: last-updated
```

Note: Standard `entities` cards do not evaluate Jinja templates in `secondary_info`.
Use custom cards (for example `custom:template-entity-row`) if you want attribute templating in row text.

## Troubleshooting

### No Sensors Appearing
1. Check **Settings** → **System** → **Logs** for errors
2. Verify the integration is loaded: **Developer Tools** → **Services** → look for `fuel_prices_uk`
3. Try restarting Home Assistant

### "Invalid API credentials" Error

- Re-check your Fuel Finder `client_id` and `client_secret`
- Confirm you created an Information Recipient app (not trader submission credentials)
- Try creating a fresh token in the Fuel Finder portal and update the integration options

### Sensors Show "Unavailable"
1. Wait for the first update (check your update interval)
2. Try increasing the search radius
3. Verify you have internet connectivity
4. Verify Fuel Finder service availability in your area from the [Fuel Finder developer docs](https://www.developer.fuel-finder.service.gov.uk/public-api)

### Update Configuration
To change settings:
1. Go to **Settings** → **Devices & Services**
2. Find "Fuel Prices UK"
3. Click **Configure**
4. Update your settings

To change location:
- You need to remove and re-add the integration

## What's Next?

- Add sensors to your dashboard
- Create automations based on fuel prices
- Set up notifications when prices drop
- Use the data in your energy monitoring

## Support

Need help?
- [Open an issue on GitHub](https://github.com/beecho01/Fuel-Prices-UK/issues)
- Check the [full README](README.md) for more details
- Look at existing issues for solutions

Enjoy monitoring fuel prices! ⛽️
