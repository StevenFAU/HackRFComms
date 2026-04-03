import { useState } from 'react'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'comms', label: 'Comms' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'adsb', label: 'ADS-B' },
  { id: 'fm', label: 'FM' },
  { id: 'signals', label: 'Signals' },
]

export default function Layout({ children, activePage, onNav }) {
  return (
    <div className="flex min-h-screen bg-[#1a1a2e]">
      {/* Sidebar */}
      <aside
        className="fixed left-0 top-0 h-full w-48 flex flex-col"
        style={{ backgroundColor: '#0f3460' }}
      >
        {/* Sidebar header */}
        <div className="px-4 py-5 border-b border-white/10">
          <span className="text-xs font-mono font-semibold tracking-widest text-gray-400 uppercase">
            HackRFComms
          </span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-4">
          {NAV_ITEMS.map((item) => {
            const isActive = activePage === item.id
            return (
              <button
                key={item.id}
                onClick={() => onNav && onNav(item.id)}
                className={`w-full text-left px-5 py-3 text-sm font-mono transition-colors ${
                  isActive
                    ? 'bg-[#00d2ff]/15 text-[#00d2ff] border-r-2 border-[#00d2ff]'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-white/5'
                }`}
              >
                {item.label}
              </button>
            )
          })}
        </nav>

        {/* Sidebar footer */}
        <div className="px-4 py-3 border-t border-white/10">
          <span className="text-xs font-mono text-gray-600">v0.2.0</span>
        </div>
      </aside>

      {/* Main area (offset by sidebar width) */}
      <div className="flex-1 ml-48 flex flex-col">
        {/* Header bar */}
        <header
          className="h-14 flex items-center px-6 border-b border-white/10"
          style={{ backgroundColor: '#0f3460' }}
        >
          <h1 className="text-xl font-bold font-mono" style={{ color: '#00d2ff' }}>
            HackRFComms
          </h1>
          <span className="ml-3 text-gray-400 text-sm font-mono">
            / {NAV_ITEMS.find((n) => n.id === activePage)?.label ?? 'Dashboard'}
          </span>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 bg-[#1a1a2e]">
          {children}
        </main>
      </div>
    </div>
  )
}
