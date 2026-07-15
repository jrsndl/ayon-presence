import axios from 'axios'
import React, { useContext, useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { AddonContext, AddonProvider } from '@ynput/ayon-react-addon-provider'
import App from './App.jsx'
import TimeLogApp from './TimeLogApp.jsx'
import './styles.css'
import './timelog.css'

function ConnectedApp() {
  const context = useContext(AddonContext)
  const { accessToken, addonName, addonVersion } = context || {}
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!accessToken || !addonName || !addonVersion) return
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`
    axios.defaults.baseURL = `${window.location.origin}/api/addons/${addonName}/${addonVersion}`
    setReady(true)
  }, [accessToken, addonName, addonVersion])
  return ready
    ? (context.scope === 'dashboard' ? <TimeLogApp ayonContext={context} /> : <App />)
    : <main className="loading">Connecting to AYON…</main>
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><AddonProvider><ConnectedApp /></AddonProvider></React.StrictMode>,
)
