#!/usr/bin/env bash

_opt() {
  python3 - "$1" <<'PY'
import json, sys
key = sys.argv[1]
with open('/data/options.json') as f:
    data = json.load(f)
val = data.get(key)
if val is None:
    print('')
elif isinstance(val, (dict, list)):
    print(json.dumps(val))
else:
    print(val)
PY
}

_json_to_csv() {
  python3 -c "
import sys, json
try:
    print(','.join(json.load(sys.stdin)))
except Exception:
    print('')
" 2>/dev/null || echo ""
}

export WEATHER_ENTITY=$(_opt weather_entity)
export SCHOOL_CALENDAR=$(_opt school_calendar)
export PORT=$(_opt port)
export PHOTOS_PATH=$(_opt photos_path)
export LEAVE_SOON_MINUTES=$(_opt leave_soon_minutes)

export CALENDARS=$(_opt calendars | _json_to_csv)
export CHORE_LISTS=$(_opt chore_lists | _json_to_csv)

# Supervisor injects SUPERVISOR_TOKEN; HA API is at http://supervisor/core
export HA_URL="http://supervisor/core"

cd /app
exec python3 main.py
