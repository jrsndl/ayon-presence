import axios from 'axios'
import { useEffect, useMemo, useState } from 'react'

function plural(value, unit) {
  return `${value} ${unit}${value === 1 ? '' : 's'} ago`
}

function relativeTime(value) {
  if (!value) return 'Never'
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return plural(seconds, 'second')
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return plural(minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return plural(hours, 'hour')
  return plural(Math.floor(hours / 24), 'day')
}

function duration(value) {
  if (value === null || value === undefined) return '—'
  const seconds = Math.max(0, Math.floor(value))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`
}

function timeOfDay(value) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function text(value) {
  return value || '—'
}

function compareValues(left, right) {
  const leftMissing = left === null || left === undefined || left === ''
  const rightMissing = right === null || right === undefined || right === ''
  if (leftMissing || rightMissing) {
    if (leftMissing && rightMissing) return 0
    return leftMissing ? 1 : -1
  }
  if (typeof left === 'number' && typeof right === 'number') return left - right
  return String(left).localeCompare(String(right), undefined, {
    numeric: true,
    sensitivity: 'base',
  })
}

function SortableTable({ columns, rows, initialSort, emptyMessage }) {
  const [sort, setSort] = useState({ key: initialSort, direction: 'asc' })
  const sortedRows = useMemo(() => {
    const column = columns.find((item) => item.key === sort.key) || columns[0]
    const direction = sort.direction === 'asc' ? 1 : -1
    return [...rows].sort((left, right) => {
      const leftValue = column.sortValue ? column.sortValue(left) : left[column.key]
      const rightValue = column.sortValue ? column.sortValue(right) : right[column.key]
      return compareValues(leftValue, rightValue) * direction
    })
  }, [columns, rows, sort])

  function changeSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }))
  }

  if (!rows.length) return <div className="empty">{emptyMessage}</div>

  return <div className="table-scroll"><table>
    <thead><tr>{columns.map((column) => {
      const active = sort.key === column.key
      return <th key={column.key} scope="col">
        <button type="button" onClick={() => changeSort(column.key)}>
          {column.label}<span className={active ? 'sort active' : 'sort'}>{active ? (sort.direction === 'asc' ? '▲' : '▼') : '↕'}</span>
        </button>
      </th>
    })}</tr></thead>
    <tbody>{sortedRows.map((row, index) => <tr key={row.id || `${initialSort}-${index}`}>
      {columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : text(row[column.key])}</td>)}
    </tr>)}</tbody>
  </table></div>
}

const userColumns = [
  { key: 'user_name', label: 'User Name' },
  { key: 'computer_name', label: 'Computer Name' },
  {
    key: 'other_computers',
    label: 'Other Computers',
    sortValue: (row) => row.other_computers.join(', '),
    render: (row) => row.other_computers.length ? row.other_computers.join(', ') : '—',
  },
  { key: 'last_active_at', label: 'Last Active', render: (row) => relativeTime(row.last_active_at) },
  { key: 'last_project', label: 'Last Project' },
  { key: 'last_folder', label: 'Last Folder' },
  { key: 'last_task', label: 'Last Task' },
  { key: 'last_task_seconds', label: 'Last Task Time', render: (row) => duration(row.last_task_seconds) },
  { key: 'day_started_at', label: 'Day Started', render: (row) => timeOfDay(row.day_started_at) },
]

const computerColumns = [
  { key: 'computer_name', label: 'Computer Name' },
  { key: 'last_user', label: 'Last User' },
  { key: 'last_active_at', label: 'Last Active', render: (row) => relativeTime(row.last_active_at) },
]

export default function App() {
  const [data, setData] = useState({ users: [], computers: [] })
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const response = await axios.get('/users')
        if (!cancelled) {
          setData(response.data)
          setUpdatedAt(new Date())
          setError('')
        }
      } catch (requestError) {
        if (!cancelled) setError(requestError.message)
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return <main>
    <header>
      <div><p className="eyebrow">AYON tray activity</p><h1>Presence</h1><p className="subtitle">User and computer activity across the studio.</p></div>
      <span className="updated">Updated {updatedAt ? relativeTime(updatedAt) : '…'}</span>
    </header>
    {error && <div className="error">Could not refresh presence: {error}</div>}
    <div className="sections">
      <section className="panel users-panel">
        <div className="section-heading"><div><p className="section-label">Users</p><h2>User activity</h2></div><span>{data.users.length} users</span></div>
        <SortableTable columns={userColumns} rows={data.users} initialSort="user_name" emptyMessage="No tray sessions have reported yet." />
      </section>
      <section className="panel computers-panel">
        <div className="section-heading"><div><p className="section-label">Computers</p><h2>Computer activity</h2></div><span>{data.computers.length} computers</span></div>
        <SortableTable columns={computerColumns} rows={data.computers} initialSort="computer_name" emptyMessage="No computers have reported yet." />
      </section>
    </div>
  </main>
}
