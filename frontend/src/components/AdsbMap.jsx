import { useEffect, useRef, useState } from 'react'

// Fort Lauderdale area bounds for the plot
const MAP = { latMin: 25.0, latMax: 27.5, lonMin: -81.5, lonMax: -79.0 }

function latToY(lat, h) {
  return h - ((lat - MAP.latMin) / (MAP.latMax - MAP.latMin)) * h
}
function lonToX(lon, w) {
  return ((lon - MAP.lonMin) / (MAP.lonMax - MAP.lonMin)) * w
}

function AircraftPlot({ aircraft }) {
  const W = 480
  const H = 320
  const hasPositions = aircraft.some(a => a.lat != null && a.lon != null)

  return (
    <div
      className="rounded-lg border border-white/10 overflow-hidden"
      style={{ backgroundColor: '#0d1117' }}
    >
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
        <span className="text-xs font-mono text-gray-500">Position Plot — FLL area</span>
        {!hasPositions && (
          <span className="text-xs font-mono text-gray-600">Waiting for CPR position pairs…</span>
        )}
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map(t => (
          <g key={t}>
            <line x1={W * t} y1={0} x2={W * t} y2={H} stroke="#ffffff08" strokeWidth={1} />
            <line x1={0} y1={H * t} x2={W} y2={H * t} stroke="#ffffff08" strokeWidth={1} />
          </g>
        ))}
        {/* Axis labels */}
        <text x={4} y={12} fill="#4b5563" fontSize={9} fontFamily="monospace">
          {MAP.latMax.toFixed(1)}°N
        </text>
        <text x={4} y={H - 4} fill="#4b5563" fontSize={9} fontFamily="monospace">
          {MAP.latMin.toFixed(1)}°N
        </text>
        <text x={4} y={H / 2} fill="#4b5563" fontSize={9} fontFamily="monospace">
          {((MAP.latMax + MAP.latMin) / 2).toFixed(1)}°N
        </text>

        {/* Aircraft markers */}
        {aircraft
          .filter(a => a.lat != null && a.lon != null)
          .map(a => {
            const x = lonToX(a.lon, W)
            const y = latToY(a.lat, H)
            if (x < 0 || x > W || y < 0 || y > H) return null
            return (
              <g key={a.icao}>
                <circle cx={x} cy={y} r={5} fill="#00d2ff" opacity={0.85} />
                <circle cx={x} cy={y} r={9} fill="none" stroke="#00d2ff" strokeWidth={1} opacity={0.3} />
                <text x={x + 10} y={y + 4} fill="#00d2ff" fontSize={9} fontFamily="monospace">
                  {a.callsign || a.icao}
                </text>
                {a.alt != null && (
                  <text x={x + 10} y={y + 14} fill="#6b7280" fontSize={8} fontFamily="monospace">
                    {a.alt.toLocaleString()}ft
                  </text>
                )}
              </g>
            )
          })}

        {/* No-data placeholder */}
        {!hasPositions && (
          <text x={W / 2} y={H / 2} fill="#374151" fontSize={11}
            fontFamily="monospace" textAnchor="middle">
            No position data yet
          </text>
        )}
      </svg>
    </div>
  )
}

function AircraftRow({ ac }) {
  return (
    <tr className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
      <td className="px-4 py-2 text-[#00d2ff] font-mono text-xs font-semibold">{ac.icao}</td>
      <td className="px-4 py-2 text-gray-200 font-mono text-xs">{ac.callsign ?? '—'}</td>
      <td className="px-4 py-2 text-gray-300 font-mono text-xs">
        {ac.alt != null ? `${ac.alt.toLocaleString()} ft` : '—'}
      </td>
      <td className="px-4 py-2 text-gray-300 font-mono text-xs">
        {ac.speed != null ? `${Math.round(ac.speed)} kt` : '—'}
      </td>
      <td className="px-4 py-2 text-gray-300 font-mono text-xs">
        {ac.heading != null ? `${Math.round(ac.heading)}°` : '—'}
      </td>
      <td className="px-4 py-2 font-mono text-xs">
        {ac.lat != null
          ? <span className="text-green-400">{ac.lat.toFixed(4)}, {ac.lon.toFixed(4)}</span>
          : <span className="text-gray-600">No position</span>
        }
      </td>
    </tr>
  )
}

export default function AdsbMap() {
  const [duration, setDuration] = useState(30)
  const [phase, setPhase] = useState('idle')   // idle | capturing | decoding | done | error
  const [aircraft, setAircraft] = useState({}) // keyed by ICAO
  const [msgCount, setMsgCount] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  function start() {
    if (wsRef.current) return
    setAircraft({})
    setMsgCount(0)
    setError(null)
    setPhase('connecting')

    const ws = new WebSocket(`ws://${window.location.host}/ws/adsb`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ duration }))
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)

        if (msg.type === 'status') {
          setPhase(msg.phase)
          if (msg.phase === 'capturing') {
            setStatusMsg(`Capturing ${msg.duration}s at 1090 MHz…`)
          } else if (msg.phase === 'computing_envelope') {
            setStatusMsg(`Computing envelope (${(msg.samples / 1e6).toFixed(0)}M samples)…`)
          } else if (msg.phase === 'decoding') {
            setStatusMsg('Scanning for ADS-B messages…')
          }
        } else if (msg.type === 'aircraft') {
          setAircraft(prev => ({ ...prev, [msg.icao]: msg }))
        } else if (msg.type === 'done') {
          setPhase('done')
          setMsgCount(msg.msg_count)
          setStatusMsg(
            `Done — ${msg.aircraft_count} aircraft, ${msg.msg_count} messages decoded`
          )
          wsRef.current = null
        } else if (msg.type === 'error') {
          setPhase('error')
          setError(msg.message)
          wsRef.current = null
        }
      } catch { /* ignore */ }
    }

    ws.onerror = () => {
      setError('WebSocket error — is the backend running?')
      setPhase('error')
      wsRef.current = null
    }
    ws.onclose = () => {
      if (wsRef.current) {
        wsRef.current = null
        if (phase !== 'done') setPhase('idle')
      }
    }
  }

  function stop() {
    wsRef.current?.close()
    wsRef.current = null
    setPhase('idle')
    setStatusMsg('')
  }

  useEffect(() => () => wsRef.current?.close(), [])

  const aircraftList = Object.values(aircraft).sort((a, b) =>
    (b.alt ?? -Infinity) - (a.alt ?? -Infinity)
  )
  const isRunning = ['connecting', 'capturing', 'computing_envelope', 'decoding'].includes(phase)

  const phaseColor = {
    idle:               'text-gray-500',
    connecting:         'text-yellow-400',
    capturing:          'text-yellow-400 animate-pulse',
    computing_envelope: 'text-yellow-400',
    decoding:           'text-blue-400 animate-pulse',
    done:               'text-green-400',
    error:              'text-red-400',
  }[phase] ?? 'text-gray-500'

  return (
    <div className="space-y-4">

      {/* ── Controls ────────────────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10 flex flex-wrap items-center gap-4"
        style={{ backgroundColor: '#16213e' }}
      >
        <div className="flex items-center gap-2">
          <label className="text-xs font-mono text-gray-500">Duration</label>
          {[15, 30, 60, 120].map(s => (
            <button
              key={s}
              onClick={() => setDuration(s)}
              disabled={isRunning}
              className={`px-3 py-1 text-xs font-mono rounded border transition-colors disabled:opacity-40 ${
                duration === s
                  ? 'border-[#00d2ff]/60 text-[#00d2ff] bg-[#00d2ff]/10'
                  : 'border-white/20 text-gray-400 hover:border-white/40'
              }`}
            >
              {s}s
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className={`text-xs font-mono ${phaseColor}`}>
            {statusMsg || phase}
          </span>
          {isRunning ? (
            <button
              onClick={stop}
              className="px-4 py-1.5 text-xs font-mono rounded border border-red-500/60 text-red-400 hover:bg-red-900/20 transition-colors"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={start}
              className="px-4 py-1.5 text-xs font-mono rounded border border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10 transition-colors"
            >
              Start Tracking
            </button>
          )}
        </div>

        {error && (
          <div className="w-full px-3 py-1.5 bg-red-900/30 border border-red-600/40 rounded text-red-300 text-xs font-mono">
            {error}
          </div>
        )}
      </div>

      {/* ── Stats bar ───────────────────────────────────────────────── */}
      <div className="flex gap-6 px-1 text-xs font-mono text-gray-500">
        <span>Aircraft: <span className="text-gray-300">{aircraftList.length}</span></span>
        <span>With position: <span className="text-green-400">
          {aircraftList.filter(a => a.lat != null).length}
        </span></span>
        {msgCount > 0 && (
          <span>Messages decoded: <span className="text-gray-300">{msgCount}</span></span>
        )}
        <span className="text-gray-600">1090 MHz · Mode S · ADS-B DF17</span>
      </div>

      {/* ── Two-column layout: table + plot ─────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

        {/* Aircraft table */}
        <div
          className="rounded-lg border border-white/10 overflow-hidden"
          style={{ backgroundColor: '#16213e' }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr
                className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-white/10"
                style={{ backgroundColor: '#0f3460' }}
              >
                <th className="px-4 py-3 font-mono">ICAO</th>
                <th className="px-4 py-3 font-mono">Callsign</th>
                <th className="px-4 py-3 font-mono">Alt</th>
                <th className="px-4 py-3 font-mono">Speed</th>
                <th className="px-4 py-3 font-mono">Hdg</th>
                <th className="px-4 py-3 font-mono">Position</th>
              </tr>
            </thead>
            <tbody>
              {aircraftList.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-600 text-xs font-mono">
                    {isRunning ? 'Waiting for aircraft…' : 'No aircraft — press Start Tracking'}
                  </td>
                </tr>
              ) : (
                aircraftList.map(ac => <AircraftRow key={ac.icao} ac={ac} />)
              )}
            </tbody>
          </table>
        </div>

        {/* Position plot */}
        <AircraftPlot aircraft={aircraftList} />
      </div>
    </div>
  )
}
