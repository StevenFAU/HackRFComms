import { useState } from 'react'
import Layout from './components/Layout'
import DeviceDashboard from './components/DeviceDashboard'
import CommsPanel from './components/CommsPanel'
import SpectrumView from './components/SpectrumView'
import AdsbMap from './components/AdsbMap'
import FmPlayer from './components/FmPlayer'
import SignalAnalysis from './components/SignalAnalysis'


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
        return <FmPlayer />
      case 'signals':
        return <SignalAnalysis />
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
