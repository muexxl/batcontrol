#! /usr/bin/env python

from fronius import fronius
import datetime
from tibber import tibber

from matplotlib import pyplot as plt

import credentials
access_token = credentials.tibber_key
fronius_user='customer'
fronius_password=credentials.fronius_password

tb=tibber.Tibber(access_token)
prices=tb.get_prices()


plt.plot(prices.keys(),prices.values())     