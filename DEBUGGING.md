# Debugging Guide

## Enable Debug Logging

To see detailed logs from the Fuel Prices UK integration, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.fuel_prices_uk: debug
```

After adding this, restart Home Assistant.

## Viewing Logs

### Method 1: Settings UI
1. Go to **Settings** → **System** → **Logs**
2. Look for entries starting with `custom_components.fuel_prices_uk`

### Method 2: Home Assistant Logs File
View the log file directly:
```bash
# In Home Assistant container
docker exec homeassistant cat /config/home-assistant.log | grep fuel_prices_uk

# Or on the host machine
tail -f /path/to/config/home-assistant.log | grep fuel_prices_uk
```

## What to Look For

### Successful Setup
You should see:
```
[custom_components.fuel_prices_uk] Setting up Fuel Prices UK config entry: <entry_id>
[custom_components.fuel_prices_uk] Update interval set to: <interval>
[custom_components.fuel_prices_uk] Initializing coordinator with location=..., radius=..., fuel_types=..., update_interval=...
```

### Data Updates
Every update interval, you should see:
```
[custom_components.fuel_prices_uk] Starting data update cycle
[custom_components.fuel_prices_uk] Search coordinates: lat=..., lon=...
[custom_components.fuel_prices_uk] Fuel types to search: [...]
[custom_components.fuel_prices_uk] Performing radius-based search: lat=..., lon=..., radius=... km
[custom_components.fuel_prices_uk.fetch_prices] Fetching stations within radius: lat=..., lon=..., radius_km=...
[custom_components.fuel_prices_uk] Successfully fetched X stations
```

### Sensor Updates
When sensors update:
```
[custom_components.fuel_prices_uk.sensor] Setting up sensors for fuel types: [...]
[custom_components.fuel_prices_uk.sensor] Data available for update, processing X stations
[custom_components.fuel_prices_uk.sensor] Found cheapest E10 price: X.XXp at Station Name
```

## Common Issues

### No Logs Appearing
1. **Check logger configuration** - Make sure you added the logger config to `configuration.yaml`
2. **Restart Home Assistant** - Logging config requires a restart
3. **Check integration is loaded** - Go to Settings → Devices & Services and verify "Fuel Prices UK" is listed

### No Data/Stations Found
Look for these messages:
```
[custom_components.fuel_prices_uk.fetch_prices] No stations found within X km radius
[custom_components.fuel_prices_uk] Successfully fetched 0 stations
```

**Solutions:**
- Increase the search radius (try 10-15 miles)
- Verify your location is in the UK
- Check that fuel stations exist in your area

### API Errors
Look for:
```
[custom_components.fuel_prices_uk.fetch_prices] API error: ...
[custom_components.fuel_prices_uk] Error fetching data: ...
```

**Solutions:**
- Check your internet connection
- Verify the API is accessible: https://api.fuel-prices.co.uk
- Wait a few minutes and let the integration retry

### Address Lookup Failures
```
[custom_components.fuel_prices_uk.config_flow] Could not find location for: <address>
```

**Solutions:**
- Try a different format (postcode only, full address, city name)
- Use the map-based location selector instead
- Verify the postcode/address is valid and in the UK

## Testing Immediately

To force an immediate update without waiting for the update interval:

1. Go to **Developer Tools** → **Services**
2. Call service: `homeassistant.update_entity`
3. Select your fuel price sensor entity
4. Click "Call Service"
5. Check logs immediately

## Example Full Log Sequence

```
2025-11-21 10:00:00 INFO [custom_components.fuel_prices_uk] Setting up Fuel Prices UK config entry: abc123
2025-11-21 10:00:00 INFO [custom_components.fuel_prices_uk] Update interval set to: 1:00:00
2025-11-21 10:00:00 INFO [custom_components.fuel_prices_uk] Initializing coordinator with location={'latitude': 51.5074, 'longitude': -0.1278}, radius=5.0 km, fuel_types=['E10', 'B7'], update_interval=1:00:00
2025-11-21 10:00:01 INFO [custom_components.fuel_prices_uk] Starting data update cycle
2025-11-21 10:00:01 INFO [custom_components.fuel_prices_uk] Search coordinates: lat=51.5074, lon=-0.1278
2025-11-21 10:00:01 INFO [custom_components.fuel_prices_uk] Fuel types to search: ['E10', 'B7']
2025-11-21 10:00:01 INFO [custom_components.fuel_prices_uk] Performing radius-based search: lat=51.5074, lon=-0.1278, radius=5.0 km
2025-11-21 10:00:01 DEBUG [custom_components.fuel_prices_uk.fetch_prices] Fetching stations within radius: lat=51.5074, lon=-0.1278, radius_km=5.0
2025-11-21 10:00:02 INFO [custom_components.fuel_prices_uk] Successfully fetched 15 stations
2025-11-21 10:00:02 INFO [custom_components.fuel_prices_uk.sensor] Setting up sensors for fuel types: ['E10', 'B7']
2025-11-21 10:00:02 INFO [custom_components.fuel_prices_uk.sensor] Creating sensor for E10
2025-11-21 10:00:02 INFO [custom_components.fuel_prices_uk.sensor] Creating sensor for B7
2025-11-21 10:00:03 DEBUG [custom_components.fuel_prices_uk.sensor] Data available for update, processing 15 stations
2025-11-21 10:00:03 INFO [custom_components.fuel_prices_uk.sensor] Found cheapest E10 price: 134.9p at Tesco Superstore
```

## Still Having Issues?

1. **Collect full logs** - Copy all lines containing `fuel_prices_uk`
2. **Check Home Assistant version** - Must be 2023.8.0 or newer
3. **Verify installation** - Check `custom_components/fuel_prices_uk/` exists
4. **Create GitHub issue** - https://github.com/beecho01/Fuel-Prices-UK/issues with logs attached
