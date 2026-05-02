// OpsBob App - Main entry point managing landing page and dashboard navigation
import { useState } from 'react'
import Landing from './Landing'
import Dashboard from './Dashboard'

function App() {
  const [showLanding, setShowLanding] = useState(true)

  if (showLanding) {
    return <Landing onEnter={() => setShowLanding(false)} />
  }

  return <Dashboard />
}

export default App

// Made with Bob
