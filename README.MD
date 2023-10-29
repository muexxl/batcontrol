Optimize your Electricity cost

Preconditions: 

1. You have a PV Installation with a BYD Battery and a Fronius inverter
2. You have a Tibber contract with hourly electricity pricing

Preparations:

1. verify the credentials of your inverter for customer or technician
2. get your tibber API key from https://developer.tibber.com/
2. create your batcontrol_config.yaml in the config folder
3. customize your load profile or use the default load profile

Install:
(consider using virtualenv)

pip install -r requirements.txt

run:
python batcontrol.py
