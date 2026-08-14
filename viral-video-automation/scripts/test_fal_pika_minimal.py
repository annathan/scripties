#!/usr/bin/env python3
"""Standalone, isolated test of fal.ai's Pika API -- no pipeline code
involved at all. Copies the exact example from fal.ai's own docs page for
fal-ai/pika/v2.2/text-to-video. Run this directly to answer one question:
does ANYTHING succeed with your fal.ai account/key, even their own
textbook example?

Usage:
    set FAL_KEY=your-real-key-here
    python scripts\\test_fal_pika_minimal.py
"""
import os

import fal_client

if not os.environ.get("FAL_KEY"):
    raise SystemExit("FAL_KEY is not set in this shell. Run: set FAL_KEY=your-real-key-here")


def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(log["message"])


result = fal_client.subscribe(
    "fal-ai/pika/v2.2/text-to-video",
    arguments={
        "prompt": "Large elegant white poodle standing proudly on the deck of a white yacht, wearing "
        "oversized glamorous sunglasses and a luxurious silk Gucci-style scarf tied around its neck, "
        "layered pearl necklaces draped across its chest, photographed from outside the yacht at a low "
        "upward angle, clear blue sky background, strong midday sunlight, washed-out faded tones, "
        "slightly overexposed 2000s fashion editorial aesthetic, cinematic analog film texture, playful "
        "luxury mood, glossy magazine style, bright harsh light and soft shadows, stylish and extravagant "
        "atmosphere. camera slow orbit and dolly in"
    },
    with_logs=True,
    on_queue_update=on_queue_update,
)
print(result)
