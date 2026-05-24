#!/usr/bin/env python3
"""
Export noise and pollution data from Supabase with local image downloads.

Creates a structured export with:
- manifest.json: Complete metadata with local image paths
- noise_logs.csv: Tabular noise data
- pollution_logs.csv: Tabular pollution data
- images/: Organized by type and day
"""

import csv
import json
import os
import re
from datetime import datetime, timezone

import requests

SUPABASE_URL = "https://rpkmdnqkhfbbvuzlvozs.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwa21kbnFraGZiYnZ1emx2b3pzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc1MDgwMTksImV4cCI6MjA3MzA4NDAxOX0."
    "OZ4anxunvuVAypmoURVxmsPIeQv6aniGh6jRZdIU104"
)
NOISE_TABLE = "noise_logs"
POLLUTION_TABLE = "pollution_logs"


def sanitize_filename(title: str) -> str:
    """Convert title to safe filename."""
    safe = re.sub(r"[^a-z0-9]+", "-", (title or "untitled").lower())
    return safe.strip("-")[:40] or "untitled"


def fetch_table(table_name: str) -> list[dict]:
    """Fetch all records from a Supabase table."""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=*&order=captured_at.desc"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def download_image(url: str, dest_path: str) -> bool:
    """Download an image from URL to local path."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  Failed to download {url}: {e}")
        return False


def process_logs(
    logs: list[dict], log_type: str, images_base: str
) -> tuple[list[dict], int]:
    """Process logs, download images, and return enriched records."""
    processed = []
    images_downloaded = 0
    total_with_photos = sum(1 for x in logs if x.get("photo_url"))

    day_counters: dict[int, int] = {}

    for log in logs:
        day = log.get("day", 0)
        if day not in day_counters:
            day_counters[day] = 0
        day_counters[day] += 1
        seq = day_counters[day]

        record = {
            "id": log.get("id"),
            "day": day,
            "itinerary_id": log.get("itinerary_id"),
            "part": log.get("part"),
            "title": log.get("title"),
            "captured_at": log.get("captured_at"),
            "latitude": log.get("latitude"),
            "longitude": log.get("longitude"),
            "note": log.get("note"),
        }

        if log_type == "noise":
            record["min_db"] = log.get("min_db")
            record["max_db"] = log.get("max_db")
        else:
            record["pm25"] = log.get("pm25")
            record["co"] = log.get("co")

        photo_url = log.get("photo_url")
        photo_name = log.get("photo_name")

        if photo_url:
            safe_title = sanitize_filename(log.get("title") or "untitled")
            filename = f"{seq:03d}_{safe_title}.jpg"
            day_folder = f"day-{day:02d}"
            local_path = f"images/{log_type}/{day_folder}/{filename}"
            full_path = os.path.join(images_base, log_type, day_folder, filename)

            print(
                f"\r  Downloading {log_type} images: {images_downloaded + 1}/{total_with_photos}",
                end="",
                flush=True,
            )
            if download_image(photo_url, full_path):
                images_downloaded += 1
                record["image"] = {
                    "local_path": local_path,
                    "original_name": photo_name,
                    "remote_url": photo_url,
                }
            else:
                record["image"] = {
                    "local_path": None,
                    "original_name": photo_name,
                    "remote_url": photo_url,
                    "download_failed": True,
                }
        else:
            record["image"] = None

        processed.append(record)

    if total_with_photos > 0:
        print()
    return processed, images_downloaded


def write_csv(logs: list[dict], filepath: str, log_type: str) -> None:
    """Write logs to CSV file."""
    if log_type == "noise":
        fieldnames = [
            "id",
            "day",
            "itinerary_id",
            "part",
            "title",
            "captured_at",
            "min_db",
            "max_db",
            "latitude",
            "longitude",
            "note",
            "local_image_path",
            "remote_image_url",
        ]
    else:
        fieldnames = [
            "id",
            "day",
            "itinerary_id",
            "part",
            "title",
            "captured_at",
            "pm25",
            "co",
            "latitude",
            "longitude",
            "note",
            "local_image_path",
            "remote_image_url",
        ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for log in logs:
            row = {k: log.get(k) for k in fieldnames if k in log}
            if log.get("image"):
                row["local_image_path"] = log["image"].get("local_path")
                row["remote_image_url"] = log["image"].get("remote_url")
            else:
                row["local_image_path"] = None
                row["remote_image_url"] = None
            writer.writerow(row)


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    export_dir = os.path.join("exports", f"export-{timestamp}")
    images_dir = os.path.join(export_dir, "images")

    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(os.path.join(images_dir, "noise"), exist_ok=True)
    os.makedirs(os.path.join(images_dir, "pollution"), exist_ok=True)

    print(f"Exporting to: {export_dir}")
    print()

    print("Fetching noise logs...")
    noise_raw = fetch_table(NOISE_TABLE)
    print(f"  Found {len(noise_raw)} noise logs")

    print("Fetching pollution logs...")
    pollution_raw = fetch_table(POLLUTION_TABLE)
    print(f"  Found {len(pollution_raw)} pollution logs")
    print()

    print("Processing noise logs and downloading images...")
    noise_logs, noise_images = process_logs(noise_raw, "noise", images_dir)
    print(f"  Downloaded {noise_images} noise images")

    print("Processing pollution logs and downloading images...")
    pollution_logs, pollution_images = process_logs(pollution_raw, "pollution", images_dir)
    print(f"  Downloaded {pollution_images} pollution images")
    print()

    manifest = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "total_noise_logs": len(noise_logs),
        "total_pollution_logs": len(pollution_logs),
        "noise_logs": noise_logs,
        "pollution_logs": pollution_logs,
    }

    manifest_path = os.path.join(export_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Wrote manifest.json")

    noise_csv_path = os.path.join(export_dir, "noise_logs.csv")
    write_csv(noise_logs, noise_csv_path, "noise")
    print(f"Wrote noise_logs.csv")

    pollution_csv_path = os.path.join(export_dir, "pollution_logs.csv")
    write_csv(pollution_logs, pollution_csv_path, "pollution")
    print(f"Wrote pollution_logs.csv")

    print()
    print("=" * 50)
    print("EXPORT COMPLETE")
    print("=" * 50)
    print(f"Output directory: {export_dir}")
    print(f"Noise logs: {len(noise_logs)}")
    print(f"Pollution logs: {len(pollution_logs)}")
    print(f"Images downloaded: {noise_images + pollution_images}")


if __name__ == "__main__":
    main()
