import { useEffect, useState } from 'react'
import StatusIndicator from './StatusIndicator'

function formatFreq(hz) {
  if (hz == null) return '—'
  return (hz / 1_000_000).toFixed(1) + ' MHz'
}

function formatRate(hz) {
  if (hz == null) return '—'
  return (hz / 1_000_000).toFixed(1) + ' MS/s'
}

function RoleBadge({ role }) {
  const colors = {
    TX: 'bg-purple-600 text-purple-100',
    RX: 'bg-blue-600 text-blue-100',
    unknown: 'bg-gray-600 text-gray-300',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${colors[role] ?? colors.unknown}`}>
      {role}
    </span>
  )
}

function DeviceCard({ device }) {
  const { serial, role, connected, board_id, firmware_version } = device
  return (
    <div
      className={`rounded-lg p-5 flex flex-col gap-3 border-2 transition-colors ${
        connected ? 'border-green-500/60' : 'border-red-600/50'
      }`}
      style={{ backgroundColor: '#16213e' }}
    >
      {/* Card header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RoleBadge role={role} />
          <span className="text-sm font-mono text-gray-300">
            {role === 'TX' ? 'TX HackRF' : role === 'RX' ? 'RX HackRF' : 'Unknown Device'}
          </span>
        </div>
        <StatusIndicator connected={connected} label={connected ? 'Connected' : 'Not found'} />
      </div>

      {/* Details */}
      <div className="space-y-1.5 text-xs font-mono">
        <div className="flex gap-2">
          <span className="text-gray-500 w-28">Serial</span>
          <span className="text-gray-200">{serial}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-gray-500 w-28">Board ID</span>
          <span className="text-gray-200">{board_id ?? '—'}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-gray-500 w-28">Firmware</span>
          <span className="text-gray-200">{firmware_version ?? '—'}</span>
        </div>
      </div>
    </div>
  )
}

export default function DeviceDashboard() {
  const [devices, setDevices] = useState([])
  const [protocols, setProtocols] = useState([])
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  async function fetchData() {
    try {
      const [devRes, protoRes] = await Promise.all([
        fetch('/api/devices'),
        fetch('/api/protocols'),
      ])
      const devData = await devRes.json()
      const protoData = await protoRes.json()
      setDevices(devData.devices ?? [])
      setProtocols(protoData.protocols ?? [])
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (err) {
      setError('Failed to reach backend')
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-8">
      {/* Section: Devices */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold font-mono text-gray-200">HackRF Devices</h2>
          {lastUpdate && (
            <span className="text-xs font-mono text-gray-600">Last updated: {lastUpdate}</span>
          )}
        </div>

        {error && (
          <div className="mb-4 px-4 py-2 bg-red-900/40 border border-red-600/50 rounded text-red-300 text-sm font-mono">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {devices.length === 0 ? (
            <p className="text-gray-500 font-mono text-sm col-span-2">Loading devices...</p>
          ) : (
            devices.map((dev) => (
              <DeviceCard key={dev.serial} device={dev} />
            ))
          )}
        </div>
      </section>

      {/* Section: Protocols */}
      <section>
        <h2 className="text-lg font-bold font-mono text-gray-200 mb-4">Protocol Configurations</h2>
        <div className="rounded-lg overflow-hidden border border-white/10" style={{ backgroundColor: '#16213e' }}>
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-white/10"
                  style={{ backgroundColor: '#0f3460' }}>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Frequency</th>
                <th className="px-4 py-3">Sample Rate</th>
                <th className="px-4 py-3">Description</th>
              </tr>
            </thead>
            <tbody>
              {protocols.map((proto, idx) => (
                <tr
                  key={proto.name}
                  className={`border-b border-white/5 ${idx % 2 === 0 ? 'bg-white/0' : 'bg-white/[0.03]'}`}
                >
                  <td className="px-4 py-3 text-[#00d2ff] font-semibold">{proto.name}</td>
                  <td className="px-4 py-3 text-gray-300">{formatFreq(proto.center_freq)}</td>
                  <td className="px-4 py-3 text-gray-300">{formatRate(proto.sample_rate)}</td>
                  <td className="px-4 py-3 text-gray-400">{proto.description}</td>
                </tr>
              ))}
              {protocols.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-4 text-gray-600 text-center">
                    Loading protocols...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
