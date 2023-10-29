#! /usr/bin/env python

import datetime
import math
import requests
import json
import logging

logger = logging.getLogger('__main__')
logger.info(f'[Tibber] loading module ')


class Tibber(object):
    def __init__(self,token=None, timezone=None) -> None:
        self.access_token=token
        self.timezone=timezone
    def get_prices(self, homeid=0):      
        if not self.access_token:
            raise RuntimeError
        url="https://api.tibber.com/v1-beta/gql"
        headers={"Authorization":"Bearer " + self.access_token, 
                "Content-Type":"application/json"}

        data="""{ "query": 
        "{viewer {homes {currentSubscription {priceInfo { current {total startsAt } today {total startsAt } tomorrow {total startsAt }}}}}}" }
        """
        raw_result=requests.post(url,data,headers=headers)
        result=json.loads(raw_result.text)
        now=datetime.datetime.now().astimezone(self.timezone)
        prices={}
        for day in ['today', 'tomorrow']:
            dayinfo=result["data"]['viewer']['homes'][homeid]['currentSubscription']['priceInfo'][day]
            for item in dayinfo:
                timestamp=datetime.datetime.fromisoformat(item['startsAt'])
                diff=timestamp-now
                rel_hour=math.ceil(diff.total_seconds()/3600)
                if rel_hour >=0:
                    prices[rel_hour]=item['total']
        return prices