import axios from 'axios'
import React, { useContext, useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { AddonContext, AddonProvider } from '@ynput/ayon-react-addon-provider'
import App from './App.jsx'
import './styles.css'

function ConnectedApp() {
  const { accessToken, addonName, addonVersion } = useContext(AddonContext)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!accessToken || !addonName || !addonVersion) return
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`
    axios.defaults.baseURL = `${window.location.origin}/api/addons/${addonName}/${addonVersion}`
    setReady(true)
  }, [accessToken, addonName, addonVersion])
  return ready ? <App /> : <main className="loading">Connecting to AYON…</main>
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><AddonProvider><ConnectedApp /></AddonProvider></React.StrictMode>,
)
