#!/bin/bash
# Draws markers on a map from the contact list using coords2img
# (https://github.com/fdlamotte/coords2img).
#
# Usage: contact_markers.sh [zoom]   (default zoom: 14)

set -euo pipefail

zoom="${1:-14}"

device=$(meshcorectl get device -o json)
lat=$(echo "$device" | jq -r '.adv_lat')
lon=$(echo "$device" | jq -r '.adv_lon')

meshcorectl get contacts -o json \
  | jq '[.[] | select(.adv_lat != 0.0 or .adv_lon != 0.0)
        | {lat: .adv_lat, lon: .adv_lon, caption: (.name // .public_key[0:8])}]' \
  | coords2img -s --lat "$lat" --lon "$lon" -z "$zoom" -J -m -f1.4 -p google_sat
