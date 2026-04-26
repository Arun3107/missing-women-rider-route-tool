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
    min_db: entry.minDb,
    max_db: entry.maxDb,
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

async function fetchNoiseLogsFromSupabase() {
  if (!isSupabaseReady()) return null;

  const res = await fetch(
    `${SUPABASE_URL.replace(/\/$/, "")}/rest/v1/${SUPABASE_NOISE_TABLE}?select=*&order=captured_at.desc`,
    {
      method: "GET",
      headers: {
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      },
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase export failed: ${res.status} ${text}`);
  }

  const rows = await res.json();

  return rows.map((row) => ({
    day: row.day,
    itineraryId: row.itinerary_id,
    part: row.part,
    title: row.title,
    timestamp: row.captured_at,
    minDb: row.min_db,
    maxDb: row.max_db,
    note: row.note,
    lat: row.latitude,
    lng: row.longitude,
    photoName: row.photo_name,
    photoType: row.photo_type,
    photoDataUrl: row.photo_data_url,
  }));
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
    `<div class="app"><header class="topbar"><div><h1>Missing Women Rider Routes</h1><p>Fixed 15-day plan - Current Location continues from the rider’s actual position</p></div><button class="export-link" onclick="exportNoiseLogs()">Export Report</button></header><div class="day-list">${days}</div></div>${noisePanel()}<div id="toast" class="toast hidden"></div>`;
}
function toggleDay(day) {
  state.openDay = state.openDay === day ? null : day;
  render();
}
function noisePanel() {
  return `<div id="noisePanel" class="noise-panel"><h2>Record Noise</h2><div class="small" id="noiseTrip"></div><div class="field"><label>Min dB (required)</label><input id="minDb" inputmode="decimal" placeholder="Example: 60"></div><div class="field"><label>Max dB (required)</label><input id="maxDb" inputmode="decimal" placeholder="Example: 85"></div><div class="field"><label>Photo (optional)</label><input id="noisePhoto" type="file" accept="image/*" capture="environment"></div><div class="field"><label>Note (optional)</label><textarea id="note" rows="3" placeholder="Add note"></textarea></div><div class="panel-actions"><button class="btn complete" onclick="closeNoise()">Cancel</button><button class="btn nav" onclick="saveNoise()">Save Log</button></div></div>`;
}
function openNoise(trip) {
  state.currentTrip = trip;
  $("#noisePanel").classList.add("open");
  $("#noiseTrip").textContent = `Day ${trip.day} - ${trip.title}`;
  $("#minDb").value = "";
  $("#maxDb").value = "";
  $("#note").value = "";
  $("#noisePhoto").value = "";
}
function closeNoise() {
  $("#noisePanel").classList.remove("open");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function exportNoiseLogs() {
  let logs = [];

  try {
    logs = (await fetchNoiseLogsFromSupabase()) || [];
  } catch (err) {
    console.error(err);
    showToast(`Supabase export failed: ${err.message.slice(0, 80)}`);
    return;
  }

  if (!logs.length && !isSupabaseReady()) {
    const saved = loadState();
    logs = saved.noiseLogs || [];
  }

  if (!logs.length) {
    showToast("No Supabase noise logs to export");
    return;
  }

  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const rows = logs
    .map((log, index) => {
      const imageBlock = log.photoDataUrl
        ? `<a href="${log.photoDataUrl}" download="noise-photo-${index + 1}.jpg"><img src="${log.photoDataUrl}" alt="Noise photo ${index + 1}" /></a>`
        : `<span class="muted">No photo</span>`;

      return `
        <tr>
          <td>${index + 1}</td>
          <td>Day ${escapeHtml(log.day)}</td>
          <td>${escapeHtml(log.title)}</td>
          <td>${escapeHtml(log.captured_at || log.timestamp)}</td>
          <td>${escapeHtml(log.minDb || "")}</td>
          <td>${escapeHtml(log.maxDb || "")}</td>
          <td>${escapeHtml(log.lat || "")}</td>
          <td>${escapeHtml(log.lng || "")}</td>
          <td>${escapeHtml(log.note || "")}</td>
          <td>${imageBlock}</td>
        </tr>`;
    })
    .join("");

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Missing Women Noise Logs</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; color: #111827; background: #f8fafc; }
    h1 { margin: 0 0 6px; font-size: 24px; }
    p { margin: 0 0 18px; color: #6b7280; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 14px; overflow: hidden; box-shadow: 0 8px 24px rgba(15,23,42,0.08); }
    th, td { border-bottom: 1px solid #e5e7eb; padding: 10px; vertical-align: top; text-align: left; font-size: 13px; }
    th { background: #0f172a; color: white; font-size: 12px; }
    img { width: 160px; max-width: 40vw; border-radius: 10px; border: 1px solid #e5e7eb; display: block; }
    .muted { color: #9ca3af; }
    .note { max-width: 220px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Missing Women Noise Logs</h1>
  <p>Exported ${escapeHtml(new Date().toLocaleString())} · ${logs.length} Supabase logs · Photos are embedded and can be opened or saved from this file.</p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Day</th>
        <th>Trip</th>
        <th>Timestamp</th>
        <th>Min dB</th>
        <th>Max dB</th>
        <th>Lat</th>
        <th>Lng</th>
        <th>Note</th>
        <th>Photo</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `missing-women-noise-report-${stamp}.html`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  showToast("Report exported with photos");
}
function saveNoise() {
  const trip = state.currentTrip;
  if (!trip) return;

  const photoInput = $("#noisePhoto");
  const photoFile = photoInput?.files?.[0] || null;

  const minDb = $("#minDb").value;
  const maxDb = $("#maxDb").value;

  if (!minDb || !maxDb) {
    showToast("Enter min and max dB");
    return;
  }

  const entry = {
    ...trip,
    timestamp: new Date().toISOString(),
    minDb: Number(minDb),
    maxDb: Number(maxDb),
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
