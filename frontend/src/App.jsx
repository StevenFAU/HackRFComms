import { useState } from 'react'
import Layout from './components/Layout'
import DeviceDashboard from './components/DeviceDashboard'
import CommsPanel from './components/CommsPanel'
import SpectrumView from './components/SpectrumView'
import AdsbMap from './components/AdsbMap'

function ComingSoon({ page }) {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <p className="text-2xl font-mono text-gray-600 mb-2">{page}</p>
        <p className="text-sm font-mono text-gray-700">Coming soon</p>
      </div>
    </div>
  )
}

export default function App() {
  const [activePage, setActivePage] = useState('dashboard')

  function renderPage() {
    switch (activePage) {
      case 'dashboard':
        return <DeviceDashboard />
      case 'comms':
        return <CommsPanel />
      case 'scanner':
        return <SpectrumView />
      case 'adsb':
        return <AdsbMap />
      case 'fm':
        return <ComingSoon page="FM Radio" />
      case 'signals':
        return <ComingSoon page="Signals" />
      default:
        return <DeviceDashboard />
    }
  }

  return (
    <Layout activePage={activePage} onNav={setActivePage}>
      {renderPage()}
    </Layout>
  )
}
