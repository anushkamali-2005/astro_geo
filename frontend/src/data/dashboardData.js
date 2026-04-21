// ── Feature grid cards (DashboardHome.jsx) ──────────────────
// Each card needs: id, icon (key into iconMap), href, accent (Tailwind gradient), title, desc
export const featureCards = [
  {
    id: 'satellites',
    icon: 'Satellite',
    href: '/astronomy',
    accent: 'from-indigo-500/30 to-blue-600/20',
    title: 'Satellite Tracker',
    desc: 'Real-time ISS position, pass predictions, and orbital visualisation for any location.',
  },
  {
    id: 'asteroids',
    icon: 'Orbit',
    href: '/astronomy',
    accent: 'from-amber-500/30 to-orange-600/20',
    title: 'Asteroid Watch',
    desc: 'Near-Earth object alerts powered by NASA CNEOS with AI risk scoring.',
  },
  {
    id: 'earth',
    icon: 'Globe2',
    href: '/earth',
    accent: 'from-emerald-500/30 to-green-600/20',
    title: 'Earth Intelligence',
    desc: 'NDVI change detection, drought monitoring, and crop-yield forecasts from Sentinel-2.',
  },
  {
    id: 'launch',
    icon: 'Rocket',
    href: '/isro',
    accent: 'from-rose-500/30 to-pink-600/20',
    title: 'Launch Predictor',
    desc: 'Go / No-Go predictions for upcoming launches using weather and historical success data.',
  },
]

// ── Recent AI predictions feed (DashboardHome.jsx) ──────────
// Each prediction needs: id, title, status, tone (verified|analyzing|upcoming), meta
export const recentPredictions = [
  {
    id: '1',
    title: 'Asteroid 2024 BX1 — close approach',
    status: 'Verified',
    tone: 'verified',
    meta: 'Risk: Low · Score: 0.12 · Source: NASA CNEOS',
  },
  {
    id: '2',
    title: 'Drought signal — Maharashtra',
    status: 'Analyzing',
    tone: 'analyzing',
    meta: 'Score: 0.52 · Moderate · NASA POWER + Sentinel-2',
  },
]

// ── ISS ticker in hero section (DashboardHome.jsx) ──────────
// Needs: headline, detail
export const issTicker = {
  headline: 'ISS Position',
  detail: 'Over Indian Ocean · Next pass Mumbai: 20:42 IST',
}

// ── Live stats ticker in header bar (DashboardLayout.jsx) ───
// Each stat needs: id, label, value
export const liveStats = [
  { id: 'sat',      label: 'Active Satellites',      value: '52' },
  { id: 'launch',   label: 'Next ISRO Launch',       value: '23d' },
  { id: 'visible',  label: 'Visible Tonight',        value: '3' },
  { id: 'verified', label: 'Predictions Verified',   value: '1,247' },
]

// ── ISRO satellite fleet (IsroMissionCenter.jsx) ────────────
// Each satellite needs: name, type, launch, health
export const isroFleet = [
  { name: 'Cartosat-3',       type: 'EO',            launch: '2019-11-27', health: 96 },
  { name: 'RISAT-2BR1',       type: 'EO',            launch: '2019-12-11', health: 93 },
  { name: 'EOS-04 (RISAT-1A)',type: 'EO',            launch: '2022-02-14', health: 97 },
  { name: 'EOS-06 (Oceansat-3)',type: 'EO',           launch: '2022-11-26', health: 98 },
  { name: 'GSAT-24',          type: 'Communication', launch: '2022-06-23', health: 95 },
  { name: 'NavIC NVS-01',     type: 'Navigation',    launch: '2023-05-29', health: 99 },
  { name: 'Chandrayaan-3',    type: 'Scientific',    launch: '2023-07-14', health: 88 },
  { name: 'Aditya-L1',        type: 'Scientific',    launch: '2023-09-02', health: 99 },
  { name: 'XPoSat',           type: 'Scientific',    launch: '2024-01-01', health: 97 },
  { name: 'INSAT-3DS',        type: 'EO',            launch: '2024-02-17', health: 99 },
]
