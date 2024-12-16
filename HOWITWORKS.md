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
