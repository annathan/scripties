#!/usr/bin/with-contenv bashio

_json_to_csv() {
  python3 -c "
import sys, json
try:
    print(','.join(json.load(sys.stdin)))
except Exception:
    print('')
" 2>/dev/null || echo ""
}

export WEATHER_ENTITY=$(bashio::config 'weather_entity')
export SCHOOL_CALENDAR=$(bashio::config 'school_calendar')
export PORT=$(bashio::config 'port')
export PHOTOS_PATH=$(bashio::config 'photos_path')
export LEAVE_SOON_MINUTES=$(bashio::config 'leave_soon_minutes')

export CALENDARS=$(bashio::config 'calendars' | _json_to_csv)
export CHORE_LISTS=$(bashio::config 'chore_lists' | _json_to_csv)

# Supervisor injects SUPERVISOR_TOKEN; HA API is at http://supervisor/core
export HA_URL="http://supervisor/core"

cd /app
exec python3 main.py
