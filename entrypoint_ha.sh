#!/bin/sh
set -e

SHARED_FOLDER="/batcontrol/addon_config"
CONFIG_FOLDER="/batcontrol/config"

CONFIG_FILE="$CONFIG_FOLDER/batcontrol_config.yaml"
CONFIG_FILE_SHARED="$SHARED_FOLDER/batcontrol_config.yaml"
CONFIG_FILE_HA="/data/options.json"

LOAD_PROFILE="$CONFIG_FOLDER/load_profile.csv"
LOAD_PROFILE_DEFAULT="$CONFIG_FOLDER/load_profile_default.csv"
LOAD_PROFILE_SHARED="$SHARED_FOLDER/load_profile.csv"

LOGFILE="/data/batcontrol.log"

# use custom config file, if available
if test -e $CONFIG_FILE_SHARED ; then
  echo "Using Config file found in addon config folder."
  ln -sf $CONFIG_FILE_SHARED $CONFIG_FILE
else
  echo "Config file batcontrol_config.yaml not found in addon config folder. Proceeding with data from HA Addon configuration"
  ln -sf $CONFIG_FILE_HA $CONFIG_FILE
fi

# use custom load profile, if available
if test -e $LOAD_PROFILE_SHARED ; then
  echo "Custom load_profile.csv found in addon config folder. Using custom load profile"
  ln -sf $LOAD_PROFILE_SHARED $LOAD_PROFILE
else
  echo "Custom load_profile.csv not found in addon config folder. Proceeding with default load profile"
  ln -sf $LOAD_PROFILE_DEFAULT $LOAD_PROFILE
fi

# Check if logfile exists. If not
# Create a symlink to /app/log/batcontrol.log
if test ! -e $LOGFILE ; then
  touch $LOGFILE
  ln -sf $LOGFILE /app/logs/batcontrol.log
fi

# Start batcontrol.py
exec python batcontrol.py
