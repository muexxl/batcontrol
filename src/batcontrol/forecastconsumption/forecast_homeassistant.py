"""HomeAssistant API based consumption forecasting

This module provides consumption forecasting using historical data from HomeAssistant.
It fetches historical consumption data for configured time periods (e.g., -7, -14, -21 days)
and calculates weighted statistics for each hour to predict future consumption.
"""

import datetime
import logging
import threading
import numpy as np
import requests
from typing import Dict, List, Tuple, Optional
from cachetools import TTLCache
from .forecastconsumption_interface import ForecastConsumptionInterface

logger = logging.getLogger(__name__)
logger.info('Loading module')


class ForecastConsumptionHomeAssistant(ForecastConsumptionInterface):
    """Forecasts consumption based on historical data from HomeAssistant API

    This class fetches historical consumption data from HomeAssistant for specified
    time periods (e.g., last 7, 14, 21 days) and calculates weighted averages
    for each hour of the week to predict future consumption.

    Attributes:
        base_url: HomeAssistant base URL
        api_token: HomeAssistant API access token
        entity_id: Entity ID to fetch consumption data for
        history_days: List of days to look back (e.g., [-7, -14, -21])
        history_weights: Weights for each history period (e.g., [1, 1, 1])
        timezone: Timezone for data processing
        consumption_cache: TTLCache storing consumption values by weekday_hour key
        cache_ttl_hours: TTL for cached data in hours
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        entity_id: str,
        timezone,
        history_days: Optional[List[int]] = None,
        history_weights: Optional[List[int]] = None,
        cache_ttl_hours: float = 48.0,
        multiplier: float = 1.0
    ) -> None:
        """Initialize HomeAssistant consumption forecaster

        Args:
            base_url: HomeAssistant base URL (e.g., "http://192.168.1.100:8123")
            api_token: HomeAssistant Long-Lived Access Token
            entity_id: Entity ID to fetch data for (e.g., "sensor.energy_consumption")
            timezone: Timezone object for data processing
            history_days: List of negative day offsets to fetch (e.g., [-7, -14, -21])
            history_weights: Weight for each history period (1-10), same length as history_days
            cache_ttl_hours: Time-to-live for cached statistics in hours (default: 48)
            multiplier: Multiplier applied to all forecast values (default: 1.0)
                       Use >1.0 to increase forecast, <1.0 to decrease
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.entity_id = entity_id
        self.timezone = timezone

        # Default to last 7, 14, 21 days with equal weights
        self.history_days = history_days if history_days else [-7, -14, -21]
        self.history_weights = history_weights if history_weights else [1, 1, 1]
        self.multiplier = multiplier

        # Validate configuration
        if len(self.history_days) != len(self.history_weights):
            raise ValueError(
                f"Length of history_days ({len(self.history_days)}) must match "
                f"history_weights ({len(self.history_weights)})"
            )

        for weight in self.history_weights:
            if not 1 <= weight <= 10:
                raise ValueError(f"History weights must be between 1 and 10, got {weight}")

        # Initialize cache with TTL
        # Cache key format: "weekday_hour" (e.g., "0_14" for Monday 14:00)
        # Cache stores consumption value in Wh for each hour slot
        # maxsize: 168 = 7 days * 24 hours (one week of hourly data)
        self.cache_ttl_hours = cache_ttl_hours
        cache_ttl_seconds = int(cache_ttl_hours * 3600)
        self.consumption_cache: TTLCache = TTLCache(maxsize=168, ttl=cache_ttl_seconds)
        self._cache_lock = threading.Lock()

        logger.info(
            "Initialized HomeAssistant consumption forecaster: "
            "entity_id=%s, history_days=%s, weights=%s, cache_ttl=%0.1fh, multiplier=%0.2f",
            entity_id, self.history_days, self.history_weights, cache_ttl_hours, multiplier
        )

    def _get_cache_key(self, weekday: int, hour: int) -> str:
        """Generate cache key from weekday and hour

        Args:
            weekday: Day of week (0=Monday, 6=Sunday)
            hour: Hour of day (0-23)

        Returns:
            Cache key in format "weekday_hour" (e.g., "0_14" for Monday 14:00)
        """
        return f"{weekday}_{hour}"

    def _fetch_hourly_statistics(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime
    ) -> Dict[Tuple[int, int], float]:
        """Fetch hourly statistics from HomeAssistant API

        Uses the statistics API to get pre-aggregated hourly consumption data.
        This is much more efficient than fetching raw history and processing manually.

        Args:
            start_time: Start of time range (will be aligned to hour boundary)
            end_time: End of time range (will be aligned to hour boundary)

        Returns:
            Dict mapping (weekday, hour) to consumption in Wh

        Raises:
            RuntimeError: If API request fails
        """
        # Align to hour boundaries for statistics API
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
        end_time = end_time.replace(minute=0, second=0, microsecond=0)

        # Format timestamps for HomeAssistant API (ISO format)
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()

        # Build API URL for statistics endpoint
        url = f"{self.base_url}/api/history/statistics/during_period/{start_iso}"
        params = {
            'statistic_ids': self.entity_id,
            'end': end_iso,
            'period': 'hour'  # Get hourly aggregated data
        }

        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }

        logger.debug(
            "Fetching hourly statistics: entity=%s, start=%s, end=%s",
            self.entity_id, start_iso, end_iso
        )

        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            # HomeAssistant statistics API returns dict with entity_id as key
            if not data or self.entity_id not in data:
                logger.warning(
                    "No statistics data returned for entity %s. "
                    "Make sure the entity has long-term statistics enabled.",
                    self.entity_id
                )
                return {}

            entity_stats = data[self.entity_id]
            logger.debug("Fetched %d hourly statistics", len(entity_stats))

            # Process statistics into hourly buckets by weekday and hour
            hourly_data: Dict[Tuple[int, int], float] = {}

            for stat in entity_stats:
                # Parse start timestamp
                start_ts_str = stat.get('start')
                if not start_ts_str:
                    continue

                # Convert timestamp (milliseconds) to datetime
                start_ts = datetime.datetime.fromtimestamp(
                    start_ts_str / 1000.0,
                    tz=self.timezone
                )

                weekday = start_ts.weekday()
                hour = start_ts.hour

                # Get consumption value - use 'sum' for cumulative sensors
                # 'sum' represents the total change during this hour
                consumption = stat.get('sum') or stat.get('state')

                if consumption is not None:
                    try:
                        consumption = float(consumption)
                        if consumption < 0:
                            logger.debug(
                                "Skipping negative consumption at %s: %.2f Wh",
                                start_ts, consumption
                            )
                            continue

                        key = (weekday, hour)
                        hourly_data[key] = consumption

                        logger.debug(
                            "Hour %s (%s): %.2f Wh",
                            key, start_ts.strftime("%Y-%m-%d %H:%M"), consumption
                        )
                    except (ValueError, TypeError):
                        logger.debug("Skipping non-numeric consumption: %s", consumption)
                        continue

            logger.debug("Processed %d hourly statistics buckets", len(hourly_data))
            return hourly_data

        except requests.exceptions.RequestException as e:
            logger.error("Failed to fetch statistics from HomeAssistant: %s", e)
            raise RuntimeError(f"HomeAssistant API request failed: {e}") from e

    def _update_cache_with_statistics(
        self,
        history_periods: List[Dict[Tuple[int, int], float]]
    ) -> int:
        """Calculate weighted statistics and update cache

        Args:
            history_periods: List of hourly data dicts from different time periods
                           Each dict maps (weekday, hour) -> consumption in Wh

        Returns:
            Number of cache entries updated
        """
        # Collect all unique (weekday, hour) combinations
        all_keys = set()
        for period_data in history_periods:
            all_keys.update(period_data.keys())

        updated_count = 0

        # Calculate weighted average for each hour and store in cache
        with self._cache_lock:
            for weekday, hour in all_keys:
                weighted_sum = 0.0
                total_weight = 0

                for period_data, weight in zip(history_periods, self.history_weights):
                    if (weekday, hour) in period_data:
                        consumption = period_data[(weekday, hour)]
                        weighted_sum += consumption * weight
                        total_weight += weight

                if total_weight > 0:
                    avg_consumption = weighted_sum / total_weight
                    # Apply multiplier to adjust forecast up or down
                    avg_consumption *= self.multiplier
                    cache_key = self._get_cache_key(weekday, hour)
                    self.consumption_cache[cache_key] = avg_consumption
                    updated_count += 1

        logger.debug("Updated %d cache entries", updated_count)
        return updated_count

    def refresh_data(self) -> None:
        """Refresh historical data and update cache

        Fetches hourly statistics from HomeAssistant for configured time periods,
        calculates weighted averages, and updates the cache.
        """
        logger.info("Refreshing consumption forecast data from HomeAssistant")

        now = datetime.datetime.now(tz=self.timezone)
        history_periods = []

        # Fetch data for each configured history period
        for days_offset in self.history_days:
            # Calculate time range for this period (24 hours)
            end_time = now + datetime.timedelta(days=days_offset)
            start_time = end_time - datetime.timedelta(hours=24)

            try:
                hourly_data = self._fetch_hourly_statistics(start_time, end_time)
                if hourly_data:
                    history_periods.append(hourly_data)
                else:
                    logger.warning(
                        "No statistics data for %d days offset",
                        days_offset
                    )
            except (RuntimeError, ValueError) as e:
                logger.error(
                    "Failed to fetch statistics for %d days offset: %s",
                    days_offset, e
                )
                # Continue with other periods even if one fails
                continue

        if not history_periods:
            logger.error("No statistics data could be fetched, forecast unavailable")
            return

        # Calculate weighted statistics and update cache
        updated_count = self._update_cache_with_statistics(history_periods)

        logger.info(
            "Successfully updated consumption forecast cache with %d hour slots",
            updated_count
        )

    def get_forecast(self, hours: int) -> Dict[int, float]:
        """Get consumption forecast for the next N hours

        Args:
            hours: Number of hours to forecast (typically up to 48)

        Returns:
            Dict mapping hour offset to predicted consumption in Wh
        """
        # Check if cache is empty, if so refresh data
        with self._cache_lock:
            cache_size = len(self.consumption_cache)

        if cache_size == 0:
            logger.info("Cache empty, refreshing consumption forecast data")
            self.refresh_data()

        # Generate forecast for requested hours
        prediction = {}
        now = datetime.datetime.now(tz=self.timezone)
        missing_keys = []

        for h in range(hours):
            future_time = now + datetime.timedelta(hours=h)
            weekday = future_time.weekday()
            hour = future_time.hour
            cache_key = self._get_cache_key(weekday, hour)

            # Get consumption from cache
            with self._cache_lock:
                consumption = self.consumption_cache.get(cache_key)

            if consumption is not None:
                prediction[h] = consumption
            else:
                # Cache miss - collect for later
                missing_keys.append((h, weekday, hour, cache_key))

        # Handle missing keys: use average of available values as fallback
        if missing_keys:
            with self._cache_lock:
                if len(self.consumption_cache) > 0:
                    # Average is already multiplied in cache, no need to apply multiplier again
                    avg_consumption = float(np.mean(list(self.consumption_cache.values())))
                else:
                    avg_consumption = 0.0
                    logger.warning("No cached data available for forecast")

            for h, weekday, hour, cache_key in missing_keys:
                prediction[h] = avg_consumption
                logger.debug(
                    "No data for %s (weekday=%d, hour=%d), using average: %.1f Wh",
                    cache_key, weekday, hour, avg_consumption
                )

        if prediction:
            logger.debug(
                "Generated %d hour forecast: avg=%.1f Wh, min=%.1f Wh, max=%.1f Wh",
                hours,
                np.mean(list(prediction.values())),
                min(prediction.values()),
                max(prediction.values())
            )
        else:
            logger.warning("Generated empty forecast")

        return prediction
