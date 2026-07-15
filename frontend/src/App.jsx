import axios from 'axios'
import { useEffect, useMemo, useRef, useState } from 'react'

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
  return value === null || value === undefined || value === '' ? '—' : value
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

function SortableTable({ columns, rows, initialSort, initialDirection = 'asc', emptyMessage }) {
  const [sort, setSort] = useState({ key: initialSort, direction: initialDirection })
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
  { key: 'dcc', label: 'DCC' },
  { key: 'workfile', label: 'Workfile' },
  { key: 'foreground_application', label: 'Foreground App' },
  { key: 'foreground_title', label: 'Window Title' },
  { key: 'last_active_at', label: 'Last Active', render: (row) => relativeTime(row.last_active_at) },
  { key: 'last_project', label: 'Last Project' },
  { key: 'last_folder', label: 'Last Folder' },
  { key: 'last_task', label: 'Last Task' },
  { key: 'last_task_seconds', label: 'Last Task Time', render: (row) => duration(row.last_task_seconds) },
  { key: 'day_started_at', label: 'Day Started', render: (row) => timeOfDay(row.day_started_at) },
  { key: 'day_ended_at', label: 'Day Ended', render: (row) => timeOfDay(row.day_ended_at) },
]

const computerColumns = [
  { key: 'computer_name', label: 'Computer Name' },
  { key: 'last_user', label: 'Last User' },
  { key: 'dcc', label: 'DCC' },
  { key: 'last_active_at', label: 'Last Active', render: (row) => relativeTime(row.last_active_at) },
]

const projectColumns = [
  { key: 'project_name', label: 'Project' },
  {
    key: 'users',
    label: 'Users',
    sortValue: (row) => row.users.join(', '),
    render: (row) => row.users.join(', '),
  },
  { key: 'user_count', label: 'User #' },
  { key: 'total_seconds', label: 'Time logged', render: (row) => duration(row.total_seconds) },
]

function timestamp(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

const eventColumns = [
  { key: 'id', label: 'ID' },
  { key: 'received_at', label: 'Received', render: (row) => timestamp(row.received_at) },
  { key: 'user_name', label: 'User' },
  { key: 'event_type', label: 'Event Type' },
  { key: 'session_id', label: 'Session ID' },
  { key: 'machine_name', label: 'Machine' },
  { key: 'platform', label: 'Platform' },
  { key: 'client_version', label: 'Client Version' },
  { key: 'client_time', label: 'Client Time', render: (row) => timestamp(row.client_time) },
  { key: 'last_input_at', label: 'Last Input', render: (row) => timestamp(row.last_input_at) },
  { key: 'idle_seconds', label: 'Idle Seconds' },
  { key: 'project_name', label: 'Project' },
  { key: 'folder_path', label: 'Folder' },
  { key: 'task_name', label: 'Task' },
  { key: 'task_started_at', label: 'Task Started', render: (row) => timestamp(row.task_started_at) },
  { key: 'dcc_name', label: 'DCC Name' },
  { key: 'dcc_version', label: 'DCC Version' },
  { key: 'workfile_name', label: 'Workfile' },
  { key: 'foreground_application', label: 'Foreground App' },
  { key: 'foreground_title', label: 'Window Title' },
]

const presets = [
  ['today', 'Today'],
  ['yesterday', 'Yesterday'],
  ['this_week', 'This Week'],
  ['last_week', 'Last Week'],
  ['this_month', 'This Month'],
  ['last_month', 'Last Month'],
  ['this_year', 'This Year'],
  ['last_year', 'Last Year'],
  ['custom', 'Custom'],
]

function dateOnly(year, month, day) {
  return new Date(year, month, day, 12)
}

function addDays(value, amount) {
  return dateOnly(value.getFullYear(), value.getMonth(), value.getDate() + amount)
}

function isoDate(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function presetRange(preset, weekStart = 'monday', now = new Date()) {
  const today = dateOnly(now.getFullYear(), now.getMonth(), now.getDate())
  const weekOffset = weekStart === 'sunday'
    ? today.getDay()
    : (today.getDay() + 6) % 7
  const currentWeekStart = addDays(today, -weekOffset)
  if (preset === 'today' || preset === 'custom') return { start: today, end: today }
  if (preset === 'yesterday') {
    const yesterday = addDays(today, -1)
    return { start: yesterday, end: yesterday }
  }
  if (preset === 'this_week') return { start: currentWeekStart, end: addDays(currentWeekStart, 6) }
  if (preset === 'last_week') return { start: addDays(currentWeekStart, -7), end: addDays(currentWeekStart, -1) }
  if (preset === 'this_month') return {
    start: dateOnly(today.getFullYear(), today.getMonth(), 1),
    end: dateOnly(today.getFullYear(), today.getMonth() + 1, 0),
  }
  if (preset === 'last_month') return {
    start: dateOnly(today.getFullYear(), today.getMonth() - 1, 1),
    end: dateOnly(today.getFullYear(), today.getMonth(), 0),
  }
  if (preset === 'this_year') return {
    start: dateOnly(today.getFullYear(), 0, 1),
    end: dateOnly(today.getFullYear(), 11, 31),
  }
  return {
    start: dateOnly(today.getFullYear() - 1, 0, 1),
    end: dateOnly(today.getFullYear() - 1, 11, 31),
  }
}

const weekdayLabels = {
  monday: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
  sunday: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
}

function sameDate(left, right) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
}

function calendarDays(month, weekStart) {
  const first = dateOnly(month.getFullYear(), month.getMonth(), 1)
  const weekOffset = weekStart === 'sunday'
    ? first.getDay()
    : (first.getDay() + 6) % 7
  const gridStart = addDays(first, -weekOffset)
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index))
}

function DateWidget({ label, value, weekStart, onChange }) {
  const [open, setOpen] = useState(false)
  const [visibleMonth, setVisibleMonth] = useState(() => dateOnly(value.getFullYear(), value.getMonth(), 1))
  const rootRef = useRef(null)
  const display = value.toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  })

  useEffect(() => {
    if (!open) return undefined
    function closeOutside(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    function closeOnEscape(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  function toggleCalendar() {
    if (!open) setVisibleMonth(dateOnly(value.getFullYear(), value.getMonth(), 1))
    setOpen((current) => !current)
  }

  function selectDate(date) {
    onChange(date)
    setOpen(false)
  }

  const monthLabel = visibleMonth.toLocaleDateString(undefined, {
    month: 'long', year: 'numeric',
  })
  const today = new Date()

  return <div className="date-field" ref={rootRef}>
    <span className="sr-only">{label}</span>
    <button type="button" className="date-arrow" aria-label={`Previous ${label.toLowerCase()}`} onClick={() => onChange(addDays(value, -1))}>‹</button>
    <button type="button" className="date-value" aria-label={label} aria-haspopup="dialog" aria-expanded={open} onClick={toggleCalendar}>{display}</button>
    <button type="button" className="date-arrow" aria-label={`Next ${label.toLowerCase()}`} onClick={() => onChange(addDays(value, 1))}>›</button>
    {open && <div className="calendar-popover" role="dialog" aria-label={`Choose ${label.toLowerCase()}`}>
      <div className="calendar-heading">
        <strong>{monthLabel}</strong>
        <div>
          <button type="button" aria-label="Previous month" onClick={() => setVisibleMonth((current) => dateOnly(current.getFullYear(), current.getMonth() - 1, 1))}>‹</button>
          <button type="button" aria-label="Next month" onClick={() => setVisibleMonth((current) => dateOnly(current.getFullYear(), current.getMonth() + 1, 1))}>›</button>
        </div>
      </div>
      <div className="calendar-weekdays" aria-hidden="true">
        {weekdayLabels[weekStart].map((weekday) => <span key={weekday}>{weekday}</span>)}
      </div>
      <div className="calendar-grid" role="grid">
        {calendarDays(visibleMonth, weekStart).map((day) => {
          const outside = day.getMonth() !== visibleMonth.getMonth()
          const selected = sameDate(day, value)
          const isToday = sameDate(day, today)
          const classNames = ['calendar-day', outside ? 'outside' : '', selected ? 'selected' : '', isToday ? 'today' : ''].filter(Boolean).join(' ')
          return <button
            type="button"
            role="gridcell"
            className={classNames}
            aria-label={day.toLocaleDateString(undefined, { dateStyle: 'full' })}
            aria-selected={selected}
            key={isoDate(day)}
            onClick={() => selectDate(day)}
          >{day.getDate()}</button>
        })}
      </div>
      <button type="button" className="calendar-today" onClick={() => selectDate(dateOnly(today.getFullYear(), today.getMonth(), today.getDate()))}>Today</button>
    </div>}
  </div>
}

export default function App() {
  const [data, setData] = useState({ users: [], computers: [] })
  const [projects, setProjects] = useState([])
  const [error, setError] = useState('')
  const [projectError, setProjectError] = useState('')
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [events, setEvents] = useState([])
  const [nextEventCursor, setNextEventCursor] = useState(null)
  const [eventsError, setEventsError] = useState('')
  const [eventsLoading, setEventsLoading] = useState(false)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [activeTab, setActiveTab] = useState('users')
  const [preset, setPreset] = useState('this_week')
  const [weekStart, setWeekStart] = useState('monday')
  const [range, setRange] = useState(() => presetRange('this_week'))
  const initializedPreset = useRef(false)
  const eventsInitialized = useRef(false)
  const eventsRequestInFlight = useRef(false)

  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const response = await axios.get('/users')
        if (!cancelled) {
          setData(response.data)
          if (!initializedPreset.current) {
            const configured = response.data.projects_default_date_range || 'this_week'
            const configuredWeekStart = response.data.projects_week_start || 'monday'
            setPreset(configured)
            setWeekStart(configuredWeekStart)
            setRange(presetRange(configured, configuredWeekStart))
            initializedPreset.current = true
          }
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

  useEffect(() => {
    if (activeTab !== 'projects') return undefined
    let cancelled = false
    async function refreshProjects() {
      setProjectsLoading(true)
      try {
        const response = await axios.get('/project-time', {
          params: { from: isoDate(range.start), to: isoDate(range.end) },
        })
        if (!cancelled) {
          setProjects(response.data.projects || [])
          setProjectError(response.data.error || '')
        }
      } catch (requestError) {
        if (!cancelled) setProjectError(requestError.message)
      } finally {
        if (!cancelled) setProjectsLoading(false)
      }
    }
    refreshProjects()
    return () => { cancelled = true }
  }, [activeTab, range])

  useEffect(() => {
    if (activeTab === 'events' && data.raw_events_debug_enabled && !eventsInitialized.current) {
      loadEvents(true)
    }
    if (activeTab === 'events' && data.raw_events_debug_enabled === false) {
      setActiveTab('users')
    }
  }, [activeTab, data.raw_events_debug_enabled])

  async function loadEvents(reset = false) {
    if (eventsRequestInFlight.current) return
    eventsRequestInFlight.current = true
    eventsInitialized.current = true
    setEventsLoading(true)
    try {
      const cursor = reset ? null : nextEventCursor
      const response = await axios.get('/raw-events', {
        params: { page_size: 50, ...(cursor ? { before_id: cursor } : {}) },
      })
      setEvents((current) => reset
        ? response.data.events || []
        : [...current, ...(response.data.events || [])])
      setNextEventCursor(response.data.next_cursor || null)
      setEventsError('')
    } catch (requestError) {
      setEventsError(requestError.message)
    } finally {
      eventsRequestInFlight.current = false
      setEventsLoading(false)
    }
  }

  function selectPreset(value) {
    setPreset(value)
    if (value !== 'custom') setRange(presetRange(value, weekStart))
  }

  function changeStart(value) {
    setPreset('custom')
    setRange((current) => ({ start: value, end: value > current.end ? value : current.end }))
  }

  function changeEnd(value) {
    setPreset('custom')
    setRange((current) => ({ start: value < current.start ? value : current.start, end: value }))
  }

  return <main>
    <header>
      <div><p className="eyebrow">AYON tray activity</p><h1>Presence</h1><p className="subtitle">User, computer, and project activity across the studio.</p></div>
      <span className="updated">Updated {updatedAt ? relativeTime(updatedAt) : '…'}</span>
    </header>
    {error && <div className="error">Could not refresh presence: {error}</div>}
    <div className="tabs" role="tablist" aria-label="Presence views">
      <button type="button" role="tab" aria-selected={activeTab === 'users'} onClick={() => setActiveTab('users')}>
        Users <span>{data.users.length}</span>
      </button>
      <button type="button" role="tab" aria-selected={activeTab === 'computers'} onClick={() => setActiveTab('computers')}>
        Computers <span>{data.computers.length}</span>
      </button>
      <button type="button" role="tab" aria-selected={activeTab === 'projects'} onClick={() => setActiveTab('projects')}>
        Projects <span>{projects.length}</span>
      </button>
      {data.raw_events_debug_enabled && <button type="button" role="tab" aria-selected={activeTab === 'events'} onClick={() => setActiveTab('events')}>
        Events <span>{events.length}{nextEventCursor ? '+' : ''}</span>
      </button>}
    </div>
    <div className="tab-content">
      <section className="panel users-panel" role="tabpanel" hidden={activeTab !== 'users'}>
        <div className="section-heading"><div><p className="section-label">Users</p><h2>User activity</h2></div><span>{data.users.length} users</span></div>
        <SortableTable columns={userColumns} rows={data.users} initialSort="user_name" emptyMessage="No tray sessions have reported yet." />
      </section>
      <section className="panel computers-panel" role="tabpanel" hidden={activeTab !== 'computers'}>
        <div className="section-heading"><div><p className="section-label">Computers</p><h2>Computer activity</h2></div><span>{data.computers.length} computers</span></div>
        <SortableTable columns={computerColumns} rows={data.computers} initialSort="computer_name" emptyMessage="No computers have reported yet." />
      </section>
      <section className="panel projects-panel" role="tabpanel" hidden={activeTab !== 'projects'}>
        <div className="section-heading projects-heading">
          <div><p className="section-label">Projects</p><h2>Time logged</h2></div>
          <span>{projects.length} projects</span>
        </div>
        <div className="date-controls" aria-label="Project report date range">
          <label className="preset-field"><span className="sr-only">Date preset</span>
            <select value={preset} onChange={(event) => selectPreset(event.target.value)}>
              {presets.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <DateWidget label="Start date" value={range.start} weekStart={weekStart} onChange={changeStart} />
          <span className="range-separator" aria-hidden="true">→</span>
          <DateWidget label="End date" value={range.end} weekStart={weekStart} onChange={changeEnd} />
        </div>
        {projectError && <div className="error inline-error">Could not load project time: {projectError}</div>}
        {projectsLoading
          ? <div className="loading">Loading project time…</div>
          : <SortableTable columns={projectColumns} rows={projects} initialSort="project_name" emptyMessage="No task time was logged in this date range." />}
      </section>
      {data.raw_events_debug_enabled && <section className="panel events-panel" role="tabpanel" hidden={activeTab !== 'events'}>
        <div className="section-heading">
          <div><p className="section-label">Debug</p><h2>Raw events</h2></div>
          <div className="heading-actions"><span>{events.length} loaded</span><button type="button" onClick={() => loadEvents(true)} disabled={eventsLoading}>Refresh</button></div>
        </div>
        {eventsError && <div className="error inline-error">Could not load raw events: {eventsError}</div>}
        {eventsLoading && !events.length
          ? <div className="loading">Loading raw events…</div>
          : <SortableTable columns={eventColumns} rows={events} initialSort="id" initialDirection="desc" emptyMessage="No retained raw events were found." />}
        {!!events.length && <div className="pagination">
          {nextEventCursor
            ? <button type="button" onClick={() => loadEvents(false)} disabled={eventsLoading}>{eventsLoading ? 'Loading…' : 'Load 50 more'}</button>
            : <span>All retained events loaded</span>}
        </div>}
      </section>}
    </div>
  </main>
}
