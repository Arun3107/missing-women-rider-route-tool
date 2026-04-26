const state = { plan: null, openDay: null, currentTrip: null };
const $ = (s) => document.querySelector(s);
const storageKey = "missingWomenRiderState";

const SUPABASE_URL = "https://rpkmdnqkhfbbvuzlvozs.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwa21kbnFraGZiYnZ1emx2b3pzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc1MDgwMTksImV4cCI6MjA3MzA4NDAxOX0.OZ4anxunvuVAypmoURVxmsPIeQv6aniGh6jRZdIU104";
const SUPABASE_NOISE_TABLE = "noise_logs";

function isSupabaseReady() {
  return (
    SUPABASE_URL &&
    SUPABASE_ANON_KEY &&
    !SUPABASE_URL.includes("PASTE_") &&
    !SUPABASE_ANON_KEY.includes("PASTE_")
  );
}

function loadState() {
  try {
    return (
      JSON.parse(localStorage.getItem(storageKey)) || {
        completed: {},
        noiseLogs: [],
      }
    );
  } catch {
    return { completed: {}, noiseLogs: [] };
  }
}
function saveState(s) {
  localStorage.setItem(storageKey, JSON.stringify(s));
}

async function saveNoiseLogToSupabase(entry) {
  if (!isSupabaseReady()) return { skipped: true };

  const payload = {
    day: entry.day,
    itinerary_id: String(entry.itineraryId),
    part: String(entry.part),
    title: entry.title,
    captured_at: entry.timestamp,
    decibel: entry.decibel ? Number(entry.decibel) : null,
    note: entry.note,
    latitude: entry.lat,
    longitude: entry.lng,
    photo_name: entry.photoName,
    photo_type: entry.photoType,
    photo_data_url: entry.photoDataUrl,
  };

  const res = await fetch(
    `${SUPABASE_URL.replace(/\/$/, "")}/rest/v1/${SUPABASE_NOISE_TABLE}`,
    {
      method: "POST",
      headers: {
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase save failed: ${res.status} ${text}`);
  }

  return { saved: true };
}

function fmt(n) {
  return Number(n || 0).toFixed(1);
}
async function init() {
  const res = await fetch("./plan.json");
  state.plan = await res.json();
  render();
}
function render() {
  const saved = loadState();
  const days = state.plan.days
    .map(
      (d) =>
        `<section class="day-card ${state.openDay === d.day ? "open" : ""}">
    <div class="day-head">
      <div>
        <div class="day-title">Day ${d.day}</div>
        <div class="ids">${d.itineraryIds.length} itineraries</div>
      </div>
      <div class="pill">${d.tripCount} trips</div>
    </div>

    <div class="meta">
      <span>📍 ${d.stopCount}</span>
      <span>🛣 ${fmt(d.googleRoadKm || d.actualDayKm || d.estimatedCoverageKm)} km</span>
      <span>⏱ ${d.googleDurationText || "--"}</span>
    </div>

    <button class="btn toggle" onclick="toggleDay(${d.day})">
      ${state.openDay === d.day ? "Hide Trips" : "View Trips"}
    </button>

    <div class="trips">
      ${d.trips
        .map((t, i) => {
          return `
            <article class="trip">
              <div class="trip-head">
                <div class="trip-title">Trip ${i + 1}</div>
                ${t.endsAtHome ? `<div class="home-badge">Ends Home</div>` : ""}
              </div>

              <div class="trip-sub">${t.title}</div>

              <div class="trip-meta">
                <span>${t.stopCount} stops</span>
                <span>${fmt(t.googleRoadKm || t.routeKm)} km</span>
                ${t.googleDurationText ? `<span>${t.googleDurationText}</span>` : ""}
              </div>

              <div class="actions">
                <a class="btn nav" href="${t.navigationUrl}" target="_blank">Navigate</a>
                <button class="btn noise" onclick='openNoise(${JSON.stringify({ day: d.day, itineraryId: t.itineraryId, part: t.part, title: t.title })})'>Noise</button>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  </section>`,
    )
    .join("");
  document.querySelector("#app").innerHTML =
    `<div class="app"><header class="topbar"><div><h1>Missing Women Rider Routes</h1><p>Fixed 15-day plan - Current Location continues from the rider’s actual position</p></div><button class="export-link" onclick="exportNoiseLogs()">Export Logs</button></header><div class="day-list">${days}</div></div>${noisePanel()}<div id="toast" class="toast hidden"></div>`;
}
function toggleDay(day) {
  state.openDay = state.openDay === day ? null : day;
  render();
}
function noisePanel() {
  return `<div id="noisePanel" class="noise-panel"><h2>Record Noise</h2><div class="small" id="noiseTrip"></div><div class="field"><label>Decibel reading (optional)</label><input id="decibel" inputmode="decimal" placeholder="Example: 72"></div><div class="field"><label>Photo (optional)</label><input id="noisePhoto" type="file" accept="image/*" capture="environment"></div><div class="field"><label>Note (optional)</label><textarea id="note" rows="3" placeholder="Add note"></textarea></div><div class="panel-actions"><button class="btn complete" onclick="closeNoise()">Cancel</button><button class="btn nav" onclick="saveNoise()">Save Log</button></div></div>`;
}
function openNoise(trip) {
  state.currentTrip = trip;
  $("#noisePanel").classList.add("open");
  $("#noiseTrip").textContent = `Day ${trip.day} - ${trip.title}`;
  $("#decibel").value = "";
  $("#note").value = "";
  $("#noisePhoto").value = "";
}
function closeNoise() {
  $("#noisePanel").classList.remove("open");
}

function exportNoiseLogs() {
  const saved = loadState();
  const logs = saved.noiseLogs || [];

  if (!logs.length) {
    showToast("No noise logs to export");
    return;
  }

  const exportData = {
    exportedAt: new Date().toISOString(),
    totalLogs: logs.length,
    logs,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");

  link.href = url;
  link.download = `missing-women-noise-logs-${stamp}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  showToast("Noise logs exported with images");
}
function saveNoise() {
  const trip = state.currentTrip;
  if (!trip) return;

  const photoInput = $("#noisePhoto");
  const photoFile = photoInput?.files?.[0] || null;

  const entry = {
    ...trip,
    timestamp: new Date().toISOString(),
    decibel: $("#decibel").value || null,
    note: $("#note").value || null,
    photoName: photoFile ? photoFile.name : null,
    photoType: photoFile ? photoFile.type : null,
    photoDataUrl: null,
    lat: null,
    lng: null,
  };

  const persist = async () => {
    const s = loadState();
    s.noiseLogs.push(entry);
    saveState(s);

    try {
      await saveNoiseLogToSupabase(entry);
      closeNoise();
      showToast(
        isSupabaseReady()
          ? "Noise log saved to Supabase"
          : "Noise log saved locally",
      );
    } catch (err) {
      console.error(err);
      closeNoise();
      showToast(`Saved locally. Supabase failed: ${err.message.slice(0, 80)}`);
    }
  };

  const persistWithLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          entry.lat = pos.coords.latitude;
          entry.lng = pos.coords.longitude;
          persist();
        },
        () => persist(),
        { enableHighAccuracy: true, timeout: 8000 },
      );
    } else {
      persist();
    }
  };

  if (photoFile) {
    const reader = new FileReader();
    reader.onload = () => {
      entry.photoDataUrl = reader.result;
      persistWithLocation();
    };
    reader.onerror = () => {
      showToast("Photo could not be saved");
    };
    reader.readAsDataURL(photoFile);
  } else {
    persistWithLocation();
  }
}
function showToast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 1800);
}
init().catch((err) => {
  document.querySelector("#app").innerHTML =
    '<div class="loading">Could not load plan.json.</div>';
  console.error(err);
});
