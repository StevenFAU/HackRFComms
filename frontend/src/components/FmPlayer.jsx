import { useEffect, useRef, useState } from 'react'

const PRESETS = [
  { label: '88.5', freq: 88.5 },
  { label: '90.3', freq: 90.3 },
  { label: '91.3', freq: 91.3 },
  { label: '93.9', freq: 93.9 },
  { label: '96.5', freq: 96.5 },
  { label: '99.9', freq: 99.9 },
  { label: '100.7', freq: 100.7 },
  { label: '103.1', freq: 103.1 },
  { label: '104.3', freq: 104.3 },
]

const DURATIONS = [5, 10, 15, 30]

// Waveform SVG renderer — renders the downsampled audio array as a centred polyline
function Waveform({ data, width = 800, height = 80 }) {
  if (!data || data.length === 0) return null
  const cx = width / 2
  const cy = height / 2
  const xStep = width / data.length
  const yScale = (height / 2) * 0.9

  const points = data
    .map((v, i) => `${(i * xStep).toFixed(1)},${(cy - v * yScale).toFixed(1)}`)
    .join(' ')

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      style={{ display: 'block', backgroundColor: '#0d1117' }}
      className="rounded"
    >
      {/* Zero line */}
      <line x1={0} y1={cy} x2={width} y2={cy} stroke="#ffffff10" strokeWidth={1} />
      <polyline points={points} fill="none" stroke="#00d2ff" strokeWidth={1} />
    </svg>
  )
}

// Capture progress bar
function ProgressBar({ elapsed, total }) {
  const pct = Math.min(100, (elapsed / total) * 100)
  return (
    <div className="w-full bg-white/5 rounded-full h-1.5 overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${pct}%`, backgroundColor: '#00d2ff' }}
      />
    </div>
  )
}

export default function FmPlayer() {
  const [freq, setFreq]         = useState(93.9)
  const [freqInput, setFreqInput] = useState('93.9')
  const [duration, setDuration] = useState(10)
  const [phase, setPhase]       = useState('idle')
  const [progress, setProgress] = useState({ elapsed: 0, total: 10 })
  const [wavUrl, setWavUrl]     = useState(null)
  const [waveform, setWaveform] = useState([])
  const [durationS, setDurationS] = useState(null)
  const [error, setError]       = useState(null)
  const [statusMsg, setStatusMsg] = useState('')

  const wsRef   = useRef(null)
  const audioRef = useRef(null)

  const isRunning = ['connecting', 'capturing', 'demodulating', 'saving'].includes(phase)

  function applyFreq(val) {
    const n = parseFloat(val)
    if (!isNaN(n) && n >= 76 && n <= 108) {
      setFreq(n)
      setFreqInput(n.toFixed(1))
    }
  }

  function nudge(delta) {
    const next = Math.round((freq + delta) * 10) / 10
    if (next >= 76 && next <= 108) {
      setFreq(next)
      setFreqInput(next.toFixed(1))
    }
  }

  function startTune() {
    if (wsRef.current) return
    setWavUrl(null)
    setWaveform([])
    setDurationS(null)
    setError(null)
    setPhase('connecting')
    setProgress({ elapsed: 0, total: duration })

    const ws = new WebSocket(`ws://${window.location.host}/ws/fm`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ freq, duration }))
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)

        if (msg.type === 'status') {
          setPhase(msg.phase)
          if (msg.phase === 'capturing') {
            setStatusMsg(`Capturing ${msg.duration}s at ${msg.freq_mhz} MHz…`)
            setProgress({ elapsed: 0, total: msg.duration })
          } else if (msg.phase === 'demodulating') {
            setStatusMsg(`Demodulating (${(msg.samples / 1e6).toFixed(0)}M samples)…`)
          } else if (msg.phase === 'saving') {
            setStatusMsg('Writing WAV…')
          }
        } else if (msg.type === 'progress') {
          setProgress({ elapsed: msg.elapsed, total: msg.total })
        } else if (msg.type === 'done') {
          setPhase('done')
          setWavUrl(msg.wav_url)
          setWaveform(msg.waveform ?? [])
          setDurationS(msg.duration_s)
          setStatusMsg(`Ready — ${msg.duration_s}s of audio`)
          wsRef.current = null
        } else if (msg.type === 'cancelled') {
          setPhase('idle')
          setStatusMsg('Cancelled')
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
      if (wsRef.current) wsRef.current = null
    }
  }

  function stopTune() {
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ type: 'stop' })) } catch {}
      wsRef.current.close()
      wsRef.current = null
    }
    setPhase('idle')
    setStatusMsg('')
  }

  useEffect(() => () => wsRef.current?.close(), [])

  // Signal strength: RMS of waveform data (as a rough SNR proxy)
  const rms = waveform.length > 0
    ? Math.sqrt(waveform.reduce((s, v) => s + v * v, 0) / waveform.length)
    : 0
  const signalPct = Math.min(100, Math.round(rms * 300))

  const phaseLabel = {
    idle:         '',
    connecting:   'Connecting…',
    capturing:    statusMsg,
    demodulating: statusMsg,
    saving:       statusMsg,
    done:         statusMsg,
    cancelled:    'Cancelled',
    error:        '',
  }[phase] ?? ''

  const phaseColor = {
    idle:         '',
    connecting:   'text-yellow-400',
    capturing:    'text-yellow-400 animate-pulse',
    demodulating: 'text-blue-400 animate-pulse',
    saving:       'text-blue-400',
    done:         'text-green-400',
    error:        'text-red-400',
  }[phase] ?? 'text-gray-400'

  return (
    <div className="space-y-4 max-w-2xl">

      {/* ── Frequency display ───────────────────────────────────────── */}
      <div
        className="rounded-lg p-6 border border-white/10 text-center"
        style={{ backgroundColor: '#16213e' }}
      >
        <div className="flex items-center justify-center gap-4 mb-4">
          <button
            onClick={() => nudge(-0.1)}
            disabled={isRunning}
            className="w-10 h-10 rounded-lg border border-white/20 text-gray-300 text-xl font-mono hover:border-[#00d2ff]/50 hover:text-[#00d2ff] transition-colors disabled:opacity-30"
          >
            ‹
          </button>

          <div className="flex items-baseline gap-1">
            <input
              type="number"
              value={freqInput}
              step="0.1"
              min="76"
              max="108"
              onChange={e => setFreqInput(e.target.value)}
              onBlur={e => applyFreq(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && applyFreq(freqInput)}
              disabled={isRunning}
              className="w-32 text-center text-4xl font-mono font-bold bg-transparent border-none outline-none text-[#00d2ff] disabled:opacity-60"
              style={{ appearance: 'textfield' }}
            />
            <span className="text-xl font-mono text-gray-400">MHz</span>
          </div>

          <button
            onClick={() => nudge(0.1)}
            disabled={isRunning}
            className="w-10 h-10 rounded-lg border border-white/20 text-gray-300 text-xl font-mono hover:border-[#00d2ff]/50 hover:text-[#00d2ff] transition-colors disabled:opacity-30"
          >
            ›
          </button>
        </div>

        {/* Frequency slider */}
        <input
          type="range"
          min="88"
          max="108"
          step="0.1"
          value={freq}
          disabled={isRunning}
          onChange={e => {
            const v = parseFloat(e.target.value)
            setFreq(v)
            setFreqInput(v.toFixed(1))
          }}
          className="w-full accent-[#00d2ff] disabled:opacity-40"
        />
        <div className="flex justify-between text-xs font-mono text-gray-600 mt-1">
          <span>88.0</span>
          <span>98.0</span>
          <span>108.0</span>
        </div>
      </div>

      {/* ── Presets ─────────────────────────────────────────────────── */}
      <div
        className="rounded-lg px-4 py-3 border border-white/10 flex flex-wrap gap-2"
        style={{ backgroundColor: '#16213e' }}
      >
        <span className="text-xs font-mono text-gray-500 self-center mr-1">Presets</span>
        {PRESETS.map(p => (
          <button
            key={p.freq}
            onClick={() => {
              setFreq(p.freq)
              setFreqInput(p.label)
            }}
            disabled={isRunning}
            className={`px-3 py-1 text-xs font-mono rounded border transition-colors disabled:opacity-40 ${
              freq === p.freq
                ? 'border-[#00d2ff]/60 text-[#00d2ff] bg-[#00d2ff]/10'
                : 'border-white/15 text-gray-400 hover:border-white/30'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* ── Duration + action ───────────────────────────────────────── */}
      <div
        className="rounded-lg p-4 border border-white/10 flex flex-wrap items-center gap-4"
        style={{ backgroundColor: '#16213e' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-500">Duration</span>
          {DURATIONS.map(d => (
            <button
              key={d}
              onClick={() => setDuration(d)}
              disabled={isRunning}
              className={`px-3 py-1 text-xs font-mono rounded border transition-colors disabled:opacity-40 ${
                duration === d
                  ? 'border-[#00d2ff]/60 text-[#00d2ff] bg-[#00d2ff]/10'
                  : 'border-white/20 text-gray-400 hover:border-white/40'
              }`}
            >
              {d}s
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className={`text-xs font-mono ${phaseColor}`}>{phaseLabel}</span>
          {isRunning ? (
            <button
              onClick={stopTune}
              className="px-5 py-2 text-sm font-mono rounded border border-red-500/60 text-red-400 hover:bg-red-900/20 transition-colors"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={startTune}
              className="px-5 py-2 text-sm font-mono rounded border border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10 transition-colors"
            >
              Tune
            </button>
          )}
        </div>

        {error && (
          <div className="w-full px-3 py-1.5 bg-red-900/30 border border-red-600/40 rounded text-red-300 text-xs font-mono">
            {error}
          </div>
        )}

        {/* Capture progress bar */}
        {phase === 'capturing' && (
          <div className="w-full space-y-1">
            <ProgressBar elapsed={progress.elapsed} total={progress.total} />
            <div className="flex justify-between text-xs font-mono text-gray-600">
              <span>{progress.elapsed}s</span>
              <span>{progress.total}s</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Audio player + waveform (shown when done) ───────────────── */}
      {wavUrl && (
        <div
          className="rounded-lg p-4 border border-white/10 space-y-4"
          style={{ backgroundColor: '#16213e' }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-gray-400">
              {freq} MHz · {durationS}s · WAV 44.1 kHz mono
            </span>
            {/* Signal strength indicator */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-500">Signal</span>
              <div className="flex gap-0.5">
                {[20, 40, 60, 80, 100].map(threshold => (
                  <div
                    key={threshold}
                    className="w-2 rounded-sm transition-colors"
                    style={{
                      height: `${8 + threshold / 10}px`,
                      backgroundColor: signalPct >= threshold ? '#00d2ff' : '#ffffff15',
                    }}
                  />
                ))}
              </div>
              <span className="text-xs font-mono text-[#00d2ff]">{signalPct}%</span>
            </div>
          </div>

          {/* Waveform */}
          <div className="rounded overflow-hidden border border-white/10">
            <Waveform data={waveform} />
          </div>

          {/* HTML5 audio player */}
          <audio
            ref={audioRef}
            controls
            className="w-full"
            style={{ accentColor: '#00d2ff' }}
            src={wavUrl}
          >
            Your browser does not support audio playback.
          </audio>
        </div>
      )}
    </div>
  )
}
