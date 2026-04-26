const fs = require("fs");

const API_KEY = process.env.GOOGLE_MAPS_API_KEY;
const PLAN_PATH = "./plan.json";

const HOME = {
  lat: 28.6226,
  lng: 77.304,
};

if (!API_KEY) {
  console.error("Missing GOOGLE_MAPS_API_KEY");
  process.exit(1);
}

const plan = JSON.parse(fs.readFileSync(PLAN_PATH, "utf8"));

function latLng(coord) {
  return {
    location: {
      latLng: {
        latitude: coord[0],
        longitude: coord[1],
      },
    },
  };
}

function homeWaypoint() {
  return {
    location: {
      latLng: {
        latitude: HOME.lat,
        longitude: HOME.lng,
      },
    },
  };
}

async function computeRoute(origin, destination, intermediates = []) {
  const res = await fetch(
    "https://routes.googleapis.com/directions/v2:computeRoutes",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
      },
      body: JSON.stringify({
        origin,
        destination,
        intermediates,
        travelMode: "TWO_WHEELER",
        routingPreference: "TRAFFIC_UNAWARE",
        computeAlternativeRoutes: false,
      }),
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Google Routes API error ${res.status}: ${text}`);
  }

  const data = await res.json();
  const route = data.routes?.[0];

  if (!route) {
    throw new Error("No route returned");
  }

  return {
    distanceMeters: route.distanceMeters || 0,
    durationSeconds:
      Number(String(route.duration || "0s").replace("s", "")) || 0,
  };
}

function formatDuration(seconds) {
  const mins = Math.round(seconds / 60);
  const h = Math.floor(mins / 60);
  const m = mins % 60;

  if (h && m) return `${h} hr ${m} min`;
  if (h) return `${h} hr`;
  return `${m} min`;
}

async function calculateDay(day) {
  let dayMeters = 0;
  let daySeconds = 0;

  for (let i = 0; i < day.trips.length; i++) {
    const trip = day.trips[i];
    const coords = trip.coords || [];

    if (!coords.length) continue;

    const isFirstTrip = i === 0;
    const isLastTrip = i === day.trips.length - 1;

    const previousTrip = day.trips[i - 1];
    const previousLastCoord =
      previousTrip?.coords?.[previousTrip.coords.length - 1];

    const origin = isFirstTrip ? homeWaypoint() : latLng(previousLastCoord);

    let destination;
    let intermediates;

    if (isLastTrip) {
      destination = homeWaypoint();
      intermediates = coords.map(latLng);
    } else {
      destination = latLng(coords[coords.length - 1]);
      intermediates = coords.slice(0, -1).map(latLng);
    }

    const result = await computeRoute(origin, destination, intermediates);

    trip.googleDistanceMeters = result.distanceMeters;
    trip.googleRoadKm = +(result.distanceMeters / 1000).toFixed(2);
    trip.googleDurationSeconds = result.durationSeconds;
    trip.googleDurationText = formatDuration(result.durationSeconds);

    dayMeters += result.distanceMeters;
    daySeconds += result.durationSeconds;

    console.log(
      `Day ${day.day}, Trip ${trip.sequenceInDay}: ${trip.googleRoadKm} km, ${trip.googleDurationText}`,
    );
  }

  day.googleDistanceMeters = dayMeters;
  day.googleRoadKm = +(dayMeters / 1000).toFixed(2);
  day.googleDurationSeconds = daySeconds;
  day.googleDurationText = formatDuration(daySeconds);
  day.googleDistanceCalculated = true;

  console.log(
    `Day ${day.day} total: ${day.googleRoadKm} km, ${day.googleDurationText}`,
  );
}

async function main() {
  for (const day of plan.days) {
    await calculateDay(day);
  }

  plan.rules.googleRoadDistancePending = false;
  plan.rules.googleRoadDistanceCalculated = true;

  fs.writeFileSync(PLAN_PATH, JSON.stringify(plan, null, 2));
  console.log("Done. Updated plan.json with Google road distances.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
