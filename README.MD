**Optimize your Electricity cost by re-charging your PV Battery when Electricity is cheap and there is not enough Solarpower available.**
To integrate batcontrol with Home Assistant, use the following repository: [ha_addons](https://github.com/muexxl/ha_addons/)

## Prerequisites:

1. A PV installation with a BYD Battery and a Fronius inverter.
2. A Tibber or aWattar contract with hourly electricity pricing. (Get a €50 bonus on sign-up using this [link](https://invite.tibber.com/x8ci52nj).)

## Preparations:

1. Verify the credentials of your inverter for customer or technician access.
2. Obtain your Tibber API key from [Tibber Developer](https://developer.tibber.com/).
3. Create your `batcontrol_config.yaml` in the config folder.
4. Customize your load profile or use the default one.

## Installation:

```sh
git clone https://github.com/muexxl/batcontrol.git  
cd batcontrol  
virtualenv venv  
source venv/bin/activate  
pip install -r requirements.txt  
```

## Running the Application:

```sh
cd /PATH/TO/batcontrol  
source venv/bin/activate        
python batcontrol.py  
```

# FAQs

## How are the different config parameters related to each other?

The parameters follow this order:

`MIN_SOC -> Backup-Power-Reserved -> max_charging_from_grid_limit -> always_allow_discharge_limit -> MAX_SOC`

The `always_allow_discharge_limit` parameter overrides any logic and allows the battery to operate freely according to the inverter's logic.

The `max_charging_from_grid_limit` parameter charges from the minimum up to the `always_allow_discharge_limit`.