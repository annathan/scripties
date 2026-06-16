# Home Automation — Home Assistant Configuration

A self-hosted Home Assistant setup for a large family home. Covers presence-based
arrival automations, whole-house Zigbee lighting, solar surplus routing, security
alarm, water leak detection, and a school-routine lighting schedule for the kids.

Built for **Home Assistant OS** on a mini-PC (HP ProDesk 600 G3 Mini or similar).

---

## Hardware

| Role | Hardware |
|---|---|
| HA server | HP ProDesk 600 G3 Mini (i7-7700T) or equivalent refurb mini-PC |
| Zigbee coordinator | Sonoff ZBDongle-E (CC2652P) |
| In-wall dimmers | Mercator Ikuü SSWM-DIMZ (trailing-edge, no neutral required) |
| Colour/ambience bulbs | Philips Hue colour bulbs + Hue Gradient Lightstrip (TV) |
| Alfresco lights | Mirabella Genio Wi-Fi GU10 (Tuya/Local Tuya, outdoor/alfresco only) |
| Garage door | ratgdo (Chamberlain/LiftMaster Security+ 2.0) |
| Front door lock | Eufy Security S330 or T8520 (via eufy-security-ws Docker bridge) |
| Solar inverter | GoodWe GW5000-DNS-30 (local UDP, no cloud) |
| Motion sensors | Aqara or SONOFF SNZB-03 PIR (Zigbee) |
| Door/window sensors | Zigbee contact sensors |
| Leak sensors | Zigbee water leak sensors |
| Pool (future) | ESP32 + MAX485 → Pentair RS-485 bus |
| Cameras | Ring doorbell + Blink cameras (cloud integrations) |
| Mobile presence | HA Companion app (iOS/Android) |
| MQTT broker | Mosquitto (HA add-on) |

**Downlight wiring note:** The HPM downlights in this house (LDLE90TRIWE, 7W)
connect to the ceiling loom via roof-space quick-connect plugs — standard AU
practice. This has no effect on the wall-switch dimmer install. The Mercator
Ikuü SSWM-DIMZ is a trailing-edge dimmer, matching the "trailing edge dimmer
only" spec on these fixtures. Minimum load is 11W; flag any single-downlight
switch loops to the electrician (two 7W fixtures = 14W, which clears the
threshold comfortably).

---

## Directory layout

```
home-automation/
├── configuration_example.yaml   # How to wire all files into configuration.yaml
├── secrets_example.yaml         # Template — copy to secrets.yaml, fill in real values, NEVER commit
├── zones.yaml                   # Home (75m) + Approaching (300m) zones
├── persons.yaml                 # Alice, Bob, Uni Student, Kid 1/2/3
│
├── packages/
│   ├── helpers.yaml             # Arrival flags, solar thresholds, relock delay
│   ├── lighting_helpers.yaml    # Sick-day flags, movie mode, colour party, room scene selectors
│   ├── alarm.yaml               # Manual alarm panel + security sensor groups
│   └── eufy_lock.yaml           # Eufy lock setup notes and exposed entities
│
├── automations/
│   ├── presence_garage.yaml     # Geo-fenced garage open on arrival; auto-close when away
│   ├── presence_front_door.yaml # Front door unlock on arrival; auto-relock + night lock
│   ├── alarm_panel.yaml         # Auto arm/disarm + trigger actions (push + camera snapshot)
│   ├── water_leak.yaml          # Critical alerts + main valve auto-shutoff
│   ├── solar_surplus.yaml       # 3-tier surplus routing: hot water → pool pump → EV charging
│   ├── lighting_school_routine.yaml  # Wake-up ramp + auto-off at school time (Google Calendar)
│   ├── lighting_scenes.yaml     # Morning, evening, movie mode, bedtime, away, colour party
│   ├── lighting_motion.yaml     # PIR-triggered lights in entry, staircase, bathrooms, ensuite
│   └── lighting_exhaust_fans.yaml   # Fans on with lights; 10-min delayed off after lights off
│
└── esphome/
    └── pool_pentair.yaml        # ESP32 pool controller template (Pentair RS-485)
```

---

## First-time setup

### 1. Copy files into HA config

Copy everything under `home-automation/` into your HA config directory
(`/config/` on Home Assistant OS). Then add the wiring from
`configuration_example.yaml` into your actual `configuration.yaml`.

### 2. Create secrets.yaml

```bash
cp secrets_example.yaml secrets.yaml
# Edit secrets.yaml with your real values — GPS coords, passwords, alarm PIN
```

**Never commit `secrets.yaml` to git.**

### 3. Install required integrations

**Via UI** (Settings → Integrations):
- GoodWe (solar inverter — local UDP, no cloud)
- Ring (cameras/doorbell)
- Blink (cameras)
- Google Calendar (for school-day automation logic)
- ZHA (Zigbee — after plugging in the Sonoff ZBDongle-E)

**Via HACS:**
- `eufy_security` — Eufy smart lock
- `localtuya` — Mirabella Genio alfresco lights (if using)

**Add-ons:**
- Mosquitto broker (MQTT — required for ratgdo and ESPHome)
- ESPHome (if building the pool controller)
- File editor or Studio Code Server (for editing config files)

### 4. Pair Zigbee devices via ZHA

Pair all Zigbee devices (dimmers, PIR sensors, contact sensors, leak sensors)
in ZHA, then rename each entity to match the IDs used in the automations.
See the entity naming comments at the top of each automation file.

### 5. Set up ratgdo (garage door)

Flash ratgdo firmware and connect to your Chamberlain/LiftMaster rail.
It auto-discovers via MQTT once Mosquitto is running. Entity: `cover.garage_door`.

### 6. Run the Eufy security bridge

```bash
docker run -d \
  --name eufy-security-ws \
  --restart unless-stopped \
  -p 3000:3000 \
  -e USERNAME="your@email.com" \
  -e PASSWORD="your_eufy_password" \
  -e COUNTRY="AU" \
  bropat/eufy-security-ws:latest
```

Then add the Eufy Security integration in HA pointing at the bridge.
See `packages/eufy_lock.yaml` for full setup steps.

### 7. Create the snapshot directory

```bash
mkdir -p /config/www/snapshots
```

The alarm trigger automation saves Ring camera snapshots here.

---

## Key automations at a glance

### Presence & arrival
- Garage door opens when Alice or Bob's phone enters the home zone (with a 300m
  "approaching" zone for early warning). A `was_away` flag prevents spurious
  triggers if HA restarts while someone is home.
- Front door auto-unlocks on arrival and re-locks after a configurable delay
  (default 3 min, adjustable from the dashboard).
- All automations respect `input_boolean.arrival_automations_enabled` — flip
  it off during parties when people will be coming and going.

### Lighting — school routine
- **Beds 2, 3, 4 (school kids, first floor):** Lights ramp up at 07:00 (warm
  to cool over 10 min) and turn off at 08:45 on school days
  (`calendar.kids_school_days`). Each kid has a sick-day toggle on the
  dashboard so their lights stay on if they're home.
- **Bed 5 (uni student, ground floor):** Entirely independent — lights follow
  her phone presence, not the school calendar.

### Lighting — scenes & motion
- Morning ramp, evening wind-down at sunset, movie mode (dim + TV lightstrip),
  colour party mode (colorloop on Hue lamps), kids bedtime (deep red → off),
  and all lights off with a 5-min grace period when the house empties.
- PIR sensors handle entry, staircase, landing (night-light mode after 22:00),
  master ensuite, and both bathrooms.
- Exhaust fans come on with their bathroom light and stay on for 10 min after
  the light turns off.

### Solar surplus routing
Three-tier dispatch keyed off `sensor.goodwe_grid_power`:

| Threshold | Action |
|---|---|
| > 1 kW export | Hot water boost |
| > 2 kW export | Pool pump high speed |
| > 3 kW export | EV charging |

Each tier requires the surplus to hold for 5 minutes before switching and uses
hysteresis to avoid toggling on cloud flicker. All dispatch stops at sunset.
Thresholds are adjustable from the dashboard (`input_number.solar_threshold_*`).

### Security alarm
Auto arms to `armed_away` when everyone leaves; disarms when the first person
arrives. Armed_home and armed_night modes available from the dashboard.
Perimeter breach → critical push notification + Ring camera snapshot.

### Water leak
Zigbee leak sensors send a critical push notification (bypasses iOS silent
mode) that repeats every 5 minutes until cleared. If nobody is home, the main
water valve auto-closes.

---

## Adapting to your house

1. **Rename persons** in `persons.yaml` to real names (IDs `kid_1`/`kid_2`/`kid_3`
   must stay the same to match automation references).
2. **Replace placeholder entity IDs** — every file has comments showing the
   expected entity IDs (e.g. `light.kitchen_dimmer`). After pairing devices
   in ZHA or HA UI, rename them to match.
3. **Adjust thresholds** from the HA dashboard — relock delay, solar surplus
   thresholds, and alarm code are all runtime-configurable via helpers.
4. **Google Calendar** — create a calendar named `Kids School Days` in Google,
   link it via the Google Calendar integration, and HA will use
   `calendar.kids_school_days` to drive the school-morning automations.

---

## What is NOT in this repo

- `secrets.yaml` — never commit real secrets to git
- HA database, `.storage/`, media files
- Actual Zigbee device pairing state (lives in HA's ZHA storage)
- Cloud integration credentials (Ring, Blink, Google) — stored in HA UI
