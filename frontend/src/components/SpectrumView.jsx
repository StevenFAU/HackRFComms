import { useCallback, useEffect, useRef, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'

// Known RF bands to annotate on the spectrum
const BANDS = [
  { start: 88,   end: 108,  label: 'FM',        color: '#a78bfa' },
  { start: 462,  end: 467,  label: 'FRS/GMRS',  color: '#34d399' },
  { start: 902,  end: 928,  label: 'ISM 915',   color: '#f59e0b' },
  { start: 1090, end: 1090, label: 'ADS-B',     color: '#f87171' },
  { start: 2400, end: 2500, label: 'WiFi 2.4G', color: '#60a5fa' },
]

const PRESETS = [
  { label: 'ISM 915',   start: 900,  end: 930  },
  { label: 'FM Radio',  start: 88,   end: 108  },
  { label: 'ADS-B',     start: 1085, end: 1095 },
  { label: 'FRS/GMRS',  start: 460,  end: 470  },
  { label: 'WiFi 2.4G', start: 2400, end: 2500 },
  { label: 'Wide',      start: 400,  end: 1700 },
]

// Waterfall colors: map power (0–1 normalized) to RGB
function powerToColor(norm) {
  // Blue → Cyan → Green → Yellow → Red
  const stops = [
    [0,   [10,  10,  80]],
    [0.3, [0,   80,  180]],
    [0.5, [0,   180, 100]],
    [0.7, [180, 200, 0]],
    [1.0, [220, 30,  10]],
  ]
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (norm >= stops[i][0] && norm <= stops[i + 1][0]) {
      lo = stops[i]
      hi = stops[i + 1]
      break
    }
  }
  const t = lo[0] === hi[0] ? 0 : (norm - lo[0]) / (hi[0] - lo[0])
  const r = Math.round(lo[1][0] + (hi[1][0] - lo[1][0]) * t)
  const g = Math.round(lo[1][1] + (hi[1][1] - lo[1][1]) * t)
  const b = Math.round(lo[1][2] + (hi[1][2] - lo[1][2]) * t)
  return [r, g, b]
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { freq, power } = payload[0].payload
  return (
    <div className="bg-[#0f3460] border border-white/20 rounded px-3 py-2 text-xs font-mono">
      <div className="text-[#00d2ff]">{freq.toFixed(2)} MHz</div>
      <div className="text-gray-300">{power.toFixed(1)} dBm</div>
    </div>
  )
}

export default function SpectrumView() {
  const [startMhz, setStartMhz] = useState(900)
  const [endMhz, setEndMhz]     = useState(930)
  const [fine, setFine]         = useState(false)
  const [scanning, setScanning] = useState(false)
  const [liveMode, setLiveMode] = useState(false)
  const [specData, setSpecData] = useState([])
  const [sweepCount, setSweepCount] = useState(0)
  const [error, setError] = useState(null)
  const [peakFreq, setPeakFreq] = useState(null)

  const canvasRef   = useRef(null)
  const wsRef       = useRef(null)
  const waterfallBuf = useRef([])  // array of {data, dbMin, dbMax} rows

  // ── Waterfall canvas renderer ──────────────────────────────────────────────
  const drawWaterfall = useCallback((newRow) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const W = canvas.width
    const H = canvas.height
    const ROW_H = 2

    // Scroll existing content up by ROW_H pixels
    const imageData = ctx.getImageData(0, ROW_H, W, H - ROW_H)
    ctx.putImageData(imageData, 0, 0)

    // Draw new row at the bottom
    if (!newRow || newRow.length === 0) return
    const powers = newRow.map(d => d.power)
    const dbMin = Math.min(...powers)
    const dbMax = Math.max(...powers)
    const range = dbMax - dbMin || 1

    const rowData = ctx.createImageData(W, ROW_H)
    for (let x = 0; x < W; x++) {
      const idx = Math.floor((x / W) * newRow.length)
      const norm = (newRow[idx].power - dbMin) / range
      const [r, g, b] = powerToColor(norm)
      for (let row = 0; row < ROW_H; row++) {
        const pIdx = (row * W + x) * 4
        rowData.data[pIdx]     = r
        rowData.data[pIdx + 1] = g
        rowData.data[pIdx + 2] = b
        rowData.data[pIdx + 3] = 255
      }
    }
    ctx.putImageData(rowData, 0, H - ROW_H)
  }, [])

  // ── Single scan ────────────────────────────────────────────────────────────
  async function runScan() {
    setScanning(true)
    setError(null)
    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_mhz: startMhz, end_mhz: endMhz, fine }),
      })
      const json = await res.json()
      const data = json.data ?? []
      setSpecData(data)
      setSweepCount(1)
      drawWaterfall(data)
      if (data.length > 0) {
        const peak = data.reduce((a, b) => (a.power > b.power ? a : b))
        setPeakFreq(peak)
      }
    } catch {
      setError('Scan failed — is the backend running?')
    } finally {
      setScanning(false)
    }
  }

  // ── Live mode (WebSocket continuous sweeps) ────────────────────────────────
  function startLive() {
    if (wsRef.current) return
    setError(null)
    setSweepCount(0)
    const ws = new WebSocket(`ws://${window.location.host}/ws/scan`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ start_mhz: startMhz, end_mhz: endMhz, fine }))
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'sweep') {
          setSpecData(msg.data)
          setSweepCount(msg.sweep_n)
          drawWaterfall(msg.data)
          if (msg.data.length > 0) {
            const peak = msg.data.reduce((a, b) => (a.power > b.power ? a : b))
            setPeakFreq(peak)
          }
        }
      } catch { /* ignore malformed */ }
    }
    ws.onerror = () => setError('WebSocket error')
    ws.onclose = () => {
      wsRef.current = null
      setLiveMode(false)
    }
    setLiveMode(true)
  }

  function stopLive() {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }))
      wsRef.current.close()
      wsRef.current = null
    }
    setLiveMode(false)
  }

  // Cleanup on unmount
  useEffect(() => () => { wsRef.current?.close() }, [])

  function applyPreset(preset) {
    setStartMhz(preset.start)
    setEndMhz(preset.end)
    if (liveMode) stopLive()
    setSpecData([])
    setSweepCount(0)
    setPeakFreq(null)
  }

  // Visible band annotations within current range
  const visibleBands = BANDS.filter(b => b.end >= startMhz && b.start <= endMhz)

  return (
    <div className="space-y-4">

      {/* ── Controls ──────────────────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10 space-y-3"
        style={{ backgroundColor: '#16213e' }}
      >
        {/* Preset buttons */}
        <div className="flex flex-wrap gap-2">
          {PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => applyPreset(p)}
              className="px-3 py-1 text-xs font-mono rounded border border-white/20 text-gray-300 hover:border-[#00d2ff]/50 hover:text-[#00d2ff] transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Freq inputs + resolution + action buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1">
            <label className="text-xs font-mono text-gray-500">Start</label>
            <input
              type="number"
              value={startMhz}
              onChange={e => setStartMhz(Number(e.target.value))}
              className="w-24 bg-[#0f3460] border border-white/10 rounded px-2 py-1 text-xs font-mono text-gray-200 focus:outline-none focus:border-[#00d2ff]/50"
            />
            <span className="text-xs font-mono text-gray-500">MHz</span>
          </div>
          <div className="flex items-center gap-1">
            <label className="text-xs font-mono text-gray-500">End</label>
            <input
              type="number"
              value={endMhz}
              onChange={e => setEndMhz(Number(e.target.value))}
              className="w-24 bg-[#0f3460] border border-white/10 rounded px-2 py-1 text-xs font-mono text-gray-200 focus:outline-none focus:border-[#00d2ff]/50"
            />
            <span className="text-xs font-mono text-gray-500">MHz</span>
          </div>
          <button
            onClick={() => setFine(f => !f)}
            className={`px-3 py-1 text-xs font-mono rounded border transition-colors ${
              fine
                ? 'border-[#00d2ff]/60 text-[#00d2ff] bg-[#00d2ff]/10'
                : 'border-white/20 text-gray-400 hover:border-white/40'
            }`}
          >
            {fine ? 'Fine (100 kHz)' : 'Coarse (1 MHz)'}
          </button>

          <div className="ml-auto flex gap-2">
            <button
              onClick={runScan}
              disabled={scanning || liveMode}
              className="px-4 py-1.5 text-xs font-mono rounded border transition-colors border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {scanning ? 'Scanning…' : 'Scan'}
            </button>
            <button
              onClick={liveMode ? stopLive : startLive}
              disabled={scanning}
              className={`px-4 py-1.5 text-xs font-mono rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                liveMode
                  ? 'border-red-500/60 text-red-400 hover:bg-red-900/20'
                  : 'border-green-500/50 text-green-400 hover:bg-green-900/20'
              }`}
            >
              {liveMode ? 'Stop Live' : 'Live'}
            </button>
          </div>
        </div>

        {error && (
          <div className="px-3 py-1.5 bg-red-900/30 border border-red-600/40 rounded text-red-300 text-xs font-mono">
            {error}
          </div>
        )}
      </div>

      {/* ── Stats bar ─────────────────────────────────────────────────── */}
      {(sweepCount > 0 || liveMode) && (
        <div className="flex gap-6 px-1 text-xs font-mono text-gray-500">
          <span>Sweeps: <span className="text-gray-300">{sweepCount}</span></span>
          <span>Bins: <span className="text-gray-300">{specData.length}</span></span>
          {peakFreq && (
            <span>
              Peak: <span className="text-[#00d2ff]">{peakFreq.freq.toFixed(2)} MHz</span>
              {' '}(<span className="text-gray-300">{peakFreq.power.toFixed(1)} dBm</span>)
            </span>
          )}
          {liveMode && (
            <span className="text-green-400 animate-pulse">● LIVE</span>
          )}
        </div>
      )}

      {/* ── Spectrum chart ────────────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10"
        style={{ backgroundColor: '#16213e' }}
      >
        <p className="text-xs font-mono text-gray-500 mb-3">Spectrum</p>
        {specData.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-gray-600 text-sm font-mono">
            {scanning ? 'Capturing…' : 'No data — press Scan or Live'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={specData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#ffffff08" vertical={false} />
              <XAxis
                dataKey="freq"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={v => `${v.toFixed(0)}`}
                tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }}
                label={{ value: 'MHz', position: 'insideBottomRight', offset: -4, fill: '#6b7280', fontSize: 10 }}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }}
                label={{ value: 'dBm', angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 10 }}
                width={45}
              />
              <Tooltip content={<CustomTooltip />} />
              {visibleBands.map(b => (
                <ReferenceLine
                  key={b.label}
                  x={(b.start + b.end) / 2}
                  stroke={b.color}
                  strokeDasharray="3 3"
                  label={{ value: b.label, fill: b.color, fontSize: 9, fontFamily: 'monospace' }}
                />
              ))}
              <Line
                type="monotone"
                dataKey="power"
                stroke="#00d2ff"
                dot={false}
                strokeWidth={1.2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Waterfall ─────────────────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10"
        style={{ backgroundColor: '#16213e' }}
      >
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-mono text-gray-500">Waterfall</p>
          <button
            onClick={() => {
              const canvas = canvasRef.current
              if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
            }}
            className="text-xs font-mono text-gray-600 hover:text-gray-400 transition-colors"
          >
            Clear
          </button>
        </div>
        <canvas
          ref={canvasRef}
          width={900}
          height={160}
          className="w-full rounded"
          style={{ imageRendering: 'pixelated', backgroundColor: '#0a0a1a' }}
        />
        <div className="flex justify-between mt-1 text-xs font-mono text-gray-600">
          <span>{startMhz} MHz</span>
          <span>← time scrolls down</span>
          <span>{endMhz} MHz</span>
        </div>
      </div>
    </div>
  )
}
