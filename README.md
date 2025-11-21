# 🇬🇧 Fuel Prices UK - Home Assistant Integration

A Home Assistant custom integration that monitors fuel prices at UK petrol stations using official government data feeds. Find the cheapest fuel near you!

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

## Features

- ✅ **Official UK Government Data** - Uses data from the UK Government's fuel price transparency scheme
- ✅ **Real-time Price Monitoring** - Track E10, E5, B7 (Diesel), and SDV (Super Diesel) prices
- ✅ **Location-Based Search** - Find stations within a specified radius of your home or any location
- ✅ **Automatic Updates** - Configurable update intervals from 5 minutes to 24 hours
- ✅ **Easy Setup** - Simple configuration flow with map-based location selection
- ✅ **Cheapest Price Sensors** - Automatically shows the cheapest price for each fuel type

## Supported Fuel Types

- **E10** - Standard unleaded petrol (10% ethanol)
- **E5** - Super unleaded petrol (5% ethanol)
- **B7** - Standard diesel (7% biodiesel)
- **SDV** - Super diesel / Premium diesel

## Supported Retailers

We query every retailer feed currently listed on the UK Government's [fuel price transparency scheme](https://www.gov.uk/guidance/access-fuel-price-data) (last checked 15 July 2025):

- Ascona Group
- Asda
- bp
- Esso Tesco Alliance
- JET Retail UK
- Karan Retail Ltd
- Morrisons
- Moto
- Motor Fuel Group
- Rontec
- Sainsbury's
- SGN
- Shell
- Tesco

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

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Fuel Prices UK"
4. Follow the configuration wizard:
   - **Update Interval**: How often to fetch prices (in seconds, minimum 300 = 5 minutes)
   - **Location**: Select your location on the map (defaults to your Home Assistant location)
   - **Search Radius**: Distance in km to search for fuel stations (1-50 km)
   - **Fuel Types**: Select which fuel types you want to monitor

### Configuration Options

After setup, you can update these settings by clicking **Configure** on the integration:

- Update interval
- Search radius
- Fuel types to monitor

Note: To change the location, you'll need to remove and re-add the integration.

## Sensors

The integration creates one sensor for each fuel type you've selected:

### Cheapest Price Sensors

**Sensor Name:** `sensor.cheapest_[fuel_type]_price`

Example: `sensor.cheapest_e10_price`

**State:** Current cheapest price in £/L

**Attributes:**
- `fuel_type`: The type of fuel (E10, E5, B7, SDV)
- `station_name`: Name of the station with the cheapest price
- `address`: Full address of the station
- `postcode`: Postcode of the station
- `brand`: Retailer brand (e.g., "Tesco", "Shell")
- `latitude`: Station latitude
- `longitude`: Station longitude
- `distance`: Distance from your location (km)
- `last_updated`: When the price was last updated

## Example Lovelace Card

```yaml
type: entities
title: Cheapest Fuel Prices Near Me
entities:
  - entity: sensor.cheapest_e10_price
    name: Unleaded (E10)
    secondary_info: attribute
    attribute: station_name
  - entity: sensor.cheapest_b7_price
    name: Diesel (B7)
    secondary_info: attribute
    attribute: station_name
  - entity: sensor.cheapest_e5_price
    name: Super Unleaded (E5)
    secondary_info: attribute
    attribute: station_name
```

### Map Card

Show fuel stations on a map:

```yaml
type: map
entities:
  - entity: sensor.cheapest_e10_price
  - entity: sensor.cheapest_b7_price
  - entity: sensor.cheapest_e5_price
default_zoom: 12
```

### Price Comparison Card

```yaml
type: horizontal-stack
cards:
  - type: statistic
    entity: sensor.cheapest_e10_price
    name: E10
    icon: mdi:gas-station
  - type: statistic
    entity: sensor.cheapest_b7_price
    name: Diesel
    icon: mdi:gas-station
  - type: statistic
    entity: sensor.cheapest_e5_price
    name: E5
    icon: mdi:gas-station
```

## How It Works

This integration ships with a lightweight async client (see `custom_components/fuel_prices_uk/api_client.py`) that talks directly to the official Home Office endpoints without external dependencies.

As mandated by the UK Government, major fuel retailers publish their prices in an open data format, making this information freely available. The integration:

1. Downloads price data from each participating retailer feed
2. Filters stations within your specified radius (or by Site ID)
3. Sorts by price for each selected fuel type
4. Creates sensors showing the cheapest options

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
- Ensure you have Python 3.9 or higher
- Try reinstalling the integration
- Restart Home Assistant

## Development & Verification

- Run `python scripts/check_api_client.py` to perform a quick end-to-end test of the bundled API client. The script prints how many stations were retrieved plus a sample entry so you can confirm the government data feeds are reachable from your environment.
- The lightweight client that ships with this integration (see `custom_components/fuel_prices_uk/api_client.py`) talks directly to the official UK Government endpoints and keeps attribution to the upstream [`uk-fuel-prices-api`](https://github.com/gaco79/uk_fuel_prices_api) project (LGPL-3.0).

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

This integration uses official data provided under the UK Government's fuel price transparency scheme:
- [UK Government Fuel Price Data](https://www.gov.uk/guidance/access-fuel-price-data)
- [uk-fuel-prices-api PyPI Package](https://pypi.org/project/uk-fuel-prices-api/)

Additional credit: portions of the in-repo API client were inspired by the open-source [`uk-fuel-prices-api`](https://github.com/gaco79/uk_fuel_prices_api) project (LGPL-3.0).

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with or endorsed by the UK Government. Price data is provided as-is from official government feeds, but accuracy cannot be guaranteed. Always verify prices at the pump before filling up.

---

Made with ❤️ for the Home Assistant community

[releases-shield]: https://img.shields.io/github/release/beecho01/Fuel-Prices-UK.svg
[releases]: https://github.com/beecho01/Fuel-Prices-UK/releases
[license-shield]: https://img.shields.io/github/license/beecho01/Fuel-Prices-UK.svg
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
