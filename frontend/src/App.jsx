import React, { useState } from 'react'
import { Theme } from '@carbon/react'
import Landing from './Landing'
import Dashboard from './Dashboard'

function App() {
  const [showDashboard, setShowDashboard] = useState(false)
  const [transitioning, setTransitioning] = useState(false)

  const handleEnterDashboard = () => {
    setTransitioning(true)
    setTimeout(() => {
      setShowDashboard(true)
      setTransitioning(false)
    }, 600)
  }

  return (
    <Theme theme="g100">
      {showDashboard ? (
        <Dashboard />
      ) : (
        <Landing
          onEnter={handleEnterDashboard}
          transitioning={transitioning}
        />
      )}
    </Theme>
  )
}

export default App
