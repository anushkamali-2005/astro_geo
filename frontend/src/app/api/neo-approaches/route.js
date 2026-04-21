import { NextResponse } from 'next/server'

export const runtime = 'nodejs'

const BACKEND = process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || 'http://localhost:8000'
const CACHE_TTL_MS = 2 * 60 * 1000

const cache = new Map()

function toNum(value, fallback) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function buildDateRange(days) {
  const start = new Date()
  const end = new Date(start)
  end.setDate(end.getDate() + Math.max(1, Math.min(days, 30)))
  const toISO = (d) => d.toISOString().slice(0, 10)
  return { startDate: toISO(start), endDate: toISO(end) }
}

function normalise(asteroids, minDiameter) {
  return (asteroids || [])
    .map((a) => {
      const diameterM = a?.diameter_km != null ? Number(a.diameter_km) * 1000 : null
      return {
        id: a.id,
        name: a.name,
        date: a.close_approach_date,
        distanceAU: a.distance_au != null ? Number(a.distance_au).toFixed(4) : null,
        diameter: diameterM != null ? Math.round(diameterM) : null,
        magnitude: a.magnitude ?? null,
        velocity: a.velocity_km_s != null ? Number(a.velocity_km_s).toFixed(2) : null,
      }
    })
    .filter((a) => a.diameter == null || a.diameter >= minDiameter)
    .slice(0, 15)
}

export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const days = toNum(searchParams.get('days'), 30)
  const distanceAU = toNum(searchParams.get('distanceAU'), 0.2)
  const minDiameter = toNum(searchParams.get('minDiameter'), 100)
  const cacheKey = `${days}|${distanceAU}|${minDiameter}`

  const hit = cache.get(cacheKey)
  if (hit && Date.now() - hit.ts < CACHE_TTL_MS) {
    return NextResponse.json({ approaches: hit.approaches, source: 'cache' })
  }

  const { startDate, endDate } = buildDateRange(days)
  const qs = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    distance_max_au: String(distanceAU),
    limit: '100',
  })

  try {
    const res = await fetch(`${BACKEND}/api/v1/asteroids/close-approaches?${qs}`, { cache: 'no-store' })
    if (!res.ok) {
      const body = await res.text()
      throw new Error(body || `Asteroid API ${res.status}`)
    }
    const data = await res.json()
    const approaches = normalise(data?.asteroids, minDiameter)
    cache.set(cacheKey, { ts: Date.now(), approaches })
    return NextResponse.json({ approaches, source: data?.source || 'live' })
  } catch (err) {
    if (hit?.approaches?.length) {
      return NextResponse.json({ approaches: hit.approaches, source: 'stale_cache', note: err.message })
    }
    return NextResponse.json({ error: 'Asteroid feed temporarily unavailable', approaches: [] }, { status: 503 })
  }
}
