import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('Connecting...')

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setStatus(`${d.project} — ${d.status}`))
      .catch(() => setStatus('Backend unreachable'))
  }, [])

  return (
    <div className="min-h-screen bg-[#1a1a2e] flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-[#00d2ff] font-mono mb-4">HackRFComms</h1>
        <p className="text-lg text-gray-300 font-mono">{status}</p>
      </div>
    </div>
  )
}
