import axios from 'axios'
import { useEffect, useMemo, useState } from 'react'

const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

function relativeTime(value) {
  if (!value) return 'never'
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  if (Math.abs(seconds) < 90) return formatter.format(seconds, 'second')
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 90) return formatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 36) return formatter.format(hours, 'hour')
  return formatter.format(Math.round(hours / 24), 'day')
}

function statusFor(row, timeout) {
  const age = (Date.now() - new Date(row.last_heartbeat_at).getTime()) / 1000
  if (age > timeout) return 'offline'
  return row.state === 'idle' ? 'away' : 'active'
}

export default function App() {
  const [data, setData] = useState({ users: [], disconnect_timeout_seconds: 600 })
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)
  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const response = await axios.get('/users')
        if (!cancelled) { setData(response.data); setUpdatedAt(new Date()); setError('') }
      } catch (requestError) { if (!cancelled) setError(requestError.message) }
    }
    refresh()
    const timer = window.setInterval(refresh, 60_000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [])
  const users = useMemo(() => {
    const grouped = new Map()
    for (const row of data.users) {
      if (!grouped.has(row.user_name)) grouped.set(row.user_name, [])
      grouped.get(row.user_name).push(row)
    }
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [data.users])

  return <main>
    <header><div><p className="eyebrow">AYON tray activity</p><h1>Presence</h1><p className="subtitle">Connection and recent input activity across studio machines.</p></div><span className="updated">Updated {updatedAt ? relativeTime(updatedAt) : '…'}</span></header>
    {error && <div className="error">Could not refresh presence: {error}</div>}
    <section className="grid">
      {users.map(([userName, machines]) => {
        const newest = [...machines].sort((a, b) => new Date(b.last_input_at) - new Date(a.last_input_at))[0]
        return <article key={userName}>
          <div className="user-heading"><div className="avatar">{userName.slice(0, 2).toUpperCase()}</div><div><h2>{userName}</h2><p>Last active {relativeTime(newest.last_input_at)} on {newest.machine_name}</p></div></div>
          <div className="machines">{machines.map((machine) => {
            const status = statusFor(machine, data.disconnect_timeout_seconds)
            return <div className="machine" key={machine.machine_name}><span className={`dot ${status}`} /><div><strong>{machine.machine_name}</strong><small>{status} · tray seen {relativeTime(machine.last_heartbeat_at)}</small></div></div>
          })}</div>
        </article>
      })}
      {!users.length && !error && <div className="empty">No tray sessions have reported yet.</div>}
    </section>
  </main>
}
