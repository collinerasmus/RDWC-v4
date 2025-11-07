#!/usr/bin/env bash
# Active-low relays: HIGH = OFF
PINS=(5 6 13 19 26 16 20 21)
for p in "${PINS[@]}"; do
  # Use raspi-gpio for deterministic one-shot init
  raspi-gpio set $p op dh      # output, drive HIGH
done
