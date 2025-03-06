**Optimize your electricity costs by re-charging your PV battery when electricity is cheap and there is not enough solar power available.**
To integrate batcontrol with Home Assistant, use the following repository: [ha_addons](https://github.com/muexxl/ha_addons/)

[![Pylint](https://github.com/muexxl/batcontrol/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/muexxl/batcontrol/actions/workflows/pylint.yml)
[![Docker Image CI](https://github.com/muexxl/batcontrol/actions/workflows/docker-image.yml/badge.svg?branch=main)](https://github.com/muexxl/batcontrol/actions/workflows/docker-image.yml)

## Prerequisites:

1. A PV installation with a BYD Battery and a Fronius Gen24 inverter.
2. An EPEX Spot based contract with hourly electricity pricing, like Awattar, Tibber etc. (Get a €50 bonus on sign-up to Tibber using this [link](https://invite.tibber.com/x8ci52nj).)
3. Customer login details to the inverter.

## Preparations:

# Local installation
## Preparations:
1. Verify the credentials of your inverter for customer or technician access. You can use either.
2. Obtain your Tibber API key from [Tibber Developer](https://developer.tibber.com/), if you use Tibber. 
3. Create your `batcontrol_config.yaml` in the config folder.
4. Configure your electricity tariff and pv installation.
5. Customize your load profile or use the default one and set your annual consumption.
6. If you have run any third-party tools using Modbus or ran some Modbus commands yourself, switch these off and restart the inverter.


## Installation:

## Install:
```sh
git clone https://github.com/muexxl/batcontrol.git
cd batcontrol
virtualenv venv
source venv/bin/activate
pip install .
```

## run
```sh
python -m batcontrol # When venv is activated
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

### Adjusting Timezone

To adjust the timezone for logging and output, set the `TZ` environment variable.

#### Plain Docker

```
docker run -d \
  --name batcontrol \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Europe/Berlin \
  muexx/batcontrol:latest
```

#### Docker-compose example

Add the `TZ` environment variable to your `docker-compose.yml`:

```
version: '3.8'

services:
  batcontrol:
    image: muexx/batcontrol:latest
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    environment:
      - TZ=Europe/Berlin
    restart: unless-stopped
```

# FAQs

## How are the different config parameters related to each other?

The parameters follow this order:

`MIN_SOC -> Backup-Power-Reserved -> max_charging_from_grid_limit -> always_allow_discharge_limit -> MAX_SOC`

The `always_allow_discharge_limit` parameter overrides any logic and allows the battery to discharge freely according to the inverter's logic.

The `max_charging_from_grid_limit` parameter charges from the minimum up to the `always_allow_discharge_limit`.

## What inverter settings will this change?

1. The software will enable the Solar.API (local network only), without which it cannot work and this will remain enabled on shut down.
2. It will save the current configuration of the battery and its usage schedule (and this will be restored to the original settings on shut down).
3. Charging from grid will be enabled (and this will be restored to the original setting on shut down).
4. The battery settings will be changed on every run of the software according to the three modes.

## Can I run other software that attempts to control the battery and inverter at the same time?

Running other software that controls the inverter or battery is currently not supported and will likely cause conflicts. If you have previously run software that controls the inverter with modbus, disable modbus and restart the inverter before running batcontrol.

## What if I need to change inverter settings while batcontrol is running?

Changing settings through the local webinterface of the inverter is possible, but not recommended. 
The recommended course of action is to shut down batcontrol, make the necessary changes and then restart batcontrol to avoid any conflicts and ensure the correct configuration is saved.

# Uninstall

To uninstall batcontrol and restore the inverter settings follow these steps:
1. Check if batcontrol is running.
2. If batcontrol is not running, check your inverters battery control schedule in the web UI. If it does not look right, batcontrol might have crashed recently. In that case restart batcontrol and then shut it down after it has finished the first run and has gone to sleep.
3. If batcontrol is running, shut it down while it is sleeping to restore the saved inverter settings.
4. Check your inverters local web UI to confirm that the inverter settings have been correctly restored.
5. Remove the software from wherever it was running from or delete the docker container.
6. Disable the Solar API in your inverters web UI, if it is not needed by any other third party software or wallboxes. For example the Fronius Wattpilot will NOT work with the solar API disabled.

# Local development

For running batcontrol off the repository for development puroposes, it is required to uses pip with [Developermode](https://setuptools.pypa.io/en/latest/userguide/development_mode.html)

```sh
git clone https://github.com/muexxl/batcontrol.git
cd batcontrol
python -m venv .venv
# Activate your environment with:
#      `source .venv/bin/activate` on Unix/macOS
# or   `.venv\Scripts\activate` on Windows

pip install --editable . 

# Now you have access to your package
# as if it was installed in .venv
python -m batcontrol
```
