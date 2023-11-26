**Optimize your Electricity cost by re-charging your PV Battery when Electricity is cheap and there is not enough Solarpower available.**

# Preconditions: 

1. You have a PV Installation with a BYD Battery and a Fronius inverter  
1. You have a Tibber contract with hourly electricity pricing. (Use this link if you want 50€ Bonus on sign up https://invite.tibber.com/x8ci52nj.)  

# Preparations:

1. verify the credentials of your inverter for customer or technician
1. get your tibber API key from https://developer.tibber.com/
1. create your batcontrol_config.yaml in the config folder
1. customize your load profile or use the default load profile

# Install:
```
git clone https://github.com/muexxl/batcontrol.git  
cd batcontrol  
virtualenv venv  
source venv/bin/activate  
pip install -r requirements.txt  
```

# run 
```
cd /PATH/TO/batcontrol  
source venv/bin/activate        
python batcontrol.py  
```
