
import pandas as pd
import numpy as np
import datetime
import math
import logging

logger = logging.getLogger("__main__")
logger.info(f'[FCConsumption] loading module ')

class ForecastConsumption(object):
    """Forecasts Consumption based on load profiles
    
        Loadprofile: 
        csv file containing, month(1..12), weekday(0..6, 0-Monday), hour(0..24) and Energy in Wh
        
        Can create load profiles:
        required input: csv file containing
            - 'timestamp' Timestamp in ISO format
            - 'energy' consumption in one our periods measured in Ws - Yes, Wattseconds!

        forecasting will be done by considering month, weekday and hour
    """

    def __init__(self, loadprofile, datafile=None) -> None:
        self.path_to_load_profile=loadprofile
        if datafile:
            self.create_loadprofile(datafile,self.path_to_load_profile)
            
        self.load_loadprofile()

    def load_data_file(self, datafile):
        df = pd.read_csv(datafile)
        df['timestamp'] = df['timestamp'].map(
            lambda timestamp: pd.to_datetime(timestamp).astimezone('UTC+01:00'))
        df['month'] = df['timestamp'].map(lambda timestamp: timestamp.month)
        df['weekday'] = df['timestamp'].map(
            lambda timestamp: timestamp.dayofweek)
        df['hour'] = df['timestamp'].map(lambda timestamp: timestamp.hour)
        # convert Ws to Wh and adjust sign
        df['energy'] = df['energy']/3600*-1
        return df

    def get_forecast(self, hours):
        t0 = datetime.datetime.now()
        df = self.dataframe
        prediction = {}

        for h in range(hours):
            delta_t = datetime.timedelta(hours=h)
            t1 = t0+delta_t
            energy = df.loc[df['hour'] == t1.hour].loc[df['month'] ==
                                               t1.month].loc[df['weekday'] == t1.weekday()]['energy'].median()
            if math.isnan(energy):
                energy = df['energy'].median()
            prediction[h]=energy
        
        logger.debug(f'[FC Cons] predicting consumption {prediction}')
        return prediction
    
    def create_loadprofile(self, datafile, path_to_profile='load_profile.csv'):
        df=self.load_data_file(datafile)
        a=[]
        energy=0
        for month in range(1,13):
            for day in range(7):
                for hour in range(24):
                    energy = df.loc[df['hour'] == hour].loc[df['month'] == month].loc[df['weekday'] == day]['energy'].mean()
                    a.append([month,day,hour,energy])
        df_load_profile=pd.DataFrame(a)
        df_load_profile.to_csv(path_to_profile,header=['month','weekday','hour','energy'], index=None)
        
    def load_loadprofile(self):
        self.dataframe=pd.read_csv(self.path_to_load_profile)

if __name__ == '__main__':
    fc=ForecastConsumption('load_profile.csv')
    print(fc.get_forecast(25))
 