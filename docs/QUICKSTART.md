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

### Step 2: Install the Required Python Package

The integration needs the `uk-fuel-prices-api` package. Home Assistant should install this automatically, but if you encounter issues:

**SSH into your Home Assistant instance and run:**
```bash
pip install uk-fuel-prices-api
```

Or if using Home Assistant Container:
```bash
docker exec -it homeassistant pip install uk-fuel-prices-api
```

### Step 3: Add the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Fuel Prices UK"
4. Click on it to start configuration

### Step 4: Configure

1. **Update Interval**: Enter how often to check prices in seconds
   - Minimum: 300 (5 minutes)
   - Recommended: 3600 (1 hour)
   - Maximum: 86400 (24 hours)

2. **Location**: Click on the map to set your monitoring location
   - Defaults to your Home Assistant location
   - You can select any location in the UK

3. **Radius**: Enter search radius in kilometers (1-50)
   - Recommended: 5-10 km for urban areas
   - Larger radius for rural areas

4. **Fuel Types**: Select which fuel types to monitor
   - E10 (Standard unleaded)
   - E5 (Super unleaded)
   - B7 (Diesel)
   - SDV (Super diesel)

5. Click **Submit**

### Step 5: View Your Sensors

After setup, sensors will be created:
- `sensor.cheapest_e10_price`
- `sensor.cheapest_b7_price`
- `sensor.cheapest_e5_price`
- `sensor.cheapest_sdv_price`

Each sensor shows:
- **State**: Cheapest price in £/L
- **Attributes**: Station name, address, brand, distance, etc.

## Example Lovelace Card

Add this to your dashboard to see prices:

```yaml
type: entities
title: Cheapest Fuel Prices
entities:
  - entity: sensor.cheapest_e10_price
    name: Unleaded (E10)
    icon: mdi:gas-station
    secondary_info: last-updated
  - entity: sensor.cheapest_b7_price
    name: Diesel (B7)
    icon: mdi:gas-station
    secondary_info: last-updated
```

## Troubleshooting

### No Sensors Appearing
1. Check **Settings** → **System** → **Logs** for errors
2. Verify the integration is loaded: **Developer Tools** → **Services** → look for `fuel_prices_uk`
3. Try restarting Home Assistant

### "Could not load uk-fuel-prices-api" Error
Run this in your HA environment:
```bash
pip install uk-fuel-prices-api geopy
```

### Sensors Show "Unavailable"
1. Wait for the first update (check your update interval)
2. Try increasing the search radius
3. Verify you have internet connectivity
4. Check if there are stations in your area on [gov.uk/guidance/access-fuel-price-data](https://www.gov.uk/guidance/access-fuel-price-data)

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
