import axios from 'axios'
import { useEffect, useMemo, useRef, useState } from 'react'

const STATUS_LABELS = {
  not_submitted: 'Not submitted',
  submitted: 'Submitted',
  approved: 'Approved',
  disputed: 'Disputed',
  rejected: 'Rejected',
}

const PRESETS = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['this_week', 'This Week'],
  ['last_week', 'Last Week'], ['this_month', 'This Month'], ['last_month', 'Last Month'],
  ['this_year', 'This Year'], ['last_year', 'Last Year'], ['custom', 'Custom'],
]

function pad(value) { return String(value).padStart(2, '0') }
function isoDay(date) { return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` }
function dayAtNoon(value = new Date()) { return new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12) }
function addDays(date, count) { const result = new Date(date); result.setDate(result.getDate() + count); return dayAtNoon(result) }
function eachDay(start, end) { const result = []; for (let day = start; day <= end; day = addDays(day, 1)) result.push(day); return result }
function duration(seconds) {
  const minutes = Math.max(0, Math.round(Number(seconds || 0) / 60))
  const hours = Math.floor(minutes / 60); const rest = minutes % 60
  return hours ? `${hours}h${rest ? ` ${rest}m` : ''}` : `${rest}m`
}
function durationInput(seconds) { return (Number(seconds || 0) / 3600).toFixed(2).replace(/\.00$/, '') }
function validZone(zone, fallback = 'UTC') {
  try { new Intl.DateTimeFormat('en', { timeZone: zone }).format(); return zone || fallback } catch { return fallback }
}
function zonedParts(value, timeZone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: validZone(timeZone), year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short',
  }).formatToParts(new Date(value))
  return Object.fromEntries(parts.map((part) => [part.type, part.value]))
}
function zonedDay(value, zone) { const part = zonedParts(value, zone); return `${part.year}-${part.month}-${part.day}` }
function zonedTime(value, zone) { const part = zonedParts(value, zone); return `${part.hour}:${part.minute}` }
function zonedDateTime(value, zone) {
  if (!value) return 'Running'
  const part = zonedParts(value, zone)
  return `${part.month}/${part.day}/${part.year} ${part.hour}:${part.minute}`
}
function zonedLocalToUtc(dateValue, timeValue, zone) {
  const [year, month, day] = dateValue.split('-').map(Number)
  const [hour, minute] = timeValue.split(':').map(Number)
  let guess = Date.UTC(year, month - 1, day, hour, minute)
  for (let index = 0; index < 2; index += 1) {
    const actual = zonedParts(new Date(guess), zone)
    const rendered = Date.UTC(+actual.year, +actual.month - 1, +actual.day, +actual.hour, +actual.minute)
    guess += Date.UTC(year, month - 1, day, hour, minute) - rendered
  }
  return new Date(guess).toISOString()
}
function rangeFor(preset, weekStart = 'monday') {
  const today = dayAtNoon(); const offset = weekStart === 'sunday' ? today.getDay() : (today.getDay() + 6) % 7
  const week = addDays(today, -offset)
  if (preset === 'today' || preset === 'custom') return { start: today, end: today }
  if (preset === 'yesterday') return { start: addDays(today, -1), end: addDays(today, -1) }
  if (preset === 'this_week') return { start: week, end: addDays(week, 6) }
  if (preset === 'last_week') return { start: addDays(week, -7), end: addDays(week, -1) }
  if (preset === 'this_month') return { start: new Date(today.getFullYear(), today.getMonth(), 1, 12), end: new Date(today.getFullYear(), today.getMonth() + 1, 0, 12) }
  if (preset === 'last_month') return { start: new Date(today.getFullYear(), today.getMonth() - 1, 1, 12), end: new Date(today.getFullYear(), today.getMonth(), 0, 12) }
  if (preset === 'this_year') return { start: new Date(today.getFullYear(), 0, 1, 12), end: new Date(today.getFullYear(), 11, 31, 12) }
  return { start: new Date(today.getFullYear() - 1, 0, 1, 12), end: new Date(today.getFullYear() - 1, 11, 31, 12) }
}
function logKey(log) { return [log.project_name, log.folder_path, log.task_name].join('|') }
function taskLabel(log) { return [log.project_name, log.folder_path, log.task_name].filter(Boolean).join(' · ') || 'Unassigned time' }
function overlaps(left, right) {
  const leftEnd = new Date(left.ended_at || Date.now()).getTime(); const rightEnd = new Date(right.ended_at || Date.now()).getTime()
  return new Date(left.started_at).getTime() < rightEnd && new Date(right.started_at).getTime() < leftEnd
}

function TaskPicker({ value, onChange, userName, assignedOnly, projectHint, bidAttribute }) {
  const [projects, setProjects] = useState([]); const [folders, setFolders] = useState([]); const [tasks, setTasks] = useState([])
  const project = value?.project_name || projectHint || ''
  const folderId = value?.folder_id || ''
  useEffect(() => {
    axios.get(`${window.location.origin}/api/projects`, { params: { active: true } }).then(({ data }) => {
      setProjects(data.projects || data || [])
    }).catch(() => setProjects(project ? [{ name: project }] : []))
  }, [projectHint])
  useEffect(() => {
    if (!project) { setFolders([]); setTasks([]); return }
    Promise.all([
      axios.get(`${window.location.origin}/api/projects/${encodeURIComponent(project)}/folders`, { params: { active: true } }),
      axios.get(`${window.location.origin}/api/projects/${encodeURIComponent(project)}/tasks`, { params: { active: true } }),
    ]).then(([folderResponse, taskResponse]) => {
      setFolders(folderResponse.data.folders || folderResponse.data || [])
      setTasks(taskResponse.data.tasks || taskResponse.data || [])
    }).catch(() => { setFolders([]); setTasks([]) })
  }, [project])
  const availableTasks = tasks.filter((task) => (!folderId || task.folderId === folderId)
    && (!assignedOnly || (task.assignees || []).includes(userName)))
  function selectProject(name) { onChange({ project_name: name || null }) }
  function selectFolder(id) {
    const folder = folders.find((item) => item.id === id)
    onChange({ project_name: project, folder_id: id || null, folder_path: folder?.path || null,
      folder_name: folder?.name || null, folder_label: folder?.label || null, thumbnail_id: folder?.thumbnailId || null })
  }
  function selectTask(id) {
    const task = tasks.find((item) => item.id === id); const folder = folders.find((item) => item.id === task?.folderId)
    if (!task) { onChange({ ...value, task_id: null, task_name: null }); return }
    onChange({ project_name: project, folder_id: task.folderId, folder_path: folder?.path,
      folder_name: folder?.name, folder_label: folder?.label, task_id: task.id,
      task_name: task.name, task_type: task.taskType, task_status: task.status,
      thumbnail_id: task.thumbnailId || folder?.thumbnailId,
      bid_hours: Number(task.attrib?.[bidAttribute]) || null })
  }
  return <div className="task-picker">
    <select aria-label="Project" value={project} onChange={(event) => selectProject(event.target.value)}>
      <option value="">Project</option>{projects.map((item) => <option key={item.name} value={item.name}>{item.label || item.name}</option>)}
    </select>
    <select aria-label="Folder" value={folderId} disabled={!project} onChange={(event) => selectFolder(event.target.value)}>
      <option value="">Folder path</option>{folders.map((item) => <option key={item.id} value={item.id}>{item.path || item.label || item.name}</option>)}
    </select>
    <select aria-label="Task" value={value?.task_id || ''} disabled={!folderId} onChange={(event) => selectTask(event.target.value)}>
      <option value="">Task</option>{availableTasks.map((item) => <option key={item.id} value={item.id}>{item.label || item.name} · {item.taskType}</option>)}
    </select>
  </div>
}

function LogModal({ initial, zone, taskProps, onClose, onSave }) {
  const initialStart = initial?.started_at || new Date().toISOString(); const startParts = zonedParts(initialStart, zone)
  const initialEnd = initial?.ended_at || new Date(new Date(initialStart).getTime() + 3600000).toISOString(); const endParts = zonedParts(initialEnd, zone)
  const [day] = useState(`${startParts.year}-${startParts.month}-${startParts.day}`)
  const [start, setStart] = useState(`${startParts.hour}:${startParts.minute}`); const [end, setEnd] = useState(`${endParts.hour}:${endParts.minute}`)
  const [task, setTask] = useState(initial || {}); const [error, setError] = useState('')
  const seconds = Math.max(0, (new Date(zonedLocalToUtc(day, end, zone)) - new Date(zonedLocalToUtc(day, start, zone))) / 1000)
  function setDuration(hours) {
    const startDate = new Date(zonedLocalToUtc(day, start, zone)); const endDate = new Date(startDate.getTime() + Number(hours) * 3600000)
    setEnd(zonedTime(endDate, zone))
  }
  async function save() {
    const started_at = zonedLocalToUtc(day, start, zone); const ended_at = zonedLocalToUtc(day, end, zone)
    if (new Date(ended_at) <= new Date(started_at)) { setError('End time must be after start time.'); return }
    await onSave({ ...task, started_at, ended_at })
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="log-modal" role="dialog" aria-modal="true" aria-label={initial?.id ? 'Edit TimeLog' : 'Create TimeLog'}>
      <header><div><span className="tl-kicker">{initial?.id ? 'Edit' : 'Create'}</span><h2>TimeLog</h2></div><button type="button" onClick={onClose}>×</button></header>
      <label>Date<input type="date" value={day} disabled /></label>
      <div className="time-fields"><label>Start<input type="time" value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>End<input type="time" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        <label>Duration<input type="number" min="0.02" step="0.25" value={durationInput(seconds)} onChange={(event) => setDuration(event.target.value)} /></label></div>
      <div className="duration-presets">{[1, 2, 4, 8].map((hours) => <button type="button" key={hours} onClick={() => setDuration(hours)}>{hours}h</button>)}</div>
      <TaskPicker value={task} onChange={setTask} {...taskProps} />
      {error && <p className="tl-error">{error}</p>}
      <footer><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="button" className="primary" onClick={save}>Save TimeLog</button></footer>
    </section>
  </div>
}

function PreferencesModal({ value, onClose, onSave }) {
  const [preferences, setPreferences] = useState(value)
  const zones = useMemo(() => typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : ['Europe/Prague', 'UTC'], [])
  return <div className="modal-backdrop" role="presentation"><section className="log-modal preferences-modal" role="dialog" aria-modal="true" aria-label="TimeLog preferences">
    <header><div><span className="tl-kicker">Artist</span><h2>Preferences</h2></div><button type="button" onClick={onClose}>×</button></header>
    <label>Artist timezone<select value={preferences.artist_timezone} onChange={(event) => setPreferences((current) => ({ ...current, artist_timezone: event.target.value }))}>{zones.map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label>
    <label>Default start hour<input type="time" value={preferences.start_hour} onChange={(event) => setPreferences((current) => ({ ...current, start_hour: event.target.value }))} /></label>
    <label className="preference-check"><input type="checkbox" checked={preferences.assigned_tasks_only} onChange={(event) => setPreferences((current) => ({ ...current, assigned_tasks_only: event.target.checked }))} />Limit task picker to tasks assigned to me</label>
    <footer><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" onClick={() => onSave(preferences)}>Save Preferences</button></footer>
  </section></div>
}

function AdvancedFilters({ filters, setFilters, context, targetUser, setTargetUser, projects }) {
  function update(name, change) { setFilters((current) => ({ ...current, [name]: { ...current[name], ...change } })) }
  const rows = [
    ['project', 'Projects'], ['taskType', 'Task Type'], ['taskName', 'Task Name'],
    ['taskStatus', 'Task Status'], ['folderName', 'Folder Name'], ['folderLabel', 'Folder Label'], ['status', 'TimeLog Status'],
  ]
  return <aside className="filter-panel"><header><span className="tl-kicker">Advanced</span><h2>Filtering</h2></header>
    {rows.map(([name, label]) => <div className="filter-row" key={name}><div><strong>{label}</strong><label><input type="checkbox" checked={filters[name].paused} onChange={(event) => update(name, { paused: event.target.checked })} />Pause</label><label><input type="checkbox" checked={filters[name].invert} onChange={(event) => update(name, { invert: event.target.checked })} />Invert</label></div>
      {name === 'project' ? <select multiple value={filters[name].value} onChange={(event) => update(name, { value: [...event.target.selectedOptions].map((option) => option.value) })}>{projects.map((project) => <option key={project} value={project}>{project}</option>)}</select>
        : name === 'status' ? <select multiple value={filters[name].value} onChange={(event) => update(name, { value: [...event.target.selectedOptions].map((option) => option.value) })}>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          : <input value={filters[name].value} onChange={(event) => update(name, { value: event.target.value })} />}</div>)}
    {context.is_manager && <div className="filter-row"><strong>User</strong><select value={targetUser} onChange={(event) => setTargetUser(event.target.value)}><option value={context.user_name}>Me</option><option value="*">Any User</option>{context.users.filter((name) => name !== context.user_name).map((name) => <option key={name} value={name}>{name}</option>)}</select></div>}
  </aside>
}

function applyFilters(logs, filters) {
  const definitions = {
    project: (log, values) => !values.length || values.includes(log.project_name),
    taskType: (log, value) => String(log.task_type || '').toLowerCase().includes(value.toLowerCase()),
    taskName: (log, value) => String(log.task_name || '').toLowerCase().includes(value.toLowerCase()),
    taskStatus: (log, value) => String(log.task_status || '').toLowerCase().includes(value.toLowerCase()),
    folderName: (log, value) => String(log.folder_name || '').toLowerCase().includes(value.toLowerCase()),
    folderLabel: (log, value) => String(log.folder_label || '').toLowerCase().includes(value.toLowerCase()),
    status: (log, values) => !values.length || values.includes(log.status),
  }
  return logs.filter((log) => Object.entries(definitions).every(([name, matcher]) => {
    const filter = filters[name]; if (filter.paused || (!filter.value.length)) return true
    const match = matcher(log, filter.value); return filter.invert ? !match : match
  }))
}

function SelectionBar({ selectedLogs, canEdit, isManager, targetUser, currentUser, action, allowMerge }) {
  if (!selectedLogs.length) return null
  const editable = selectedLogs.some((log) => ['not_submitted', 'disputed'].includes(log.status))
  const submitted = selectedLogs.every((log) => log.status === 'submitted')
  return <div className="selection-bar"><strong>{selectedLogs.length} selected</strong>
    {canEdit && selectedLogs.length === 1 && <button onClick={() => action('duplicate')}>Duplicate</button>}
    {canEdit && <button onClick={() => action('delete')}>Delete</button>}
    {canEdit && editable && <button className="primary" onClick={() => action('submit')}>Submit Selected</button>}
    {canEdit && allowMerge && <button onClick={() => action('merge')}>Merge</button>}
    {isManager && targetUser !== currentUser && submitted && <><button className="approve" onClick={() => action('approve')}>Approve</button><button className="dispute" onClick={() => action('dispute')}>Dispute</button><button className="reject" onClick={() => action('reject')}>Reject</button></>}
  </div>
}

function TrackerView({ logs, zone, selected, select, canEdit, openEdit, play, submit, taskTotals }) {
  const days = useMemo(() => Object.entries(logs.reduce((result, log) => {
    const day = zonedDay(log.started_at, zone); (result[day] ||= []).push(log); return result
  }, {})).sort(([left], [right]) => right.localeCompare(left)), [logs, zone])
  return <div className="tracker-view">{days.map(([day, dayLogs]) => <section className="tracker-day" key={day}>
    <div className="day-separator"><strong>{new Date(`${day}T12:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</strong><span>{duration(dayLogs.reduce((sum, log) => sum + log.total_seconds, 0))}</span></div>
    {dayLogs.map((log, index) => <article key={log.id} className={`task-card status-${log.status} ${selected.has(log.id) ? 'selected' : ''}`} onClick={(event) => select(log.id, index, event)} onDoubleClick={() => canEdit && log.is_editable && openEdit(log)}>
      <div className="task-thumb">{log.thumbnail_id ? <img src={`${window.location.origin}/api/projects/${encodeURIComponent(log.project_name)}/thumbnails/${log.thumbnail_id}`} /> : <span>{(log.task_name || '?').slice(0, 1).toUpperCase()}</span>}</div>
      <div className="task-main"><span className="status-pill">{STATUS_LABELS[log.status]}</span><h3>{log.task_name || 'Unassigned time'}</h3><p>{[log.project_name, log.folder_path, log.task_type].filter(Boolean).join(' · ')}</p><small>{zonedDateTime(log.started_at, zone)} → {zonedDateTime(log.ended_at, zone)}</small></div>
      <div className="task-metric"><strong>{duration(log.total_seconds)}</strong><span>tracked</span></div>
      <div className="task-metric"><strong>{log.bid_hours ? `${Math.round((((taskTotals[logKey(log)]?.total_seconds || log.total_seconds) / 3600) / log.bid_hours) * 100)}%` : '—'}</strong><span title={taskTotals[logKey(log)] ? `${taskTotals[logKey(log)].user_count} users logged this task` : ''}>{log.bid_hours ? `${log.bid_hours}h bid` : 'No bid'}</span></div>
      {canEdit && <div className="card-actions"><button title="Start another TimeLog" onClick={(event) => { event.stopPropagation(); play(log) }}>▶</button>{['not_submitted', 'disputed'].includes(log.status) && log.ended_at && log.task_name && <button onClick={(event) => { event.stopPropagation(); submit([log.id]) }}>Submit</button>}</div>}
    </article>)}
  </section>)}</div>
}

function TimesheetView({ logs, days, zone, openCreate, canEdit, startHour }) {
  const rows = useMemo(() => Object.values(logs.reduce((result, log) => {
    const key = logKey(log); const row = result[key] ||= { key, sample: log, total: 0, days: {} }; const day = zonedDay(log.started_at, zone)
    row.total += log.total_seconds; (row.days[day] ||= []).push(log); return result
  }, {})), [logs, zone])
  const dayTotals = Object.fromEntries(days.map((day) => [isoDay(day), logs.filter((log) => zonedDay(log.started_at, zone) === isoDay(day)).reduce((sum, log) => sum + log.total_seconds, 0)]))
  function newCellLog(day, sample) {
    const key = isoDay(day); const existing = logs.filter((log) => zonedDay(log.started_at, zone) === key && log.ended_at)
    const latest = existing.sort((left, right) => new Date(right.ended_at) - new Date(left.ended_at))[0]
    const start = latest ? zonedTime(latest.ended_at, zone) : startHour
    const startDate = new Date(zonedLocalToUtc(key, start, zone)); const endDate = new Date(startDate.getTime() + 3600000)
    return { ...sample, id: null, started_at: startDate.toISOString(), ended_at: endDate.toISOString() }
  }
  return <div className="timesheet-scroll"><table className="timesheet"><thead><tr><th className="frozen thumbnail">Thumb</th><th className="frozen identity">Project / Folder / Task</th><th className="frozen bid">Bid</th><th className="frozen mine">My Total</th>{days.map((day) => <th key={isoDay(day)}>{day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.key}><td className="frozen thumbnail">{row.sample.thumbnail_id ? '▣' : '—'}</td><td className="frozen identity"><strong>{row.sample.task_name || 'Unassigned'}</strong><span>{row.sample.project_name} {row.sample.folder_path}</span></td><td className="frozen bid">{row.sample.bid_hours ? `${row.sample.bid_hours}h` : '—'}</td><td className="frozen mine">{duration(row.total)}</td>{days.map((day) => { const key = isoDay(day); const cell = row.days[key] || []; return <td className="day-cell" key={key} onDoubleClick={() => canEdit && openCreate(cell.length === 1 ? cell[0] : newCellLog(day, row.sample))}>{cell.length ? <><strong>{duration(cell.reduce((sum, log) => sum + log.total_seconds, 0))}</strong><span>{zonedTime(cell[0].started_at, zone)}–{zonedTime(cell[cell.length - 1].ended_at, zone)}</span></> : <button type="button" disabled={!canEdit} onClick={() => openCreate(newCellLog(day, row.sample))}>＋</button>}</td>})}</tr>)}</tbody>
    <tfoot><tr><th className="frozen thumbnail" /><th className="frozen identity">Totals</th><th className="frozen bid" /><th className="frozen mine">{duration(logs.reduce((sum, log) => sum + log.total_seconds, 0))}</th>{days.map((day) => <th key={isoDay(day)}>{duration(dayTotals[isoDay(day)])}</th>)}</tr></tfoot></table></div>
}

function laneLayout(logs) {
  const sorted = [...logs].sort((a, b) => new Date(a.started_at) - new Date(b.started_at)); const lanes = []
  return sorted.map((log) => { let lane = lanes.findIndex((end) => end <= new Date(log.started_at).getTime()); if (lane < 0) { lane = lanes.length; lanes.push(0) } lanes[lane] = new Date(log.ended_at || Date.now()).getTime(); return { log, lane, count: lanes.length } })
}

function mergeLayerSegments(logs) {
  const sorted = [...logs].sort((left, right) => new Date(left.started_at) - new Date(right.started_at)); const merged = []
  sorted.forEach((log) => { const previous = merged[merged.length - 1]; if (previous && new Date(log.started_at) <= new Date(previous.ended_at)) { if (new Date(log.ended_at) > new Date(previous.ended_at)) previous.ended_at = log.ended_at; previous.foreground_application ||= log.foreground_application; previous.foreground_title ||= log.foreground_title } else merged.push({ ...log, id: `${log.id}-${merged.length}` }) })
  return merged
}

function CalendarView({ logs, activity, autoLogs, days, zone, selected, select, canEdit, openEdit, openCreate, update }) {
  const [showActivity, setShowActivity] = useState(true); const [showAuto, setShowAuto] = useState(true); const [pxHour, setPxHour] = useState(64); const [columnSize, setColumnSize] = useState('medium')
  const drag = useRef(null); const calendarRef = useRef(null); const today = zonedDay(new Date(), zone)
  function minuteOf(value) { const part = zonedParts(value, zone); return +part.hour * 60 + +part.minute }
  function beginMove(event, log, mode = 'move') {
    if (!canEdit || !log.is_editable) return; event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { y: event.clientY, log, mode }
  }
  async function endMove(event) {
    if (!drag.current) return; event.stopPropagation(); const current = drag.current; drag.current = null
    if (current.mode === 'create') {
      const first = Math.max(0, Math.min(1439, Math.round(((current.y - current.top) / pxHour) * 4) * 15))
      const second = Math.max(0, Math.min(1439, Math.round(((event.clientY - current.top) / pxHour) * 4) * 15))
      const startMinute = Math.min(first, second); const endMinute = Math.max(startMinute + 15, Math.max(first, second))
      const start = `${pad(Math.floor(startMinute / 60))}:${pad(startMinute % 60)}`; const end = `${pad(Math.floor(endMinute / 60))}:${pad(endMinute % 60)}`
      const candidate = { started_at: zonedLocalToUtc(current.day, start, zone), ended_at: zonedLocalToUtc(current.day, end, zone) }
      if (!logs.some((other) => overlaps(candidate, other))) openCreate(candidate)
      return
    }
    const { y, log, mode } = current
    const delta = Math.round(((event.clientY - y) / pxHour) * 4) * 15; if (!delta) return
    let start = new Date(log.started_at); let end = new Date(log.ended_at)
    if (mode !== 'end') start = new Date(start.getTime() + delta * 60000)
    if (mode !== 'start') end = new Date(end.getTime() + delta * 60000)
    if (end <= start || zonedDay(start, zone) !== zonedDay(log.started_at, zone) || zonedDay(end, zone) !== zonedDay(log.started_at, zone)) return
    const candidate = { ...log, started_at: start.toISOString(), ended_at: end.toISOString() }
    if (logs.some((other) => other.id !== log.id && overlaps(candidate, other))) return
    await update(log.id, { started_at: candidate.started_at, ended_at: candidate.ended_at })
  }
  function beginCreate(event, day) {
    if (!canEdit || isoDay(day) > today || event.target !== event.currentTarget) return
    event.currentTarget.setPointerCapture(event.pointerId); const rect = event.currentTarget.getBoundingClientRect()
    drag.current = { mode: 'create', y: event.clientY, top: rect.top, day: isoDay(day) }
  }
  const side = (showActivity ? 10 : 0) + (showAuto ? 20 : 0)
  return <div className="calendar-shell"><div className="calendar-tools"><button onClick={() => setPxHour(48)}>Frame All</button><button className={showActivity ? 'active' : ''} onClick={() => setShowActivity(!showActivity)}>Activity</button><button className={showAuto ? 'active' : ''} onClick={() => setShowAuto(!showAuto)}>AutoLog</button><select value={columnSize} onChange={(event) => setColumnSize(event.target.value)}><option value="small">Small columns</option><option value="medium">Medium columns</option><option value="large">Large columns</option></select><strong>Total {duration(logs.reduce((sum, log) => sum + log.total_seconds, 0))}</strong></div>
    <div className={`calendar-grid-view columns-${columnSize}`} ref={calendarRef} onWheel={(event) => { if (event.ctrlKey) return; event.preventDefault(); setPxHour((value) => Math.max(36, Math.min(144, value + (event.deltaY < 0 ? 8 : -8)))) }}>
      <div className="hour-axis"><div className="calendar-header" />{Array.from({ length: 24 }, (_, hour) => <div className="hour-label" style={{ height: pxHour }} key={hour}>{pad(hour)}:00</div>)}</div>
      {days.map((day) => { const key = isoDay(day); const userDay = logs.filter((log) => zonedDay(log.started_at, zone) === key); const autoDay = autoLogs.filter((log) => zonedDay(log.started_at, zone) === key); const activityDay = mergeLayerSegments(activity.filter((log) => zonedDay(log.started_at, zone) === key)); const lanes = laneLayout(userDay); const laneCount = Math.max(1, ...lanes.map((item) => item.count)); return <section className={`calendar-column ${key === today ? 'today' : ''} ${key > today ? 'future' : ''}`} key={key}>
        <header className="calendar-header"><strong>{day.toLocaleDateString(undefined, { weekday: 'long' })}</strong><span>{day.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span><small>{duration(userDay.reduce((sum, log) => sum + log.total_seconds, 0))}</small></header>
        <div className="calendar-day-body" style={{ height: pxHour * 24 }} onPointerDown={(event) => beginCreate(event, day)} onPointerUp={endMove}>
          {showActivity && activityDay.map((item) => <div key={`a${item.id}`} className="calendar-segment activity-segment" title={`${zonedTime(item.started_at, zone)}–${zonedTime(item.ended_at, zone)} · ${item.foreground_application || ''} · ${item.foreground_title || ''}`} style={{ top: minuteOf(item.started_at) / 60 * pxHour, height: Math.max(3, item.total_seconds ? item.total_seconds / 3600 * pxHour : (new Date(item.ended_at) - new Date(item.started_at)) / 3600000 * pxHour), left: 0, width: '10%' }} />)}
          {showAuto && autoDay.map((item) => <div key={`t${item.id}`} className="calendar-segment auto-segment" title={`${taskLabel(item)} · ${item.dcc_name || ''} ${item.dcc_version || ''} · ${item.workfile_name || ''}`} style={{ top: minuteOf(item.started_at) / 60 * pxHour, height: Math.max(3, (new Date(item.ended_at || Date.now()) - new Date(item.started_at)) / 3600000 * pxHour), left: `${showActivity ? 10 : 0}%`, width: '20%' }} />)}
          {lanes.map(({ log, lane }) => <div key={log.id} className={`calendar-segment user-segment status-${log.status} ${selected.has(log.id) ? 'selected' : ''}`} title={`${taskLabel(log)} · ${duration(log.total_seconds)} · ${zonedTime(log.started_at, zone)}–${zonedTime(log.ended_at, zone)}`} style={{ top: minuteOf(log.started_at) / 60 * pxHour, height: Math.max(18, log.total_seconds / 3600 * pxHour), left: `calc(${side}% + ${(100 - side) / laneCount * lane}%)`, width: `calc(${(100 - side) / laneCount}% - 3px)` }} onClick={(event) => { event.stopPropagation(); select(log.id, userDay.indexOf(log), event) }} onDoubleClick={() => canEdit && log.is_editable && openEdit(log)} onPointerDown={(event) => beginMove(event, log)} onPointerUp={endMove}>
            <button className="resize top" aria-label="Resize start" onPointerDown={(event) => beginMove(event, log, 'start')} onPointerUp={endMove} /><strong>{log.folder_name || log.project_name || 'Unassigned'}</strong><span>{log.task_name || 'TimeLog'}</span><small>{duration(log.total_seconds)}</small><button className="resize bottom" aria-label="Resize end" onPointerDown={(event) => beginMove(event, log, 'end')} onPointerUp={endMove} />
          </div>)}
        </div></section> })}
    </div></div>
}

function emptyFilters() { return Object.fromEntries(['project', 'taskType', 'taskName', 'taskStatus', 'folderName', 'folderLabel', 'status'].map((name) => [name, { value: ['project', 'status'].includes(name) ? [] : '', paused: false, invert: false }])) }

export default function TimeLogApp({ ayonContext }) {
  const [context, setContext] = useState(null); const [data, setData] = useState({ timelogs: [], activity: [], auto_logs: [] }); const [error, setError] = useState('')
  const [view, setView] = useState('tracker'); const [preset, setPreset] = useState('this_week'); const [range, setRange] = useState(rangeFor('this_week')); const [zoneMode, setZoneMode] = useState('studio')
  const [targetUser, setTargetUser] = useState(''); const [showFilters, setShowFilters] = useState(false); const [filters, setFilters] = useState(emptyFilters)
  const [selected, setSelected] = useState(new Set()); const [lastIndex, setLastIndex] = useState(null); const [modal, setModal] = useState(null); const [preferencesOpen, setPreferencesOpen] = useState(false); const [pickerTask, setPickerTask] = useState({ project_name: ayonContext?.projectName || '' }); const [, setTick] = useState(0)
  useEffect(() => { axios.get('/timelog/context').then(({ data: value }) => { setContext(value); setTargetUser(value.user_name); setRange(rangeFor('this_week', value.week_start)) }).catch((requestError) => setError(requestError.message)) }, [])
  const zone = validZone(zoneMode === 'studio' ? context?.studio_timezone : zoneMode === 'tray' ? (data.tray_timezone || context?.tray_timezone) : context?.preferences?.artist_timezone, context?.studio_timezone)
  async function refresh() {
    if (!targetUser) return
    try {
      const names = targetUser === '*' ? context.users : [targetUser]
      const responses = await Promise.all(names.map((name) => axios.get('/timelog/data', { params: { from: isoDay(range.start), to: isoDay(range.end), user_name: name } })))
      setData(responses.length === 1 ? responses[0].data : {
        user_name: '*', timelogs: responses.flatMap((response) => response.data.timelogs || []),
        activity: responses.flatMap((response) => response.data.activity || []), auto_logs: responses.flatMap((response) => response.data.auto_logs || []), running: null, tray_timezone: null, task_totals: responses[0]?.data.task_totals || [],
      }); setError('')
    } catch (requestError) { setError(requestError.response?.data?.detail || requestError.message) }
  }
  useEffect(() => { refresh() }, [targetUser, range.start.getTime(), range.end.getTime()])
  useEffect(() => { const timer = window.setInterval(() => setTick((value) => value + 1), 1000); return () => window.clearInterval(timer) }, [])
  const filtered = useMemo(() => applyFilters(data.timelogs || [], filters), [data.timelogs, filters]); const days = useMemo(() => eachDay(range.start, range.end), [range]); const canEdit = targetUser === context?.user_name
  const taskTotals = useMemo(() => Object.fromEntries((data.task_totals || []).map((item) => [[item.project_name, item.folder_path, item.task_name].join('|'), item])), [data.task_totals])
  const selectedLogs = filtered.filter((log) => selected.has(log.id)); const projects = [...new Set((data.timelogs || []).map((log) => log.project_name).filter(Boolean))].sort()
  const taskProps = { userName: context?.user_name, assignedOnly: context?.preferences?.assigned_tasks_only, projectHint: ayonContext?.projectName, bidAttribute: context?.bid_attribute }
  function select(id, index, event) {
    setSelected((current) => { const next = new Set(event.ctrlKey || event.metaKey ? current : []); if (event.shiftKey && lastIndex !== null) { const [from, to] = [lastIndex, index].sort((a, b) => a - b); filtered.slice(from, to + 1).forEach((log) => next.add(log.id)) } else if ((event.ctrlKey || event.metaKey) && next.has(id)) next.delete(id); else next.add(id); return next }); setLastIndex(index)
  }
  async function saveLog(payload) { if (modal?.id) await axios.patch(`/timelog/entries/${modal.id}`, payload); else await axios.post('/timelog/entries', payload); setModal(null); await refresh() }
  async function updateLog(id, payload) { await axios.patch(`/timelog/entries/${id}`, payload); await refresh() }
  async function submit(ids) { await axios.post('/timelog/submit', { ids }); setSelected(new Set()); await refresh() }
  async function selectionAction(action) {
    const ids = selectedLogs.map((log) => log.id)
    if (action === 'delete' && window.confirm(`Delete ${ids.length} selected TimeLog${ids.length === 1 ? '' : 's'}?`)) await axios.post('/timelog/delete', { ids })
    else if (action === 'duplicate') await axios.post(`/timelog/duplicate/${ids[0]}`)
    else if (action === 'submit') await submit(ids.filter((id) => selectedLogs.find((log) => log.id === id)?.is_editable))
    else if (action === 'merge' && window.confirm('Merge selected TimeLogs into the earliest record?')) await axios.post('/timelog/merge', { ids })
    else if (['approve', 'dispute', 'reject'].includes(action)) await axios.post('/timelog/review', { ids, status: { approve: 'approved', dispute: 'disputed', reject: 'rejected' }[action] })
    setSelected(new Set()); await refresh()
  }
  async function toggleTimer() {
    if (data.running) await axios.post('/timelog/timer/stop')
    else await axios.post('/timelog/entries', { ...pickerTask, started_at: new Date().toISOString(), ended_at: null })
    await refresh()
  }
  async function play(log) { if (data.running) await axios.post('/timelog/timer/stop'); await axios.post('/timelog/entries', { ...log, id: undefined, started_at: new Date().toISOString(), ended_at: null }); await refresh() }
  async function savePreferences(preferences) { const response = await axios.put('/timelog/preferences', preferences); setContext((current) => ({ ...current, preferences: response.data.preferences })); setPreferencesOpen(false) }
  function createFromSelection() { const seed = selectedLogs.length === 1 ? selectedLogs[0] : pickerTask; setModal({ ...seed, id: null, started_at: new Date().toISOString(), ended_at: new Date(Date.now() + 3600000).toISOString() }) }
  function createFromCalendar(initial) { const start = new Date(initial.started_at); const previous = [...filtered].filter((log) => new Date(log.ended_at || Date.now()) <= start).sort((left, right) => new Date(right.ended_at) - new Date(left.ended_at))[0]; setModal({ ...(previous || pickerTask), id: null, ...initial }) }
  function choosePreset(value) { setPreset(value); if (value !== 'custom') setRange(rangeFor(value, context?.week_start)) }
  if (!context) return <main className="timelog-page"><div className="tl-loading">Loading Presence TimeLog…</div></main>
  const runningSeconds = data.running ? (Date.now() - new Date(data.running.started_at).getTime()) / 1000 : 0
  return <main className="timelog-page"><header className="tl-page-header"><div><span className="tl-kicker">Presence</span><h1>TimeLog</h1><p>Shape automatic activity into an accurate, reviewable record.</p></div><div className="timezone-toggle" aria-label="Display timezone">{['studio', 'tray', 'artist'].map((mode) => <button className={zoneMode === mode ? 'active' : ''} key={mode} onClick={() => setZoneMode(mode)}>{mode[0].toUpperCase() + mode.slice(1)} Time</button>)}</div></header>
    {error && <div className="tl-error">{error}</div>}
    <section className="live-tracker"><TaskPicker value={data.running || pickerTask} onChange={setPickerTask} {...taskProps} /><div className="live-counter"><span>{data.running ? 'Tracking now' : 'Ready to track'}</span><strong>{duration(data.running ? runningSeconds : 0)}</strong></div><button disabled={!canEdit} className={`tracker-button ${data.running ? 'stop' : 'start'}`} onClick={toggleTimer}>{data.running ? '■ Stop' : '▶ Start'}</button></section>
    <section className="timelog-controls"><div className="view-tabs">{[['tracker', 'Tracker'], ['timesheet', 'Timesheet'], ['calendar', 'Calendar']].map(([name, label]) => <button className={view === name ? 'active' : ''} key={name} onClick={() => setView(name)}>{label}</button>)}</div>
      <div className="range-controls"><select value={preset} onChange={(event) => choosePreset(event.target.value)}>{PRESETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button aria-label="Previous start date" onClick={() => { setPreset('custom'); setRange((current) => ({ ...current, start: addDays(current.start, -1) })) }}>‹</button><input aria-label="Start date" type="date" value={isoDay(range.start)} onChange={(event) => { setPreset('custom'); setRange((current) => ({ ...current, start: dayAtNoon(new Date(`${event.target.value}T12:00`)) })) }} /><button aria-label="Next start date" onClick={() => { setPreset('custom'); setRange((current) => ({ ...current, start: addDays(current.start, 1) })) }}>›</button><span>→</span><button aria-label="Previous end date" onClick={() => { setPreset('custom'); setRange((current) => ({ ...current, end: addDays(current.end, -1) })) }}>‹</button><input aria-label="End date" type="date" value={isoDay(range.end)} onChange={(event) => { setPreset('custom'); setRange((current) => ({ ...current, end: dayAtNoon(new Date(`${event.target.value}T12:00`)) })) }} /><button aria-label="Next end date" onClick={() => { setPreset('custom'); setRange((current) => ({ ...current, end: addDays(current.end, 1) })) }}>›</button></div>
      <button className="secondary" disabled={!canEdit} onClick={createFromSelection}>＋ Create TimeLog</button><button onClick={() => setPreferencesOpen(true)}>Preferences</button><button className={showFilters ? 'active' : ''} onClick={() => setShowFilters(!showFilters)}>Filters</button></section>
    <SelectionBar selectedLogs={selectedLogs} canEdit={canEdit} isManager={context.is_manager} targetUser={targetUser} currentUser={context.user_name} action={selectionAction} allowMerge={view === 'calendar' && selectedLogs.length > 1 && new Set(selectedLogs.map((log) => zonedDay(log.started_at, zone))).size === 1} />
    <div className="timelog-workspace"><section className="timelog-content">{view === 'tracker' && <TrackerView logs={filtered} zone={zone} selected={selected} select={select} canEdit={canEdit} openEdit={setModal} play={play} submit={submit} taskTotals={taskTotals} />}{view === 'timesheet' && <TimesheetView logs={filtered} days={days} zone={zone} openCreate={setModal} canEdit={canEdit} startHour={context.preferences.start_hour} />}{view === 'calendar' && <CalendarView logs={filtered} activity={data.activity || []} autoLogs={data.auto_logs || []} days={days} zone={zone} selected={selected} select={select} canEdit={canEdit} openEdit={setModal} openCreate={createFromCalendar} update={updateLog} />}</section>
      {showFilters && <AdvancedFilters filters={filters} setFilters={setFilters} context={context} targetUser={targetUser} setTargetUser={(value) => { setTargetUser(value); setSelected(new Set()) }} projects={projects} />}</div>
    {modal && <LogModal initial={modal} zone={zone} taskProps={taskProps} onClose={() => setModal(null)} onSave={saveLog} />}
    {preferencesOpen && <PreferencesModal value={context.preferences} onClose={() => setPreferencesOpen(false)} onSave={savePreferences} />}
  </main>
}
