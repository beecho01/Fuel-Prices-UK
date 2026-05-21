<p align="center"><img src="images/icon.png" width="140" style="vertical-align: middle;"></p>

<h1 align="center">Fuel Prices UK - Home Assistant Integration</h1>

<p align="center">
   <em>
      A Home Assistant custom integration that monitors fuel prices at UK petrol stations using official government data feeds. 
      <p align="center">
         Find the cheapest fuel near you!
      </p>
   </em>
</p>

<br>

<div>
  <p align="center">
    <img src="https://img.shields.io/github/languages/top/beecho01/Fuel-Prices-UK?style=for-the-badge&color=012169">
    <img src="https://img.shields.io/github/languages/code-size/beecho01/Fuel-Prices-UK?style=for-the-badge&color=FFFFFF">
    <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/github/license/beecho01/Fuel-Prices-UK?style=for-the-badge&logoColor=white&label=License&color=C8102E"></a>
  </p>
</div>

## Features

- ✅ **Official Fuel Finder API** - Uses the UK Government Fuel Finder API (OAuth-protected)
- ✅ **Real-time Price Monitoring** - Track E10, E5, B7 (Diesel), and SDV (Super Diesel) prices
- ✅ **Location-Based Search** - Find stations within a specified radius of your home or any location
- ✅ **Automatic Updates** - Configurable update intervals from 5 minutes to 24 hours
- ✅ **Easy Setup** - Simple configuration flow with map-based location selection
- ✅ **Cheapest Price Sensors** - Automatically shows the cheapest price for each fuel type
- ✅ **Ranked Cheapest Options** - Optionally expose 2nd, 3rd (up to 5th) cheapest stations per fuel type

## Supported Fuel Types

- **E10** - Standard unleaded petrol (10% ethanol)
- **E5** - Super unleaded petrol (5% ethanol)
- **B7** - Standard diesel (7% bio-diesel)
- **SDV** - Super diesel / Premium diesel

## Fuel Finder API Access

This integration now uses the UK Government Fuel Finder platform directly:

- Public data API: `GET /api/v1/pfs` and `GET /api/v1/pfs/fuel-prices`
- Authentication: OAuth client credentials via `POST /api/v1/oauth/generate_access_token`
- Documentation: [Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk/public-api)

You must create your own API application credentials before setup.

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository in HACS:
   - Click on HACS in the sidebar
   - Click on "Integrations"
   - Click the three dots in the top right corner
   - Select "Custom repositories"
   - Enter the repository URL: `https://github.com/beecho01/Fuel-Prices-UK`
   - Select category: "Integration"
   - Click "Add"
3. Find "Fuel Prices UK" in the HACS integration list
4. Click "Download"
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/beecho01/Fuel-Prices-UK/releases)
2. Extract the `custom_components/fuel_prices_uk` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Setup via UI

Before adding the integration, create API credentials:

1. Sign in at the [Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk/public-api)
2. Create an Information Recipient application
3. Copy your `client_id` and `client_secret`

Then in Home Assistant:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Fuel Prices UK"
4. Follow the configuration wizard:
  - **Fuel Finder API Client ID**
  - **Fuel Finder API Client Secret**
  - **Location Method** (map or address/postcode)
  - **Update Interval**: How often to fetch prices (minimum 300 seconds)
  - **Location**: Map pin or address/postcode lookup
  - **Search Radius**: Distance in miles (0.5-31)
  - **Fuel Types**: Fuel types to monitor

### Configuration Options

After setup, you can update these settings by clicking **Configure** on the integration:

- Fuel Finder API credentials
- Update interval
- Search radius
- Fuel types to monitor
- Number of cheapest options to expose per fuel type (1-5)

---

### Setup via `configuration.yaml`

As an alternative to the UI wizard, you can configure the integration in `configuration.yaml`.
This is particularly useful for keeping credentials out of the UI by using [Home Assistant secrets](https://www.home-assistant.io/docs/configuration/secrets/) (`!secret`).

> **Note:** On first load, HA reads the YAML block and creates a normal config entry automatically.
> Once the entry is created you can remove the YAML block — the entry persists independently.
> If the block remains, HA will silently skip it on subsequent restarts (duplicate detection via unique ID).

#### Configuration reference

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | No¹ | — | Human-readable name for this instance. Used as the entry title and to uniquely distinguish multiple instances that share the same API credentials. |
| `client_id` | string | **Yes** | — | Fuel Finder API client ID. Use `!secret` to keep it out of plain text. |
| `client_secret` | string | **Yes** | — | Fuel Finder API client secret. Use `!secret` to keep it out of plain text. |
| `location` | mapping | No | HA home location | Location block — see sub-keys below. Omit entirely to use HA's configured home coordinates. |
| `location.postcode` | string | No² | — | UK postcode (e.g. `SW1A 1AA`). Resolved via postcodes.io. |
| `location.address` | string | No² | — | Free text address or place name (e.g. `"10 Downing Street, London"`). Resolved via Nominatim. |
| `location.lat` | float | No² | — | Latitude in decimal degrees. Must be paired with `location.long`. |
| `location.long` | float | No² | — | Longitude in decimal degrees. Must be paired with `location.lat`. |
| `radius` | mapping | No | 3 miles | Search radius block — see sub-keys below. |
| `radius.type` | string | **Yes** (if `radius` present) | — | Unit for the radius value. Must be `miles` or `km`. |
| `radius.value` | float | **Yes** (if `radius` present) | — | Numeric radius value (0.1 – 200). |
| `fuel_types` | mapping | No | E10 + B7 | Boolean map of fuel types to monitor. Omit a key or set it to `false` to skip that fuel. |
| `fuel_types.E10` | boolean | No | `true` | E10 — standard unleaded petrol. |
| `fuel_types.E5` | boolean | No | `false` | E5 — super unleaded petrol. |
| `fuel_types.B7` | boolean | No | `true` | B7 — standard diesel. |
| `fuel_types.SDV` | boolean | No | `false` | SDV — super / premium diesel. |
| `count` | mapping | No | — | Sensor count options. |
| `count.cheapest` | integer | No | `3` | Number of cheapest-ranked sensors to create per fuel type (0 – 5). `0` disables cheapest sensors. |
| `count.nearest` | integer | No | `0` | Number of nearest-distance sensors to create per fuel type (0 – 5). `0` disables nearest sensors. |
| `ignore_stale_data_days` | integer | No | `0` | Skip stations whose price data is older than this many days. `0` means no limit. |
| `update_interval` | integer | No | `3600` | How often to poll for new prices, in seconds (300 – 86400). |

¹ `name` is optional for a single instance but **strongly recommended** when configuring multiple locations under the same domain key.  
² Only one of `postcode`, `address`, or `lat`+`long` should be set. Priority order if multiple keys are present: `postcode` → `address` → `lat`+`long`.

#### Examples

**Minimal — postcode location, secrets for credentials:**

```yaml
fuel_prices_uk:
  client_id: !secret fuel_uk_client_id
  client_secret: !secret fuel_uk_client_secret
  location:
    postcode: "SW1A 1AA"
```

**Full single-location example:**

```yaml
fuel_prices_uk:
  name: Home
  client_id: !secret fuel_uk_client_id
  client_secret: !secret fuel_uk_client_secret
  location:
    postcode: "SW1A 1AA"
  radius:
    type: miles
    value: 5.0
  fuel_types:
    E10: true
    E5: false
    B7: true
    SDV: false
  count:
    cheapest: 3
    nearest: 2
  ignore_stale_data_days: 1
  update_interval: 3600
```

**Free text address:**

```yaml
fuel_prices_uk:
  client_id: !secret fuel_uk_client_id
  client_secret: !secret fuel_uk_client_secret
  location:
    address: "10 Downing Street, London"
  radius:
    type: miles
    value: 3.0
```

**Explicit coordinates:**

```yaml
fuel_prices_uk:
  client_id: !secret fuel_uk_client_id
  client_secret: !secret fuel_uk_client_secret
  location:
    lat: 51.5033
    long: -0.1276
  radius:
    type: km
    value: 8.0
```

**Multiple locations (list syntax):**

```yaml
fuel_prices_uk:
  - name: Home
    client_id: !secret fuel_uk_client_id
    client_secret: !secret fuel_uk_client_secret
    location:
      postcode: "SW1A 1AA"
    radius:
      type: miles
      value: 5.0

  - name: Work
    client_id: !secret fuel_uk_client_id
    client_secret: !secret fuel_uk_client_secret
    location:
      postcode: "EC1A 1BB"
    radius:
      type: miles
      value: 3.0
    fuel_types:
      E10: true
      B7: true
    count:
      cheapest: 1
      nearest: 0
```

Each list item creates its own config entry and its own set of sensors. The `name` field becomes the entry title in **Settings → Devices & Services**.

---

## Sensors

The integration creates ranked sensors for each fuel type you've selected.

### Cheapest Price Sensors

The integration creates ranked sensors per selected fuel type based on your **Number of Cheapest Options** setting.

- Rank 1 keeps the existing entity naming style and represents the cheapest station.
- Higher ranks expose next-best alternatives (for example 2nd and 3rd cheapest).

**Rank 1 Sensor Name:** `sensor.fuel_price_uk_[location]_[distance]_cheapest_[fuel_type]`

**Higher Rank Sensor Name:** `sensor.fuel_price_uk_[location]_[distance]_rank_[n]_cheapest_[fuel_type]`

Example: `sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e10`

**State:** Current price for that rank in £/L to 3 decimal places (e.g. £1.379)

**Attributes:**
- `fuel_type`: The type of fuel (E10, E5, B7, SDV)
- `price_rank`: Rank position (1 = cheapest, 2 = second cheapest, etc.)
- `price_rank_label`: Human-readable rank label (for example `1st`, `2nd`, `3rd`)
- `address`: Full address of the station
- `postcode`: Postcode of the station
- `brand`: Retailer brand (e.g., "Tesco", "Shell")
- `latitude`: Station latitude
- `longitude`: Station longitude
- `distance`: Distance from your location (km)
- `last_updated`: When the price was last updated
- `unit_of_measurement`: GBP
- `device_class`: monetary
- `icon`: mdi:gas-station

## Example Lovelace Card

<img width="400" src="https://raw.githubusercontent.com/beecho01/Fuel-Prices-UK/refs/heads/main/images/entities_card_example.png">

```yaml
type: entities
title: Cheapest Fuel Prices Near Me
entities:
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e10
    name: Unleaded (E10)
    secondary_info: last-updated
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_b7
    name: Diesel (B7)
    secondary_info: last-updated
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e5
    name: Super Unleaded (E5)
    secondary_info: last-updated
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_sdv
    name: Super Diesel (SDV)
    secondary_info: last-updated
```

The standard Home Assistant `entities` card does not evaluate Jinja templates in `secondary_info`.
If you want `brand` + `address` rendered inline, use a custom row card such as `custom:template-entity-row` from HACS.

### Example Ranked Card (1st, 2nd, 3rd)

Use this if you enabled **Number of Cheapest Options** as 3 or higher.

```yaml
type: entities
title: E10 Cheapest Alternatives
entities:
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e10
    name: E10 1st Cheapest
    secondary_info: last-updated
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_rank_2_cheapest_e10
    name: E10 2nd Cheapest
    secondary_info: last-updated
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_rank_3_cheapest_e10
    name: E10 3rd Cheapest
    secondary_info: last-updated
```

You can repeat the same pattern for other fuel types (`b7`, `e5`, `sdv`) by changing the entity suffix.

### Example Map Card
Show fuel stations on a map:

<img width="400" src="https://raw.githubusercontent.com/beecho01/Fuel-Prices-UK/refs/heads/main/images/map_card_example.png">

```yaml
type: map
entities:
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e10
    label_mode: attribute
    attribute: fuel_type
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_b7
    label_mode: attribute
    attribute: fuel_type
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e5
    label_mode: attribute
    attribute: fuel_type
  - entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_sdv
    label_mode: attribute
    attribute: fuel_type
auto_fit: true
```

### Example Grid Card

<img width="400" src="https://raw.githubusercontent.com/beecho01/Fuel-Prices-UK/refs/heads/main/images/grid_sensor_example.png">

```yaml
type: grid
square: false
columns: 2
cards:
  - type: sensor
    entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e10
    name: E10
    icon: mdi:gas-station
  - type: sensor
    entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_b7
    name: Diesel
    icon: mdi:gas-station
  - type: sensor
    entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_e5
    name: E5
    icon: mdi:gas-station
  - type: sensor
    entity: sensor.fuel_price_uk_sw1a_2aa_3_mi_cheapest_sdv
    name: SDV
    icon: mdi:gas-station
```

## How It Works

This integration ships with a lightweight async client in `custom_components/fuel_prices_uk/api_client.py` that:

1. Exchanges your `client_id` and `client_secret` for a short-lived OAuth token
2. Fetches station metadata (`/api/v1/pfs`) and fuel prices (`/api/v1/pfs/fuel-prices`) in API batches
3. Normalises fuel types from the new API (for example `B7_STANDARD` → `B7`)
4. Filters stations within your configured radius and exposes the cheapest values per fuel type

## Data Update Frequency

- Minimum update interval: 5 minutes (300 seconds)
- Maximum update interval: 24 hours (86400 seconds)
- Recommended: 1 hour (3600 seconds) - this balances fresh data with API usage

Note: Most retailers update their prices once per day, typically overnight.

## Troubleshooting

### No Data / Sensors Unavailable

- Check that you have an internet connection
- Verify your location and radius settings
- Some areas may have limited station coverage
- Try increasing the search radius

### Prices Seem Outdated

- Check the `last_updated` attribute on the sensor
- Retailers update at different times - some may be slower than others
- Try reducing the update interval for more frequent checks

### Integration Won't Load

- Check your Home Assistant logs for errors
- Verify your Fuel Finder API credentials are valid
- Ensure you have Python 3.9 or higher
- Try reinstalling the integration
- Restart Home Assistant

### Setup Completes But Sensors Stay Unavailable Briefly

During setup, the integration now creates entities first and performs the initial API sync in the background.
If the Fuel Finder API is slow, sensors can remain unavailable for a short period before prices appear.

- Wait a few minutes and then refresh entity states
- Check logs for `[coordinator][startup_refresh]` messages
- If the first sync fails, the scheduled refresh cycle will retry automatically

## Development & Verification

- Run `python scripts/check_api_client.py --client-id YOUR_ID --client-secret YOUR_SECRET` to perform a quick end-to-end check against the Fuel Finder API.
- You can also set `FUEL_FINDER_CLIENT_ID` and `FUEL_FINDER_CLIENT_SECRET` environment variables and run the same script without flags.

## Known Limitations

- Data quality depends on retailer participation in the government scheme
- Not all fuel stations are included (only those participating in the transparency scheme)
- Prices may be up to 24 hours old depending on when retailers update their data
- Some retailers may not provide all fuel types

## Support

For issues, feature requests, or questions:
- [Open an issue on GitHub](https://github.com/beecho01/Fuel-Prices-UK/issues)
- Check existing issues to see if your question has been answered

## Data Sources

This integration uses official data provided by the UK Government Fuel Finder service:
- [Fuel Finder Public API](https://www.developer.fuel-finder.service.gov.uk/public-api)
- [Fuel Finder API Authentication](https://www.developer.fuel-finder.service.gov.uk/api-authentication)
- [Fuel Finder Information Recipient OpenAPI](https://www.developer.fuel-finder.service.gov.uk/apis-ifr/info-recipent)

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with or endorsed by the UK Government. Price data is provided as-is from official government feeds, but accuracy cannot be guaranteed. Always verify prices at the pump before filling up.

---

Made with ❤️ for the Home Assistant community
