import { useEffect, useRef, useState } from 'react'

// ── Canvas drawing helpers ─────────────────────────────────────────────────

// Same colormap as SpectrumView waterfall
function normToRgb(norm) {
  const stops = [
    [0,   [10,  10,  80]],
    [0.3, [0,   80,  180]],
    [0.5, [0,   180, 100]],
    [0.7, [180, 200, 0]],
    [1.0, [220, 30,  10]],
  ]
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (norm >= stops[i][0] && norm <= stops[i + 1][0]) { lo = stops[i]; hi = stops[i + 1]; break }
  }
  const t = lo[0] === hi[0] ? 0 : (norm - lo[0]) / (hi[0] - lo[0])
  return [
    Math.round(lo[1][0] + (hi[1][0] - lo[1][0]) * t),
    Math.round(lo[1][1] + (hi[1][1] - lo[1][1]) * t),
    Math.round(lo[1][2] + (hi[1][2] - lo[1][2]) * t),
  ]
}

function SpectrogramCanvas({ data }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const { data: flat, time_bins: W, freq_bins: H,
            duration_s, carrier_khz, freq_min_khz, freq_max_khz } = data

    const canvas = canvasRef.current
    canvas.width  = W
    canvas.height = H
    const ctx = canvas.getContext('2d')
    const img = ctx.createImageData(W, H)

    for (let t = 0; t < W; t++) {
      for (let f = 0; f < H; f++) {
        const norm = flat[t * H + f] ?? 0
        const [r, g, b] = normToRgb(norm)
        // flip freq axis (low freq at bottom)
        const row = H - 1 - f
        const idx = (row * W + t) * 4
        img.data[idx]     = r
        img.data[idx + 1] = g
        img.data[idx + 2] = b
        img.data[idx + 3] = 255
      }
    }
    ctx.putImageData(img, 0, 0)

    // Carrier line
    const carrierNorm = (carrier_khz - freq_min_khz) / (freq_max_khz - freq_min_khz)
    const carrierY = Math.round((1 - carrierNorm) * H)
    ctx.strokeStyle = 'rgba(0,210,255,0.7)'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(0, carrierY)
    ctx.lineTo(W, carrierY)
    ctx.stroke()
  }, [data])

  if (!data) return null
  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded"
      style={{ imageRendering: 'pixelated', backgroundColor: '#0a0a1a' }}
    />
  )
}

function EnvelopeCanvas({ envelope }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!envelope || !canvasRef.current) return
    const { t, v, threshold_norm } = envelope
    const canvas = canvasRef.current
    const W = canvas.width
    const H = canvas.height
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, W, H)

    const xOf = i => (i / (v.length - 1)) * W
    const yOf = val => H - val * H * 0.9 - 4

    // Fill
    ctx.beginPath()
    ctx.moveTo(0, H)
    v.forEach((val, i) => ctx.lineTo(xOf(i), yOf(val)))
    ctx.lineTo(W, H)
    ctx.closePath()
    ctx.fillStyle = 'rgba(255,102,0,0.25)'
    ctx.fill()

    // Line
    ctx.beginPath()
    v.forEach((val, i) => i === 0 ? ctx.moveTo(0, yOf(val)) : ctx.lineTo(xOf(i), yOf(val)))
    ctx.strokeStyle = '#ff6600'
    ctx.lineWidth = 1.2
    ctx.stroke()

    // Threshold
    const ty = yOf(threshold_norm)
    ctx.setLineDash([6, 4])
    ctx.strokeStyle = '#00d2ff'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, ty); ctx.lineTo(W, ty)
    ctx.stroke()
    ctx.setLineDash([])

    // Label
    ctx.font = '10px monospace'
    ctx.fillStyle = '#00d2ff'
    ctx.fillText('threshold', 4, ty - 4)
  }, [envelope])

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={120}
      className="w-full rounded"
      style={{ backgroundColor: '#0d1117' }}
    />
  )
}

function OokZoomCanvas({ ook }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!ook || !canvasRef.current) return
    const { t_ms, v, threshold_norm, preamble_end_ms, sync_end_ms, total_ms } = ook
    const canvas = canvasRef.current
    const W = canvas.width
    const H = canvas.height
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, W, H)

    const xOf = ms => (ms / total_ms) * W
    const yOf = val => H - val * H * 0.85 - 8

    // Section backgrounds
    ctx.fillStyle = 'rgba(255,255,0,0.04)'
    ctx.fillRect(0, 0, xOf(preamble_end_ms), H)
    ctx.fillStyle = 'rgba(0,210,255,0.04)'
    ctx.fillRect(xOf(preamble_end_ms), 0, xOf(sync_end_ms) - xOf(preamble_end_ms), H)

    // ON/OFF fill
    v.forEach((val, i) => {
      const x0 = xOf(t_ms[i])
      const x1 = i < v.length - 1 ? xOf(t_ms[i + 1]) : W
      const isHigh = val > threshold_norm
      ctx.fillStyle = isHigh ? 'rgba(0,200,80,0.35)' : 'rgba(220,30,30,0.12)'
      ctx.fillRect(x0, 0, x1 - x0, H)
    })

    // Line
    ctx.beginPath()
    v.forEach((val, i) => {
      const x = xOf(t_ms[i])
      i === 0 ? ctx.moveTo(x, yOf(val)) : ctx.lineTo(x, yOf(val))
    })
    ctx.strokeStyle = '#ff6600'
    ctx.lineWidth = 1.2
    ctx.stroke()

    // Threshold
    const ty = yOf(threshold_norm)
    ctx.setLineDash([5, 4])
    ctx.strokeStyle = '#00d2ff'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, ty); ctx.lineTo(W, ty); ctx.stroke()
    ctx.setLineDash([])

    // Section labels
    ctx.font = '9px monospace'
    ctx.fillStyle = '#888'
    ctx.fillText('PREAMBLE', 4, 12)
    ctx.fillStyle = '#00d2ff'
    ctx.fillText('SYNC', xOf(preamble_end_ms) + 4, 12)
    ctx.fillStyle = '#aaa'
    ctx.fillText('DATA + CRC', xOf(sync_end_ms) + 4, 12)
  }, [ook])

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={130}
      className="w-full rounded"
      style={{ backgroundColor: '#0d1117' }}
    />
  )
}

function BitsCanvas({ bits }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!bits || !canvasRef.current) return
    const { data: bdata, frame_sections: sec } = bits
    if (!bdata || bdata.length === 0) return

    const canvas = canvasRef.current
    const W = canvas.width
    const H = canvas.height
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, W, H)

    const n = bdata.length
    const barW = W / n
    const barH = H * 0.65
    const barY = H * 0.2

    // Section backgrounds
    const sectionX = (idx) => (idx / n) * W
    ctx.fillStyle = 'rgba(255,255,0,0.06)'; ctx.fillRect(0, barY - 4, sectionX(sec.preamble_end), barH + 8)
    ctx.fillStyle = 'rgba(0,210,255,0.06)'; ctx.fillRect(sectionX(sec.preamble_end), barY - 4, sectionX(sec.sync_end) - sectionX(sec.preamble_end), barH + 8)
    ctx.fillStyle = 'rgba(200,0,200,0.05)'; ctx.fillRect(sectionX(sec.sync_end), barY - 4, sectionX(sec.len_end) - sectionX(sec.sync_end), barH + 8)

    // Bars
    bdata.forEach((bit, i) => {
      ctx.fillStyle = bit ? '#00cc44' : '#222'
      ctx.fillRect(i * barW, barY, barW - 0.5, barH)
    })

    // Section labels
    ctx.font = '9px monospace'
    const labelY = barY - 6
    ctx.fillStyle = '#888'
    ctx.fillText('PREAMBLE', sectionX(0) + 2, labelY)
    ctx.fillStyle = '#00d2ff'
    ctx.fillText('SYNC', sectionX(sec.preamble_end) + 2, labelY)
    ctx.fillStyle = '#c084fc'
    ctx.fillText('LEN', sectionX(sec.sync_end) + 2, labelY)
    ctx.fillStyle = '#aaa'
    ctx.fillText('PAYLOAD + CRC', sectionX(sec.len_end) + 2, labelY)

    // Bit count label
    ctx.fillStyle = '#4b5563'
    ctx.font = '10px monospace'
    ctx.fillText(`${n} bits`, W - 55, H - 4)
  }, [bits])

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={90}
      className="w-full rounded"
      style={{ backgroundColor: '#0d1117' }}
    />
  )
}

function TimelinePanel({ timeline }) {
  if (!timeline?.available) return null
  const { sender, receiver, turnaround_s, total_s } = timeline
  const allPhases = [...(sender?.phases ?? []), ...(receiver?.phases ?? [])]
  if (allPhases.length === 0) return null

  const scale = W => `${(W / total_s) * 100}%`
  const offset = s => `${(s / total_s) * 100}%`

  return (
    <div
      className="rounded-lg p-4 border border-white/10 space-y-3"
      style={{ backgroundColor: '#16213e' }}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-mono text-gray-400">Protocol Timeline</p>
        {turnaround_s != null && (
          <span className="text-xs font-mono text-[#00d2ff]">
            Turnaround: {turnaround_s}s
          </span>
        )}
      </div>

      {/* Sender row */}
      {sender?.phases?.length > 0 && (
        <div className="space-y-1">
          <span className="text-xs font-mono text-gray-500">SENDER (Dev 0)</span>
          <div className="relative h-6 rounded overflow-hidden" style={{ backgroundColor: '#0d1117' }}>
            {sender.phases.map((ph, i) => (
              <div
                key={i}
                className="absolute h-full flex items-center px-1 text-xs font-mono text-white overflow-hidden"
                style={{
                  left: offset(ph.start),
                  width: scale(ph.end - ph.start),
                  backgroundColor: ph.color + 'cc',
                  minWidth: 4,
                }}
              >
                <span className="truncate" style={{ fontSize: 9 }}>{ph.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Receiver row */}
      {receiver?.phases?.length > 0 && (
        <div className="space-y-1">
          <span className="text-xs font-mono text-gray-500">RECEIVER (Dev 1)</span>
          <div className="relative h-6 rounded overflow-hidden" style={{ backgroundColor: '#0d1117' }}>
            {receiver.phases.map((ph, i) => (
              <div
                key={i}
                className="absolute h-full flex items-center px-1 text-xs font-mono text-white overflow-hidden"
                style={{
                  left: offset(ph.start),
                  width: scale(ph.end - ph.start),
                  backgroundColor: ph.color + 'cc',
                  minWidth: 4,
                }}
              >
                <span className="truncate" style={{ fontSize: 9 }}>{ph.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Time axis */}
      <div className="flex justify-between text-xs font-mono text-gray-600 px-0.5">
        <span>0s</span>
        <span>{(total_s / 2).toFixed(1)}s</span>
        <span>{total_s}s</span>
      </div>
    </div>
  )
}

function Panel({ title, subtitle, children }) {
  return (
    <div
      className="rounded-lg p-4 border border-white/10 space-y-2"
      style={{ backgroundColor: '#16213e' }}
    >
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-mono text-gray-400">{title}</p>
        {subtitle && <p className="text-xs font-mono text-gray-600">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export default function SignalAnalysis() {
  const [files, setFiles]       = useState([])
  const [selected, setSelected] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  // Load file list + timeline on mount
  useEffect(() => {
    fetch('/api/signals/list')
      .then(r => r.json())
      .then(d => {
        setFiles(d.files ?? [])
        if (d.files?.length > 0) setSelected(d.files[0].name)
      })
      .catch(() => setError('Could not load file list'))

    fetch('/api/signals/timeline')
      .then(r => r.json())
      .then(d => setTimeline(d.available ? d : null))
      .catch(() => {})
  }, [])

  async function analyze() {
    if (!selected) return
    setLoading(true)
    setError(null)
    setAnalysis(null)
    try {
      const res = await fetch('/api/signals/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selected }),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setAnalysis(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">

      {/* ── File picker ────────────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10 flex flex-wrap items-center gap-3"
        style={{ backgroundColor: '#16213e' }}
      >
        <span className="text-xs font-mono text-gray-500">IQ File</span>
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          className="flex-1 min-w-[200px] bg-[#0f3460] border border-white/10 rounded px-3 py-1.5 text-xs font-mono text-gray-200 focus:outline-none focus:border-[#00d2ff]/50"
        >
          {files.length === 0 && <option value="">No IQ files found</option>}
          {files.map(f => (
            <option key={f.name} value={f.name}>
              {f.name} ({f.size_mb} MB)
            </option>
          ))}
        </select>

        <button
          onClick={analyze}
          disabled={loading || !selected}
          className="px-4 py-1.5 text-xs font-mono rounded border border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>

        {error && (
          <div className="w-full px-3 py-1.5 bg-red-900/30 border border-red-600/40 rounded text-red-300 text-xs font-mono">
            {error}
          </div>
        )}
      </div>

      {/* ── Stats row (once analyzed) ──────────────────────────────── */}
      {analysis && (
        <div className="flex flex-wrap gap-6 px-1 text-xs font-mono text-gray-500">
          <span>Duration: <span className="text-gray-300">{analysis.duration_s}s</span></span>
          <span>Sample rate: <span className="text-gray-300">{(analysis.sample_rate / 1e6).toFixed(0)} MS/s</span></span>
          <span>Carrier: <span className="text-[#00d2ff]">+{analysis.carrier_khz} kHz offset</span></span>
          <span>Burst: <span className="text-gray-300">{analysis.burst_start_s}s – {analysis.burst_end_s}s</span></span>
          {analysis.bits?.n_bits > 0 && (
            <span>Decoded: <span className="text-green-400">{analysis.bits.n_bits} bits</span>
              <span className="text-gray-600"> (preamble match: {analysis.bits.preamble_score}/64)</span>
            </span>
          )}
        </div>
      )}

      {/* ── 4-panel display ───────────────────────────────────────── */}
      {analysis && (
        <div className="space-y-4">

          <Panel
            title="Spectrogram — full capture (first 1s)"
            subtitle={`${analysis.spectrogram.freq_min_khz} – ${analysis.spectrogram.freq_max_khz} kHz offset · cyan dashed = our carrier`}
          >
            <SpectrogramCanvas data={analysis.spectrogram} />
            <div className="flex justify-between text-xs font-mono text-gray-600 mt-1">
              <span>0s</span>
              <span>← time →</span>
              <span>{analysis.spectrogram.duration_s}s</span>
            </div>
          </Panel>

          <Panel
            title="Demodulated envelope — where is the signal?"
            subtitle={`${analysis.duration_s}s capture · cyan = detection threshold`}
          >
            <EnvelopeCanvas envelope={analysis.envelope} />
            <div className="flex justify-between text-xs font-mono text-gray-600 mt-1">
              <span>0s</span>
              <span>{(analysis.duration_s / 2).toFixed(1)}s</span>
              <span>{analysis.duration_s}s</span>
            </div>
          </Panel>

          <Panel
            title="OOK zoom — one frame at burst start"
            subtitle="green = carrier ON (bit 1)  ·  red = carrier OFF (bit 0)"
          >
            <OokZoomCanvas ook={analysis.ook_zoom} />
            <div className="flex justify-between text-xs font-mono text-gray-600 mt-1">
              <span>0 ms</span>
              <span>{(analysis.ook_zoom.total_ms / 2).toFixed(1)} ms</span>
              <span>{analysis.ook_zoom.total_ms.toFixed(1)} ms</span>
            </div>
          </Panel>

          <Panel
            title="Decoded bits — one frame"
            subtitle={
              analysis.bits?.n_bits > 0
                ? `${analysis.bits.n_bits} bits · green = 1 (carrier ON) · dark = 0 (carrier OFF)`
                : 'No valid frame found'
            }
          >
            {analysis.bits?.n_bits > 0
              ? <BitsCanvas bits={analysis.bits} />
              : <div className="text-gray-600 text-xs font-mono py-4 text-center">
                  Could not decode a frame — try a cleaner capture
                </div>
            }
          </Panel>
        </div>
      )}

      {/* ── Protocol timeline ─────────────────────────────────────── */}
      {timeline && <TimelinePanel timeline={timeline} />}
      {!timeline && !analysis && (
        <div
          className="rounded-lg p-4 border border-white/10 text-center text-xs font-mono text-gray-600"
          style={{ backgroundColor: '#16213e' }}
        >
          Protocol timeline — select an IQ file above and click Analyze, or run a comms session with --save to generate timeline data
        </div>
      )}
    </div>
  )
}
