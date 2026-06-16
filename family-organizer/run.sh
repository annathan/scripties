#!/usr/bin/with-contenv bashio

export WEATHER_ENTITY=$(bashio::config 'weather_entity')
export SCHOOL_CALENDAR=$(bashio::config 'school_calendar')
export PORT=$(bashio::config 'port')

# Convert JSON array to comma-separated string
CALS=$(bashio::config 'calendars')
export CALENDARS=$(echo "$CALS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(','.join(data))
except Exception:
    print('')
" 2>/dev/null || echo "")

# Supervisor injects SUPERVISOR_TOKEN; HA API is at http://supervisor/core
export HA_URL="http://supervisor/core"

cd /app
exec python3 main.py
