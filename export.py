#!/usr/bin/env python3
"""Unified export script for rider data.

Exports rider data (pollution or sound) from manifest to destination format.

Usage:
    python export.py --type pollution --manifest exports/export-2026-05-24/manifest.json
    python export.py --type sound --manifest exports/export-2026-05-24/manifest.json
    python export.py --type pollution --manifest ... --geocode --city delhi
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


IST = ZoneInfo("Asia/Kolkata")

DEFAULT_OUTPUTS = {
    "pollution": Path("../streetaqi/data/rider"),
    "sound": Path("../soundscape/data/rider"),
}

USER_AGENTS = {
    "pollution": (
        "streetaqi-research/1.0 "
        "(https://github.com/soodoku/streetaqi; gaurav.sood@outlook.com)"
    ),
    "sound": (
        "soundscape-delhi-research/1.0 "
        "(https://github.com/soodoku/soundscape; gaurav.sood@outlook.com)"
    ),
}


def coord_key(lat: float, lng: float) -> str:
    """Generate consistent cache key for coordinates."""
    return f"{lat:.6f},{lng:.6f}"


def reverse_geocode(
    lat: float, lng: float, cache: dict, session: requests.Session
) -> dict | None:
    """Fetch location data for coordinates using Nominatim."""
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
    """Parse note field to extract stop_id and traffic annotations."""
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


def extract_reading_data(log: dict, data_type: str) -> dict:
    """Extract type-specific reading fields from log."""
    if data_type == "pollution":
        return {"pm25": log.get("pm25"), "co": log.get("co")}
    else:
        return {"min_db": log.get("min_db"), "max_db": log.get("max_db"), "status": "ok"}


def convert_reading(
    log: dict,
    data_type: str,
    export_name: str,
    export_dir: Path,
    location: dict | None = None,
) -> dict:
    """Convert a single log to reading format."""
    note_parsed = parse_note(log.get("note"))

    itinerary = None
    if log.get("itinerary_id") and log.get("part"):
        itinerary = f"{log['itinerary_id']}-{log['part']}"

    frame_path = None
    if log.get("image") and log["image"].get("local_path"):
        if data_type == "pollution":
            frame_path = f"data/rider/{export_name}/{log['image']['local_path']}"
        else:
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
        "reading": extract_reading_data(log, data_type),
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


def copy_images(manifest: dict, source_dir: Path, dest_dir: Path) -> int:
    """Copy pollution images to destination directory."""
    pollution_logs = manifest.get("pollution_logs", [])
    copied = 0

    for log in pollution_logs:
        if not log.get("image") or not log["image"].get("local_path"):
            continue

        local_path = log["image"]["local_path"]
        src = source_dir / local_path
        dst = dest_dir / local_path

        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    return copied


def load_location_cache(
    data_type: str,
    source_dir: Path,
    city_dir: Path | None,
    location_cache_path: Path | None,
) -> dict:
    """Load location cache from available sources."""
    cache_sources = []
    if location_cache_path:
        cache_sources.append(location_cache_path)

    if data_type == "pollution" and city_dir:
        cache_sources.append(city_dir / "location_cache.json")

    cache_sources.append(source_dir / "location_cache.json")

    for cache_path in cache_sources:
        if cache_path.exists():
            print(f"Loading location cache from {cache_path}")
            with open(cache_path) as f:
                cache = json.load(f)
            print(f"  Loaded {len(cache)} cached locations")
            return cache

    return {}


def process(
    manifest_path: Path,
    output_dir: Path,
    data_type: str,
    city: str = "delhi",
    geocode: bool = False,
    geocode_delay: float = 1.1,
    location_cache_path: Path | None = None,
) -> None:
    """Export rider data to destination format."""
    source_dir = manifest_path.parent
    export_name = f"export-{datetime.now().strftime('%Y-%m-%d')}"

    if data_type == "pollution":
        export_dir = output_dir / export_name
        city_dir = output_dir / city
        export_dir.mkdir(parents=True, exist_ok=True)
        city_dir.mkdir(parents=True, exist_ok=True)
        readings_output_dir = city_dir
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        export_dir = source_dir
        city_dir = None
        readings_output_dir = output_dir

    print(f"Loading manifest from {manifest_path}")
    with open(manifest_path) as f:
        manifest = json.load(f)

    log_key = "pollution_logs" if data_type == "pollution" else "noise_logs"
    logs = manifest.get(log_key, [])
    print(f"  Found {len(logs)} {data_type} logs")

    if not logs:
        print(f"  No {data_type} logs to export")
        return

    if data_type == "pollution":
        dest_manifest = export_dir / "manifest.json"
        shutil.copy2(manifest_path, dest_manifest)
        print(f"  Copied manifest -> {dest_manifest}")

        print("  Copying pollution images...")
        copied = copy_images(manifest, source_dir, export_dir)
        print(f"  Copied {copied} images -> {export_dir}/images/pollution/")

    location_cache = load_location_cache(
        data_type, source_dir, city_dir, location_cache_path
    )

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENTS[data_type]

    readings = []
    geocoded_count = 0
    for i, log in enumerate(logs):
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
                print(f"\r  Geocoding: {i + 1}/{len(logs)}", end="", flush=True)
                location = reverse_geocode(
                    log["latitude"], log["longitude"], location_cache, session
                )
                geocoded_count += 1
                time.sleep(geocode_delay)

        reading = convert_reading(log, data_type, export_name, export_dir, location)
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

    if data_type == "pollution":
        output["city"] = city
        output["export_name"] = export_name

    output_path = readings_output_dir / "readings.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {output_path}")

    if geocode and geocoded_count > 0:
        cache_path = readings_output_dir / "location_cache.json"
        with open(cache_path, "w") as f:
            json.dump(location_cache, f, indent=2)
        print(f"Wrote {cache_path}")

    if data_type == "pollution":
        print(f"\nTo annotate images with LLM:")
        print(f"  cd ../streetaqi")
        print(f"  streetaqi annotate --images 'data/rider/{export_name}/images/pollution/**/*.jpg'")


def main():
    parser = argparse.ArgumentParser(
        description="Export rider data (pollution or sound)"
    )
    parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=["pollution", "sound"],
        help="Type of data to export: pollution or sound",
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
        default=None,
        help="Output directory (default depends on --type)",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="delhi",
        help="City name for organizing output (default: delhi, pollution only)",
    )
    parser.add_argument(
        "--location-cache",
        type=Path,
        default=None,
        help="Path to location_cache.json (auto-loads from export/dest dir)",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip reverse geocoding (default: geocode enabled)",
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

    output_dir = args.output if args.output else DEFAULT_OUTPUTS[args.type]

    process(
        manifest_path=args.manifest,
        output_dir=output_dir,
        data_type=args.type,
        city=args.city,
        geocode=not args.no_geocode,
        geocode_delay=args.geocode_delay,
        location_cache_path=args.location_cache,
    )


if __name__ == "__main__":
    main()
