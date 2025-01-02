# How does it work?

In winter time there is usually not enough energy available from your residential pv installation to meet your demand, so you need to get additional energy from the grid. 
This software helps to get the additional energy at the cheapest price by controlling your inverter in a smart way.

The software pulls three forecasts:

1. electricty prices - from the Tibber API or from the Awattar API for other EPEX Spot based tariffs.
2. your pv electricity production forecast based on the pv installation.
3. your electricty consumption forecast based on the load profile. You can provide your own or the use the default profile. In any case, the load profile is scaled to the annual consumption that you provide.

From 2. and 3. the net consumption (i.e. load - pv production) is forecast, which forms the basis of all further calculations which are run every three minutes.

Based on the three forecasts AND the current state of charge (SOC) the software puts the inverter in one of the three modes.

To correctly configure the software for your home, you will need to adapt the settings in: config/batcontrol_config.yaml

## Modes

### MODE 10 - DISCHARGE ALLOWED . 
This is the normal mode of the battery if there is sufficient energy available or energy is currently expensive. If the battery is full the surplus will be fed into the grid. If there is not enough energy coming from your pv installatation to meet your demand energy from the battery will be used. 

In addition it is possible to limit the battery charge using the configuration parameter ``max_pv_charge_rate``. At a battery SOC above ``always_allow_discharge_limit`` batcontrol will always allow discharging.

### MODE 0 - AVOID DISCHARGE. 
If your consumption exceeds your current production energy from the grid will be used and the battery will not be discharged. This mode is used if prices are increasing in the future and the energy from the battery can be more efficiently used in the future. Direct consumption is not affected.

### MODE -1 - CHARGE FROM GRID. 
The battery is charged from the grid at a certain charge rate. This mode calculates the estimated required energy for future hours with high electricity prices. The objective is to charge the battery enough so that you do not need to consume energy from the grid in these hours with high prices.
The difference in price is configured with ``min_price_difference``. Charging and Discharging has losses of up to 20%, depending on set-up. This should be considered in the configuration depending on your actual set-up.
How fast the battery can be charged via the grid is defined with the ``max_grid_charge_rate`` configuration. There is a seperate general upper recharge limit is ``max_charging_from_grid_limit``.

## Heatpump integration
### Thermia Heatpump Strategy

The Thermia heat pump integration in this software is designed to optimize the operation of your heat pump based on electricity prices, energy consumption, and energy production forecasts. The strategy aims to minimize energy costs by adjusting the heat pump's operating modes according to predefined rules and configurations.

#### Thermia Online API Extension

The Thermia Online API (https://github.com/klejejs/python-thermia-online-api) has been forked and extended (https://github.com/hashtagKnorke/thermia-online-api/tree/add_calendars) to leverage the Calendar function schedule API of Thermia Online API for setting up the behavior of the Thermia heat pump. This extension allows to control the heat pump based on predefined schedules and energy price forecasts.

##### Integration of the fork
The changes in the fork have been raised as a PR (https://github.com/klejejs/python-thermia-online-api/pull/48) so that they might converge into the mainstream library. For the meantime, the fork has been integrated into the batcontrol repo as a a submodule, integrating the library as sourcecode during dockerfile build.  
In case the directory is not in path a small hack in (https://github.com/hashtagKnorke/batcontrol/blob/be5f4eb2df73936234807a4ff355b7d1a9da882e/heatpump/thermia_heatpump.py#L36) tries to add the subdir to the pyton path so that the import succeeds.

##### Key Enhancements

1. **Calendar Function Integration**: The API now supports the Calendar function, enabling users to define and manage schedules for the heat pump's operation. This allows for automated adjustments to the heat pump's modes based on time and energy price forecasts.

2. **Enhanced Scheduling**: Users can create, update, and delete schedules for the heat pump. These schedules can specify different operating modes for different times of the day, optimizing energy usage and cost savings.

##### API Methods

The following methods have been added to the Thermia API to support the Calendar function:

- **get_schedules(installation_id: str)**: Retrieves the schedules for a given installation.
- **add_new_schedule(installation_id: str, data: dict)**: Adds a new schedule for a given installation.
- **delete_schedule(installation_id: str, schedule_id: int)**: Deletes a schedule for a given installation.

These methods allow for full control over the scheduling of the heat pump's operation, enabling users to optimize energy usage and minimize costs effectively.

#### Benefits

- **Cost Savings**: By scheduling the heat pump to operate in energy-saving modes during high price periods, users can significantly reduce their energy costs.
- **Automation**: The integration with the Calendar function allows for automated control of the heat pump, reducing the need for manual adjustments.
- **Flexibility**: Users can define multiple schedules with different operating modes, providing flexibility to adapt to changing energy prices and consumption patterns.

To get started with the extended Thermia Online API, refer to the documentation and configure the necessary settings in the `config/batcontrol_config.yaml` file.

#### Key Components

1. **ThermiaHighPriceHandling**: Manages settings to handle high price periods.
2. **ThermiaStrategySlot**: Represents a strategy decision for a specific time slot.
3. **ThermiaHeatpump**: The main class that manages and controls the Thermia heat pump.

#### Strategy Overview

The strategy involves setting the heat pump to the most energy-saving mode during high price periods while considering the following modes:

- **E: EVU Block**: Activated when electricity prices are high. Maximum energy saving, deactivating heating and Hot water production.
- **B: Hot Water Block**: Activated to block hot water production during high price periods.
- **R: Reduced Heat**: Lowers the heating effect to save energy.
- **N: Normal mode**: No adjustments to heatpump behaviour.
- **H: Increased Heat**: Increases heating when energy is cheap or there is a PV surplus.
- **W: Hot Water Boost**: Boosts hot water production when there is an energy surplus.

#### Configuration Parameters

- **min_price_for_evu_block**: Minimum price to trigger EVU block mode.
- **max_evu_block_hours**: Maximum hours per day for EVU block mode.
- **max_evu_block_duration**: Maximum continuous duration for EVU block mode.
- **min_price_for_hot_water_block**: Minimum price to trigger hot water block mode.
- **max_hot_water_block_hours**: Maximum hours per day for hot water block mode.
- **max_hot_water_block_duration**: Maximum continuous duration for hot water block mode.
- **min_price_for_reduced_heat**: Minimum price to trigger reduced heat mode.
- **max_reduced_heat_hours**: Maximum hours per day for reduced heat mode.
- **max_reduced_heat_duration**: Maximum continuous duration for reduced heat mode.
- **reduced_heat_temperature**: Temperature setting for reduced heat mode.
- **max_price_for_increased_heat**: Maximum price to trigger increased heat mode.
- **min_energy_surplus_for_increased_heat**: Minimum energy surplus to trigger increased heat mode.
- **max_increased_heat_hours**: Maximum hours per day for increased heat mode.
- **max_increased_heat_duration**: Maximum continuous duration for increased heat mode.
- **increased_heat_temperature**: Temperature setting for increased heat mode.
- **max_increased_heat_outdoor_temperature**: Maximum outdoor temperature for increased heat mode.
- **min_energy_surplus_for_hot_water_boost**: Minimum energy surplus to trigger hot water boost mode.
- **max_hot_water_boost_hours**: Maximum hours per day for hot water boost mode.

#### Operation

The software continuously monitors electricity prices, energy consumption, and production forecasts. Based on these inputs and the current state of charge (SOC) of the battery, it dynamically adjusts the heat pump's operating mode to optimize energy usage and minimize costs.

The strategy is recalculated every three minutes to ensure that the heat pump operates in the most cost-effective manner, taking into account the latest forecasts and current conditions.

To configure the Thermia heat pump integration, you will need to adapt the settings in `config/batcontrol_config.yaml`.
