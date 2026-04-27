"""
title: Feature Request to Drew
author: Drew
description: >
  Lets Jess send Drew a feature request by just asking in chat.
  Triggers when she says things like "tell Drew I want X" or
  "can you ask Drew to add Y". Sends a push notification via ntfy.
required_open_webui_version: 0.3.17
"""

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        ntfy_url: str = Field(
            default="https://ntfy.sh/your-channel-name-here",
            description=(
                "ntfy channel URL. Change 'your-channel-name-here' to something "
                "long and random — this is your private channel. "
                "Example: https://ntfy.sh/drew-llm-k7x9mq2p"
            ),
        )

    def __init__(self):
        self.valves = self.Valves()

    def send_feature_request(self, feature: str) -> str:
        """
        Send a feature request notification to Drew.
        Use this when the user asks to tell Drew they want a new feature,
        capability, or change to the app. Phrase it naturally in the confirmation.
        :param feature: A clear description of what the user wants added or changed.
        :return: Confirmation that the request was sent, or an error message.
        """
        try:
            response = requests.post(
                self.valves.ntfy_url,
                data=feature.encode("utf-8"),
                headers={
                    "Title": "Feature request from Jess",
                    "Priority": "default",
                    "Tags": "bulb",
                },
                timeout=5,
            )
            if response.status_code == 200:
                return "Sent. Drew will get a notification."
            return f"The notification didn't go through (status {response.status_code}). Try again, or let Drew know directly."
        except requests.exceptions.Timeout:
            return "Timed out trying to reach the notification service. Try again in a moment."
        except Exception as e:
            return f"Something went wrong: {e}"
