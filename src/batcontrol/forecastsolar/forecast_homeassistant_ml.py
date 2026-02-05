"""HomeAssistant Solar Forecast ML integration

This module provides solar forecasting using ML-based forecast data from
HomeAssistant Solar Forecast ML integration (HACS).

Based on HACS integration: https://zara-toorox.github.io/
Sensor: sensor.solar_forecast_ml_prognose_nachste_stunde

"""

import asyncio
import json
import logging
import threading
from typing import Dict, Optional

from cachetools import TTLCache
from websockets.asyncio.client import connect
from .baseclass import ForecastSolarBaseclass

logger = logging.getLogger(__name__)
logger.info('Loading module')

logger_ha_details = logging.getLogger(
    "batcontrol.forecastsolar.forecast_homeassistant_ml.details")
logger_ha_communication = logging.getLogger(
    "batcontrol.forecastsolar.forecast_homeassistant_ml.communication")


# pylint: disable=too-many-instance-attributes
class ForecastSolarHomeAssistantML(ForecastSolarBaseclass):
    """Provides solar forecast from HomeAssistant Solar Forecast ML integration

    This class fetches solar forecast data from HomeAssistant Solar Forecast ML
    integration sensor (typically sensor.solar_forecast_ml_prognose_nachste_stunde).
    The sensor provides hourly ML-based predictions in its attributes.

    Attributes:
        base_url: HomeAssistant base URL
        api_token: HomeAssistant API access token
        entity_id: Entity ID of the sensor providing forecast
        timezone: Timezone for data processing
        sensor_unit: Unit of the sensor ('wh', 'kwh', or 'auto')
        unit_conversion_factor: Factor to convert sensor values to Wh
        forecast_cache: TTLCache storing hourly forecast values
        cache_ttl_hours: TTL for cached forecast data
    """

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        pvinstallations: list,
        timezone,
        base_url: str,
        api_token: str,
        entity_id: str,
        min_time_between_api_calls: int = 21600,
        delay_evaluation_by_seconds: int = 300,
        cache_ttl_hours: float = 24.0,
        sensor_unit: Optional[str] = "auto",
        target_resolution: int = 60
    ) -> None:
        """Initialize HomeAssistant solar forecast provider

        Args:
            pvinstallations: List of PV installation dicts (for compatibility with baseclass)
                Each dict should contain 'name' key for logging
            timezone: Timezone object for data processing
            base_url: HomeAssistant base URL (e.g., "http://192.168.1.100:8123")
            api_token: HomeAssistant Long-Lived Access Token
            entity_id: Entity ID of forecast sensor (e.g., "sensor.solar_forecast_ml_...")
            min_time_between_api_calls: Minimum seconds between API calls (default: 6 hours)
            delay_evaluation_by_seconds: Delay before first evaluation (default: 5 min)
            cache_ttl_hours: Time-to-live for cached forecast in hours (default: 24)
            sensor_unit: Optional sensor unit ('auto', 'Wh', or 'kWh').
                        If set to 'Wh' or 'kWh', skips auto-detection.
                        If set to 'auto', queries Home Assistant to detect unit.
                        Default: auto (auto-detect)
            target_resolution: Target resolution in minutes (15 or 60)
        """
        # Initialize baseclass with native 60-minute resolution
        super().__init__(
            pvinstallations,
            timezone,
            min_time_between_api_calls,
            delay_evaluation_by_seconds,
            target_resolution=target_resolution,
            native_resolution=60
        )

        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.entity_id = entity_id

        # Validate sensor_unit parameter
        if sensor_unit is not None:
            sensor_unit_lower = sensor_unit.lower()
            if sensor_unit_lower not in ['auto', 'wh', 'kwh']:
                raise ValueError(
                    f"Invalid sensor_unit '{sensor_unit}'. "
                    f"Allowed values: 'auto', 'Wh', 'kWh'"
                )
            self.sensor_unit = sensor_unit_lower
        else:
            raise ValueError(
                f"Invalid sensor_unit '{sensor_unit}'. "
                f"Allowed values: 'auto', 'Wh', 'kWh'"
            )

        # Initialize cache with TTL
        # Cache key format: "hour_N" (e.g., "hour_0", "hour_1")
        # Cache stores forecast value in Wh for each hour
        # maxsize: 96 = 4 days * 24 hours (supports up to 96-hour forecast)
        self.cache_ttl_hours = cache_ttl_hours
        cache_ttl_seconds = int(cache_ttl_hours * 3600)
        self.forecast_cache: TTLCache = TTLCache(
            maxsize=96, ttl=cache_ttl_seconds)
        self._cache_lock = threading.Lock()

        # Query sensor to determine unit and set conversion factor
        if self.sensor_unit and self.sensor_unit != 'auto':
            # User explicitly configured the unit, skip discovery
            if self.sensor_unit == 'wh':
                self.unit_conversion_factor = 1.0
                logger.info(
                    "Using configured sensor unit: Wh (conversion factor: 1.0)"
                )
            elif self.sensor_unit == 'kwh':
                self.unit_conversion_factor = 1000.0
                logger.info(
                    "Using configured sensor unit: kWh (conversion factor: 1000.0)"
                )
        else:
            # Auto-detect unit from Home Assistant
            logger.info("Auto-detecting sensor unit from Home Assistant...")
            self.unit_conversion_factor = self._check_sensor_unit()

        logger.info(
            "Initialized HomeAssistant Solar Forecast ML provider: "
            "entity_id=%s, cache_ttl=%0.1fh, sensor_unit=%s, "
            "unit_conversion_factor=%0.1f",
            entity_id, cache_ttl_hours, self.sensor_unit or 'auto',
            self.unit_conversion_factor
        )

    def _check_sensor_unit(self) -> float:
        """Check sensor's unit_of_measurement and return conversion factor

        Queries the sensor via WebSocket to get its unit_of_measurement attribute.
        Returns the appropriate conversion factor to convert to Wh.

        Returns:
            float: Conversion factor (1.0 for Wh, 1000.0 for kWh)

        Raises:
            ValueError: If unit_of_measurement is neither Wh nor kWh
            RuntimeError: If sensor cannot be queried
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._check_sensor_unit_async())

    async def _check_sensor_unit_async(self) -> float:
        """Async implementation of sensor unit check

        Returns:
            float: Conversion factor (1.0 for Wh, 1000.0 for kWh)

        Raises:
            ValueError: If unit_of_measurement is neither Wh nor kWh
            RuntimeError: If sensor cannot be queried
        """
        logger.debug(
            "Checking unit_of_measurement for entity: %s",
            self.entity_id)

        websocket, message_id = await self._websocket_connect()

        try:
            # Request all states to find our entity
            states_request = {
                "id": message_id,
                "type": "get_states"
            }
            logger_ha_communication.debug(
                "Sending get_states request: %s", states_request)
            await websocket.send(json.dumps(states_request))

            # Receive states response
            states_response = await websocket.recv()
            states_result = json.loads(states_response)
            logger_ha_communication.debug(
                "Received states response: id=%s, type=%s, success=%s",
                states_result.get("id"),
                states_result.get("type"),
                states_result.get("success"))

            if not states_result.get("success"):
                error_msg = states_result.get(
                    "error", {}).get(
                    "message", "Unknown error")
                logger.error("get_states request failed: %s", error_msg)
                raise RuntimeError(f"Failed to get sensor states: {error_msg}")

            # Find our entity in the results
            states = states_result.get("result", [])
            entity_state = None
            for state in states:
                if state.get("entity_id") == self.entity_id:
                    entity_state = state
                    break

            if entity_state is None:
                raise RuntimeError(
                    f"Entity '{self.entity_id}' not found in HomeAssistant. "
                    f"Please check the entity_id."
                )

            # Get unit_of_measurement from attributes
            attributes = entity_state.get("attributes", {})
            unit = attributes.get("unit_of_measurement")

            logger.info(
                "Entity '%s' has unit_of_measurement: %s",
                self.entity_id, unit
            )

            # Determine conversion factor based on unit
            if unit == "Wh":
                logger.debug("Unit is Wh, no conversion needed")
                return 1.0

            if unit == "kWh":
                logger.info(
                    "Unit is kWh, will multiply values by 1000 to convert to Wh")
                return 1000.0

            raise ValueError(
                f"Unsupported unit_of_measurement '{unit}' for entity "
                f"'{self.entity_id}'. Only 'Wh' and 'kWh' are supported.")

        finally:
            await self._websocket_disconnect(websocket)

    async def _websocket_connect(self):
        """Connect to HomeAssistant WebSocket API and authenticate

        Returns:
            Tuple of (websocket connection, message_id counter)

        Raises:
            RuntimeError: If connection or authentication fails
        """
        # Build WebSocket URL
        ws_url = self.base_url.replace(
            'http://', 'ws://').replace('https://', 'wss://')
        ws_url = f"{ws_url}/api/websocket"

        logger_ha_communication.debug(
            "Connecting to HomeAssistant WebSocket: %s", ws_url)

        # Set max_size to 4MB to handle large Home Assistant instances
        websocket = await connect(ws_url, max_size=4 * 1024 * 1024)

        # Step 1: Receive auth_required message
        auth_required = await websocket.recv()
        auth_msg = json.loads(auth_required)
        logger_ha_communication.debug(
            "Received auth_required message: %s", auth_msg)

        if auth_msg.get("type") != "auth_required":
            await websocket.close()
            raise RuntimeError(f"Unexpected message: {auth_msg}")

        # Step 2: Send authentication
        auth_payload = {
            "type": "auth",
            "access_token": self.api_token
        }
        logger_ha_communication.debug("Sending authentication message")
        await websocket.send(json.dumps(auth_payload))

        # Step 3: Receive auth response
        auth_response = await websocket.recv()
        auth_result = json.loads(auth_response)
        logger_ha_communication.debug(
            "Received auth response: %s", auth_result)

        if auth_result.get("type") != "auth_ok":
            logger.error(
                "WebSocket authentication failed: %s", auth_result
            )
            await websocket.close()
            raise RuntimeError(
                f"Authentication failed: "
                f"{auth_result.get('message', 'Unknown error')}"
            )

        logger_ha_communication.debug("WebSocket authentication successful")

        return websocket, 1  # Return websocket and initial message_id

    async def _websocket_disconnect(self, websocket):
        """Disconnect from HomeAssistant WebSocket API

        Args:
            websocket: WebSocket connection to close
        """
        try:
            await websocket.close()
            logger_ha_communication.debug("WebSocket connection closed")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger_ha_communication.warning(
                "Error closing WebSocket connection: %s", e)

    async def _fetch_forecast_async(
        self,
        websocket=None
    ) -> Dict[int, float]:
        """Fetch solar forecast from HomeAssistant sensor via WebSocket

        Args:
            websocket: Optional existing websocket connection to reuse

        Returns:
            Dict mapping hour index to solar generation in Wh
            (e.g., {0: 879.0, 1: 1265.0, 2: 1688.0, ...})

        Raises:
            RuntimeError: If WebSocket connection or API request fails
        """
        # Track if we need to manage the websocket connection
        should_disconnect = False

        try:
            if websocket is None:
                websocket, message_id = await self._websocket_connect()
                should_disconnect = True
            else:
                message_id = 1

            try:
                # Request all states to find our entity
                states_request = {
                    "id": message_id,
                    "type": "get_states"
                }
                logger_ha_details.debug(
                    "Sending get_states request for entity: %s", self.entity_id)
                await websocket.send(json.dumps(states_request))

                # Receive states response
                states_response = await websocket.recv()
                states_result = json.loads(states_response)
                logger_ha_details.debug(
                    "Received states response: id=%s, type=%s, success=%s",
                    states_result.get("id"),
                    states_result.get("type"),
                    states_result.get("success"))

                if not states_result.get("success"):
                    error_msg = states_result.get(
                        "error", {}
                    ).get("message", "Unknown error")
                    logger.error("Get states request failed: %s", error_msg)
                    raise RuntimeError(
                        f"Get states request failed: {error_msg}"
                    )

                # Find our entity in the results
                states = states_result.get("result", [])
                entity_state = None
                for state in states:
                    if state.get("entity_id") == self.entity_id:
                        entity_state = state
                        break

                if entity_state is None:
                    raise RuntimeError(
                        f"Entity '{self.entity_id}' not found in HomeAssistant"
                    )

                logger_ha_details.debug(
                    "Found entity state: %s", json.dumps(entity_state, indent=2))

                # Parse forecast data from attributes
                attributes = entity_state.get("attributes", {})
                forecast_dict = self._parse_forecast_from_attributes(
                    attributes)

                logger_ha_details.debug(
                    "Parsed %d hours of forecast data", len(forecast_dict))

                return forecast_dict

            finally:
                # Only disconnect if we created the connection
                if should_disconnect:
                    await self._websocket_disconnect(websocket)

        except Exception as e:
            logger.error(
                "Failed to fetch forecast from HomeAssistant: %s", e)
            raise RuntimeError(
                f"HomeAssistant WebSocket request failed: {e}") from e

    def _parse_forecast_from_attributes(
        self,
        attributes: dict
    ) -> Dict[int, float]:
        """Parse forecast data from sensor attributes

        Supports multiple formats:
        1. Primary: hours_list array with {time, kwh} objects
        2. Fallback: hour_1, hour_2, ... attributes with times

        Args:
            attributes: Sensor attributes dict from HomeAssistant

        Returns:
            Dict mapping hour index (0, 1, 2, ...) to generation in Wh

        Raises:
            ValueError: If no valid forecast data found
        """
        forecast_dict: Dict[int, float] = {}

        # Try primary format: hours_list
        hours_list = attributes.get("hours_list")
        if hours_list and isinstance(hours_list, list) and len(hours_list) > 0:
            logger_ha_details.debug(
                "Parsing forecast from hours_list (%d entries)", len(hours_list))

            for hour_idx, entry in enumerate(hours_list):
                if not isinstance(entry, dict):
                    logger_ha_details.debug(
                        "Skipping non-dict entry in hours_list: %s", entry)
                    continue

                kwh_value = entry.get("kwh")
                if kwh_value is None:
                    logger_ha_details.debug(
                        "Skipping entry without 'kwh' key: %s", entry)
                    continue

                try:
                    kwh_value = float(kwh_value)
                    # Convert to Wh
                    wh_value = kwh_value * self.unit_conversion_factor

                    forecast_dict[hour_idx] = wh_value
                    logger_ha_details.debug(
                        "Hour %d: %.2f kWh -> %.2f Wh",
                        hour_idx, kwh_value, wh_value
                    )
                except (ValueError, TypeError) as e:
                    logger_ha_details.debug(
                        "Skipping invalid kWh value in hours_list: %s (error: %s)",
                        kwh_value, e)
                    continue

            if forecast_dict:
                return forecast_dict

            logger_ha_details.warning(
                "hours_list present but no valid entries parsed")

        # Fallback: Try hour_1, hour_2, ... format
        logger_ha_details.debug("Trying fallback hour_N attribute format")
        hour_idx = 1
        while True:
            hour_key = f"hour_{hour_idx}"
            hour_time_key = f"hour_{hour_idx}_time"

            if hour_key not in attributes:
                break  # No more hours

            kwh_value = attributes.get(hour_key)
            if kwh_value is None:
                logger_ha_details.debug(
                    "Skipping missing %s", hour_key)
                hour_idx += 1
                continue

            try:
                kwh_value = float(kwh_value)
                # Convert to Wh
                wh_value = kwh_value * self.unit_conversion_factor
                # hour_idx 1-based in attributes, but 0-based in forecast_dict
                forecast_dict[hour_idx - 1] = wh_value
                logger_ha_details.debug(
                    "Hour %d (%s): %.2f kWh -> %.2f Wh",
                    hour_idx - 1, attributes.get(hour_time_key, "?"),
                    kwh_value, wh_value
                )
            except (ValueError, TypeError) as e:
                logger_ha_details.debug(
                    "Skipping invalid kWh value for %s: %s (error: %s)",
                    hour_key, kwh_value, e)

            hour_idx += 1

        if not forecast_dict:
            raise ValueError(
                "Could not parse any forecast data from sensor attributes. "
                "Expected 'hours_list' array or 'hour_N' attributes."
            )

        return forecast_dict

    def _update_cache(self, forecast_dict: Dict[int, float]) -> int:
        """Store parsed forecast in cache

        Args:
            forecast_dict: Dict mapping hour index to generation in Wh

        Returns:
            Number of cache entries updated
        """
        with self._cache_lock:
            logger.debug(
                "Updating cache with %d hours of forecast data",
                len(forecast_dict)
            )
            updated_count = 0

            for hour_idx, wh_value in forecast_dict.items():
                cache_key = f"hour_{hour_idx}"
                self.forecast_cache[cache_key] = wh_value
                updated_count += 1

                logger_ha_details.debug(
                    "Updated cache: key=%s, value=%.2f Wh",
                    cache_key, wh_value
                )

        logger.info("Updated %d cache entries", updated_count)
        return updated_count

    def refresh_data(self) -> None:
        """Refresh solar forecast data from HomeAssistant

        Fetches the latest forecast from the sensor, parses it, and updates cache.
        """
        logger.info("Refreshing solar forecast data from HomeAssistant")

        try:
            # Run async fetch function
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            forecast_dict = loop.run_until_complete(
                self._fetch_forecast_async())

            if forecast_dict:
                self._update_cache(forecast_dict)
                logger.info(
                    "Successfully refreshed solar forecast with %d hours",
                    len(forecast_dict))
            else:
                logger.error(
                    "No forecast data obtained from HomeAssistant")

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error refreshing forecast: %s", e)

    def _get_forecast_native(self, hours: int) -> Dict[int, float]:
        """Get hour-aligned forecast at native (60-minute) resolution.

        Args:
            hours: Number of hours to forecast

        Returns:
            Dict mapping hour index to energy value (Wh per hour)
            Index 0 = start of current hour

        Raises:
            RuntimeError: If no forecast data available
        """
        # Check if cache has required data, refresh if needed
        missing_keys = False
        with self._cache_lock:
            for h in range(hours):
                cache_key = f"hour_{h}"
                if cache_key not in self.forecast_cache:
                    missing_keys = True
                    logger_ha_details.debug(
                        "Cache miss for key: %s", cache_key)
                    break

        if missing_keys:
            logger.info(
                "Cache missing required keys, refreshing solar forecast data")
            self.refresh_data()

        # Generate forecast for requested hours
        prediction = {}

        for h in range(hours):
            cache_key = f"hour_{h}"

            with self._cache_lock:
                wh_value = self.forecast_cache.get(cache_key)

            if wh_value is not None:
                prediction[h] = wh_value
            else:
                logger_ha_details.warning(
                    "No cached data for %s", cache_key
                )
                # Break on first cache miss
                break

        if prediction:
            values = list(prediction.values())
            logger.debug(
                "Generated %d hour forecast: avg=%.1f Wh, min=%.1f Wh, max=%.1f Wh",
                len(prediction),
                sum(values) / len(values) if values else 0,
                min(values) if values else 0,
                max(values) if values else 0
            )
        else:
            logger.error("Generated empty forecast")
            raise RuntimeError("No solar forecast data available")

        return prediction
