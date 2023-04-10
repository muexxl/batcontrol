import datetime
import time
import math
import requests
import json
print("importing ForecastSolar..")


class ForecastSolar(object):
    def __init__(self, token=None) -> None:
        self.access_token = token
        self.result_e = {}
        self.result_w = {}
        self.last_update = 0
        self.seconds_between_updates = 900

    def get_forecast(self):
        t0 = time.time()
        dt = t0-self.last_update
        if dt > self.seconds_between_updates:
            self.get_raw_forecast()
            self.last_update = t0
        prediction={}
        for hour in range(48+1):
            prediction[hour]=0
        if self.result_e=={}:
            return prediction   
        if self.result_w=={}:
            return prediction   
        
        now = datetime.datetime.now()
        current_hour = datetime.datetime(
            now.year, now.month, now.day, now.hour).astimezone()
        response_time_string = self.result_e['message']['info']['time']
        response_time = datetime.datetime.fromisoformat(response_time_string)
        response_timezone = response_time.tzinfo
        for result in [self.result_e, self.result_w]:
            for isotime, value in result['result'].items():
                timestamp = datetime.datetime.fromisoformat(
                    isotime).astimezone(response_timezone)
                diff = timestamp-current_hour
                rel_hour = math.ceil(diff.total_seconds()/3600)-1
                if rel_hour >= 0:
                    if rel_hour in prediction.keys():
                        prediction[rel_hour]+=value
                    else:
                        prediction[rel_hour]=value
        return prediction

    def get_raw_forecast(self):
        lat = '49.634580'
        lon = '8.6315182'
        dec = '32'  # declination
        az = '87'  # 90 =W -90 = E
        kwp = '5.695'
        url = f"https://api.forecast.solar/estimate/watthours/period/{lat}/{lon}/{dec}/{az}/{kwp}"
        response = requests.get(url)
        if response.status_code == 200:
            self.result_w = json.loads(response.text)
        else:
            return

        dec = '32'  # declination
        az = '-93'  # 90 =W -90 = E
        kwp = '6.030'  # 5.695
        url = f"https://api.forecast.solar/estimate/watthours/period/{lat}/{lon}/{dec}/{az}/{kwp}"
        response = requests.get(url)
        if response.status_code == 200:
            self.result_e = json.loads(response.text)
            self.last_update = datetime.datetime.now()
        else:
            return
