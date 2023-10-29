Optimize your Electricity cost by re-charging your PV Battery when Electricity is cheap and there is not enough Solarpower available.

Preconditions: 

1. You have a PV Installation with a BYD Battery and a Fronius inverter
2. You have a Tibber contract with hourly electricity pricing

Preparations:

1. verify the credentials of your inverter for customer or technician
2. get your tibber API key from https://developer.tibber.com/
3. create your batcontrol_config.yaml in the config folder
4. customize your load profile or use the default load profile

Install:

git clone https://github.com/muexxl/batcontrol.git
cd batcontrol
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt

run:

source venv/bin/activate
python batcontrol.py
