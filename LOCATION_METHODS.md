# Location Input Methods

The Fuel Prices UK integration now supports **two methods** for specifying your location:

## 1. Map-based Location (Default)
- **Interactive map interface** - visually select your location
- **Visual radius circle** displayed on the map
- **Uses Home Assistant's location** as default starting point
- Best for: Users who prefer visual selection

## 2. Address/Postcode Input
- **Text input** for UK postcodes, addresses, or location names
- **Automatic geocoding** using:
  - **postcodes.io API** for UK postcodes
  - **Nominatim** for addresses and place names
  - **Direct coordinate input** (format: `lat,long`)
- Best for: Users who know their exact postcode/address

## Configuration Flow

### Initial Setup
1. **Choose Location Method**: Select "Map" or "Address or Postcode"
2. **Configure Settings**: Based on your choice:
   - **Map**: Select location on interactive map
   - **Address**: Enter postcode (e.g., "SW1A 1AA"), address, or place name
3. **Set Radius**: Specify search radius in miles (0.5-31 miles)
4. **Select Fuel Types**: Choose which fuel types to monitor
5. **Set Update Interval**: How often to fetch prices (5 min - 24 hours)

**Note**: When using the map method, the radius circle is displayed based on the initial radius value. If you change the radius number, the circle will update when you submit the form and re-open the configuration. This is a limitation of Home Assistant's UI framework.

### Options/Reconfiguration
- Can **switch between methods** when reconfiguring
- All settings can be updated including location method
- Original address stored for reference when using address method

## Examples

### Valid Address/Postcode Inputs:
- `SW1A 1AA` - UK postcode
- `10 Downing Street, London` - Full address
- `Manchester` - City name
- `51.5074,-0.1278` - Direct coordinates (lat,long)

### How Location Lookup Works:
1. **Check if coordinates**: Parse `lat,long` format
2. **Check if postcode**: Validate and lookup via postcodes.io
3. **Check if location name**: Search postcodes.io places database
4. **Fallback to Nominatim**: Broader geocoding search (UK only)

## Technical Details

### Storage
- **Location**: Stored as `{latitude, longitude}` dict
- **Method**: Tracked with `location_method` key ("map" or "address")
- **Address**: Original address string stored when using address method
- **Radius**: Stored in **kilometers** internally, displayed in **miles**

### API Integration
- Both methods provide coordinates to the `uk-fuel-prices-api`
- No difference in API behavior between methods
- Address lookup happens **only during configuration**, not at runtime

### Dependencies
- **geopy** (>=2.2.0): For geocoding and distance calculations
- **postcodes.io**: Free UK postcode lookup API
- **Nominatim**: OpenStreetMap geocoding service

## Benefits of Dual Method Support

✅ **Flexibility**: Users choose their preferred input method
✅ **Accuracy**: Postcodes provide precise UK locations
✅ **Compatibility**: Works with existing map-based configs
✅ **Convenience**: Quick setup for users who know their postcode
✅ **Accessibility**: Text input may be easier for some users

## Error Handling

### Address Lookup Errors:
- **Invalid postcode**: "Could not find location. Please check your postcode/address and try again."
- **Unknown location**: Fallback to Nominatim for broader search
- **Network errors**: Logged with details for troubleshooting
- **Geocoder unavailable**: Graceful error message displayed

### Debug Logging:
Enable debug logging to see location lookup details:
```yaml
logger:
  default: info
  logs:
    custom_components.fuel_prices_uk: debug
```

Logs include:
- Address/postcode being looked up
- Coordinates found
- API calls to postcodes.io and Nominatim
- Lookup failures with reasons
