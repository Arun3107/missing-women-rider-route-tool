#!/usr/bin/env python3
"""Export rider form data to soundscape readings format.

Transforms exports from this tool into the standard soundscape readings
JSON schema for analysis.

Usage:
    python export_sound.py --manifest exports/2026-05-24/manifest.json --output ../soundscape/output/rider
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


IST = ZoneInfo("Asia/Kolkata")


def coord_key(lat: float, lng: float) -> str:
    """Generate consistent cache key for coordinates."""
    return f"{lat:.6f},{lng:.6f}"


def reverse_geocode(
    lat: float, lng: float, cache: dict, session: requests.Session
) -> dict | None:
    """Fetch location data for coordinates using Nominatim.

    Args:
        lat: Latitude
        lng: Longitude
        cache: Location cache dict (modified in place)
        session: Requests session with headers set

    Returns:
        Dict with address, road_type, road_name or None if lookup fails
    """
    key = coord_key(lat, lng)
    if key in cache:
        return cache[key]

    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?format=jsonv2&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
    )

    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        result = {
            "address": data.get("display_name"),
            "road_type": data.get("type") if data.get("category") == "highway" else None,
            "road_name": data.get("name"),
        }

        if result["address"]:
            cache[key] = result
        return result
    except Exception:
        return None


def parse_note(note: str | None) -> dict:
    """Parse note field to extract stop_id and traffic annotations.

    Args:
        note: Raw note string like "1.2" or "2.1 traffic stop"

    Returns:
        Dictionary with stop_id, is_traffic_stop, is_traffic_jam
    """
    if not note:
        return {
            "stop_id": None,
            "is_traffic_stop": False,
            "is_traffic_jam": False,
        }

    note_lower = note.lower()
    is_traffic_stop = "traffic stop" in note_lower
    is_traffic_jam = "traffic jam" in note_lower

    parts = note.split()
    stop_id = parts[0] if parts else None

    return {
        "stop_id": stop_id,
        "is_traffic_stop": is_traffic_stop,
        "is_traffic_jam": is_traffic_jam,
    }


def convert_timestamp_to_ist(ts_str: str | None) -> str | None:
    """Convert ISO timestamp to IST (India Standard Time)."""
    if not ts_str:
        return None

    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_ist = dt.astimezone(IST)
    return dt_ist.isoformat()


def convert_reading(
    log: dict, export_dir: Path, location: dict | None = None
) -> dict:
    """Convert a single rider log to soundscape reading format."""
    note_parsed = parse_note(log.get("note"))

    itinerary = None
    if log.get("itinerary_id") and log.get("part"):
        itinerary = f"{log['itinerary_id']}-{log['part']}"

    frame_path = None
    if log.get("image") and log["image"].get("local_path"):
        frame_path = str(export_dir / log["image"]["local_path"])

    timestamp_ist = convert_timestamp_to_ist(log.get("captured_at"))

    image_data = None
    if log.get("image"):
        image_data = {
            "local_path": log["image"].get("local_path"),
            "original_name": log["image"].get("original_name"),
            "remote_url": log["image"].get("remote_url"),
        }

    reading = {
        "id": log.get("id"),
        "timestamp": timestamp_ist,
        "timestamp_utc": log.get("captured_at"),
        "gps": {
            "latitude": log.get("latitude"),
            "longitude": log.get("longitude"),
        },
        "reading": {
            "min_db": log.get("min_db"),
            "max_db": log.get("max_db"),
            "status": "ok",
        },
        "frame_path": frame_path,
        "image": image_data,
        "metadata": {
            "day": log.get("day"),
            "itinerary": itinerary,
            "title": log.get("title"),
            "stop_id": note_parsed["stop_id"],
            "is_traffic_stop": note_parsed["is_traffic_stop"],
            "is_traffic_jam": note_parsed["is_traffic_jam"],
            "note_raw": log.get("note"),
        },
    }

    if location:
        reading["metadata"]["address"] = location.get("address")
        reading["metadata"]["road_type"] = location.get("road_type")
        reading["metadata"]["road_name"] = location.get("road_name")

    return reading


def process(
    manifest_path: Path,
    output_dir: Path,
    geocode: bool = False,
    geocode_delay: float = 1.1,
    location_cache_path: Path | None = None,
) -> None:
    """Convert rider manifest to soundscape readings JSON.

    Args:
        manifest_path: Path to rider manifest.json
        output_dir: Output directory (default: output/rider)
        geocode: Whether to reverse geocode coordinates to addresses
        geocode_delay: Delay between geocode requests (Nominatim policy: 1/sec)
        location_cache_path: Path to location_cache.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    export_dir = manifest_path.parent

    print(f"Loading manifest from {manifest_path}")
    with open(manifest_path) as f:
        manifest = json.load(f)

    noise_logs = manifest.get("noise_logs", [])
    print(f"  Found {len(noise_logs)} noise logs")

    location_cache: dict = {}
    if location_cache_path is None:
        default_cache = export_dir / "location_cache.json"
        if default_cache.exists():
            location_cache_path = default_cache
    if location_cache_path:
        print(f"Loading location cache from {location_cache_path}")
        with open(location_cache_path) as f:
            location_cache = json.load(f)
        print(f"  Loaded {len(location_cache)} cached locations")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "soundscape-delhi-research/1.0 "
        "(https://github.com/soodoku/soundscape; gaurav.sood@outlook.com)"
    )

    readings = []
    geocoded_count = 0
    for i, log in enumerate(noise_logs):
        location = None
        if log.get("latitude") and log.get("longitude"):
            key = coord_key(log["latitude"], log["longitude"])
            if key in location_cache:
                cached = location_cache[key]
                if isinstance(cached, str):
                    location = {"address": cached, "road_type": None, "road_name": None}
                else:
                    location = cached
            elif geocode:
                print(f"\r  Geocoding: {i + 1}/{len(noise_logs)}", end="", flush=True)
                location = reverse_geocode(
                    log["latitude"], log["longitude"], location_cache, session
                )
                geocoded_count += 1
                time.sleep(geocode_delay)

        reading = convert_reading(log, export_dir, location)
        readings.append(reading)

    if geocode and geocoded_count > 0:
        print()
        print(f"  Geocoded {geocoded_count} new locations")

    addresses_found = sum(1 for r in readings if r["metadata"].get("address"))
    print(f"  Addresses resolved: {addresses_found}/{len(readings)}")

    traffic_stops = sum(1 for r in readings if r["metadata"]["is_traffic_stop"])
    traffic_jams = sum(1 for r in readings if r["metadata"]["is_traffic_jam"])
    regular = len(readings) - traffic_stops - traffic_jams

    print(f"  Traffic stops: {traffic_stops}")
    print(f"  Traffic jams: {traffic_jams}")
    print(f"  Regular stops: {regular}")

    output = {
        "source": "rider_form",
        "export_date": manifest.get("export_date"),
        "reading_count": len(readings),
        "readings": readings,
    }

    output_path = output_dir / "readings.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {output_path}")

    if geocode:
        cache_path = output_dir / "location_cache.json"
        with open(cache_path, "w") as f:
            json.dump(location_cache, f, indent=2)
        print(f"Wrote {cache_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export rider form data to soundscape readings format"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to rider export manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../soundscape/output/rider"),
        help="Output directory (default: ../soundscape/output/rider)",
    )
    parser.add_argument(
        "--location-cache",
        type=Path,
        default=None,
        help="Path to location_cache.json (auto-loads from export dir)",
    )
    parser.add_argument(
        "--geocode",
        action="store_true",
        help="Reverse geocode coordinates to addresses (slow, ~1 req/sec)",
    )
    parser.add_argument(
        "--geocode-delay",
        type=float,
        default=1.1,
        help="Delay between geocode requests in seconds (default: 1.1)",
    )

    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Error: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    process(
        manifest_path=args.manifest,
        output_dir=args.output,
        geocode=args.geocode,
        geocode_delay=args.geocode_delay,
        location_cache_path=args.location_cache,
    )


if __name__ == "__main__":
    main()
