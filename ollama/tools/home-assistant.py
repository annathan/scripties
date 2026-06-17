"""
title: Home Assistant Control
author: Drew
description: >
  Query and control Home Assistant from the chat interface.
  Jess (or anyone) can ask things like:
    "Is the front door locked?"
    "Turn on the pool pump"
    "What's the solar production right now?"
    "Close the garage door"
  The tool calls the HA REST API directly using a long-lived access token.
required_open_webui_version: 0.3.17
"""

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        ha_url: str = Field(
            default="http://homeassistant.local:8123",
            description=(
                "Base URL of your Home Assistant instance. "
                "Use the LAN IP if mDNS doesn't resolve: http://192.168.x.x:8123"
            ),
        )
        ha_token: str = Field(
            default="",
            description=(
                "Long-lived access token from HA. Generate one at: "
                "HA → Profile (bottom-left) → Long-lived access tokens → Create token"
            ),
        )

    def __init__(self):
        self.valves = self.Valves()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.valves.ha_token}",
            "Content-Type": "application/json",
        }

    def get_entity_state(self, entity_id: str) -> str:
        """
        Get the current state and attributes of a Home Assistant entity.
        Use this to answer questions like "Is the front door locked?",
        "What's the temperature outside?", "Is the garage door open?",
        or "How much solar power are we generating?".
        :param entity_id: The HA entity ID, e.g. lock.front_door, sensor.goodwe_pv_power.
        :return: A plain-English description of the entity's current state.
        """
        try:
            resp = requests.get(
                f"{self.valves.ha_url}/api/states/{entity_id}",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code == 404:
                return f"I couldn't find '{entity_id}' in Home Assistant. Check the entity ID is correct."
            if resp.status_code != 200:
                return f"Home Assistant returned an error (status {resp.status_code})."

            data = resp.json()
            state = data.get("state", "unknown")
            attrs = data.get("attributes", {})
            unit = attrs.get("unit_of_measurement", "")
            friendly = attrs.get("friendly_name", entity_id)

            if unit:
                return f"{friendly} is {state} {unit}."
            return f"{friendly} is {state}."

        except requests.exceptions.ConnectionError:
            return "Can't reach Home Assistant. Check the HA URL in tool settings."
        except requests.exceptions.Timeout:
            return "Home Assistant didn't respond in time. It may be restarting."
        except Exception as e:
            return f"Something went wrong: {e}"

    def call_service(self, domain: str, service: str, entity_id: str) -> str:
        """
        Call a Home Assistant service to control a device.
        Use this to turn devices on or off, lock/unlock doors, open/close covers, etc.
        Examples:
          - Turn off the pool pump: domain=switch, service=turn_off, entity_id=switch.pool_pump_high_speed
          - Lock the front door: domain=lock, service=lock, entity_id=lock.front_door
          - Open the garage: domain=cover, service=open_cover, entity_id=cover.garage_door
          - Turn on hot water boost: domain=switch, service=turn_on, entity_id=switch.hot_water_boost
        :param domain: The HA domain, e.g. switch, lock, cover, light, script.
        :param service: The service to call, e.g. turn_on, turn_off, lock, unlock, open_cover, close_cover.
        :param entity_id: The HA entity ID to target, e.g. switch.pool_pump_high_speed.
        :return: Confirmation that the command was sent, or an error message.
        """
        try:
            resp = requests.post(
                f"{self.valves.ha_url}/api/services/{domain}/{service}",
                headers=self._headers(),
                json={"entity_id": entity_id},
                timeout=5,
            )
            if resp.status_code in (200, 201):
                action = service.replace("_", " ").replace("turn ", "")
                friendly = entity_id.split(".")[-1].replace("_", " ")
                return f"Done — {friendly} {action}."
            return f"Home Assistant returned an error (status {resp.status_code})."

        except requests.exceptions.ConnectionError:
            return "Can't reach Home Assistant. Check the HA URL in tool settings."
        except requests.exceptions.Timeout:
            return "Home Assistant didn't respond in time. It may be restarting."
        except Exception as e:
            return f"Something went wrong: {e}"

    def get_solar_summary(self) -> str:
        """
        Get a summary of the current solar production and grid status.
        Use this when the user asks about solar power, what's being exported,
        or whether it's a good time to run high-power appliances.
        :return: A plain-English summary of solar production and grid import/export.
        """
        try:
            entities = ["sensor.goodwe_pv_power", "sensor.goodwe_grid_power"]
            states = {}
            for eid in entities:
                resp = requests.get(
                    f"{self.valves.ha_url}/api/states/{eid}",
                    headers=self._headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    states[eid] = data.get("state", "unknown")

            pv = states.get("sensor.goodwe_pv_power", "unknown")
            grid = states.get("sensor.goodwe_grid_power", "unknown")

            if pv == "unknown" or grid == "unknown":
                return "Couldn't read solar data from Home Assistant. Check that the GoodWe integration is connected."

            pv_w = float(pv)
            grid_w = float(grid)

            if grid_w < 0:
                surplus = abs(grid_w)
                return (
                    f"Solar is generating {pv_w:.0f} W and exporting {surplus:.0f} W to the grid. "
                    f"Good time to run high-power appliances."
                )
            else:
                return (
                    f"Solar is generating {pv_w:.0f} W and importing {grid_w:.0f} W from the grid. "
                    f"Not enough surplus to run high-power appliances right now."
                )

        except ValueError:
            return "Solar sensor returned a non-numeric value — the GoodWe integration may be unavailable."
        except requests.exceptions.ConnectionError:
            return "Can't reach Home Assistant. Check the HA URL in tool settings."
        except requests.exceptions.Timeout:
            return "Home Assistant didn't respond in time."
        except Exception as e:
            return f"Something went wrong: {e}"
