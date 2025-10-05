# EVCC Dynamic Tariff Integration

This document describes how batcontrol integrates with the evcc API to fetch dynamic electricity pricing data.

## Overview

batcontrol can use evcc as a dynamic tariff provider to obtain electricity prices for optimizing battery charging and discharging schedules. The evcc API provides price data that can be updated at various intervals (e.g., hourly or sub-hourly).

## Configuration

To use evcc as your dynamic tariff provider, configure it in your `batcontrol_config.yaml`:

```yaml
dynamictariff:
  provider: "evcc"
  url: "http://your-evcc-server:7070/api/tariff/planner"
```

## Price Data Processing

### Hourly Price Averaging

**Important:** As of the current version, when evcc delivers multiple price entries for the same hour (e.g., every 15 minutes), batcontrol calculates the hourly price as the **average of all prices** provided for that hour.

This averaging behavior ensures that:
- Sub-hourly price variations are smoothed into a single hourly price
- The battery control logic works with consistent hourly pricing data
- Price fluctuations within an hour are fairly represented

### Example

If evcc provides the following 15-minute interval prices for a single hour:
- 10:00 - 10:15: 0.20 €/kWh
- 10:15 - 10:30: 0.24 €/kWh
- 10:30 - 10:45: 0.28 €/kWh
- 10:45 - 11:00: 0.32 €/kWh

Batcontrol will calculate the hourly price for 10:00-11:00 as:
```
Average = (0.20 + 0.24 + 0.28 + 0.32) / 4 = 0.26 €/kWh
```

### Compatibility

This implementation maintains compatibility with:
- **evcc 0.203.0 and later**: Uses the `value` field for price data
- **Earlier versions**: Falls back to the `price` field
- **API structure changes**: Supports both the newer direct `rates` field and the legacy `result.rates` structure (pre-0.207.0)

## API Endpoint

The evcc price endpoint typically provides data at:
```
http://<evcc-host>:<port>/api/tariff/planner
```

The API returns price information with timestamps indicating when each price period begins.

## Technical Details

- Prices are indexed by relative hour from the current time
- Only future prices (relative hour ≥ 0) are processed
- The timezone specified in your configuration is used for all time calculations
- Multiple price entries falling within the same hour boundary are averaged together

## Related Updates

The hourly averaging functionality was implemented to better handle sub-hourly price data from evcc and provide more accurate optimization of battery charging schedules.
