**Optimize your Electricity cost by re-charging your PV Battery when Electricity is cheap and there is not enough Solarpower available.**
To integrate batcontrol with Home Assistant, use the following repository: [ha_addons](https://github.com/muexxl/ha_addons/)

## Prerequisites:

1. A PV installation with a BYD Battery and a Fronius inverter.
2. An EPEX Spot based contract with hourly electricity pricing, like Awattar, Tibber etc. (Get a €50 bonus on sign-up to Tibber using this [link](https://invite.tibber.com/x8ci52nj).)

## Preparations:

# Local installation
## Preparations:
1. Verify the credentials of your inverter for customer or technician access.
2. Obtain your Tibber API key from [Tibber Developer](https://developer.tibber.com/), if you use Tibber. 
3. Create your `batcontrol_config.yaml` in the config folder.
4. Configure your electricity tariff and pv installation.
5. Customize your load profile or use the default one and set your annual consumption.


## Installation:

## Install:
```sh
git clone https://github.com/muexxl/batcontrol.git
cd batcontrol
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

## run
```sh
cd /PATH/TO/batcontrol
source venv/bin/activate
python batcontrol.py
```

# Docker usage

## Preparations

```
mkdir -p ./config -p ./logs
```

- Download the the latest [batcontrol_config.yaml](https://raw.githubusercontent.com/muexxl/batcontrol/refs/heads/main/config/batcontrol_config_dummy.yaml) sample, adjust and place it to config/batcontrol_config.yaml.

- Use the default load_profile (automatically) or create your own.-

### Plain Docker

```
docker run -d \
  --name batcontrol \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  muexx/batcontrol:latest
```

### Docker-compose example

Create docker-compose.yml with the following content:

```
version: '3.8'

services:
  batcontrol:
    image: muexx/batcontrol:latest
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
```

Then start the container using `docker-compose up -d`.

# FAQs

## How are the different config parameters related to each other?

The parameters follow this order:

`MIN_SOC -> Backup-Power-Reserved -> max_charging_from_grid_limit -> always_allow_discharge_limit -> MAX_SOC`

The `always_allow_discharge_limit` parameter overrides any logic and allows the battery to discharge freely according to the inverter's logic.

The `max_charging_from_grid_limit` parameter charges from the minimum up to the `always_allow_discharge_limit`.
