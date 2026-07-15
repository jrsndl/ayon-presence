import ast
from pathlib import Path


def test_presence_uses_supported_settings_frontend_scope():
    tree = ast.parse(Path("server/__init__.py").read_text(encoding="utf-8"))

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "PresenceAddon":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "frontend_scopes"
                for target in statement.targets
            ):
                assert ast.literal_eval(statement.value) == {"settings": {}}
                return

    raise AssertionError("PresenceAddon.frontend_scopes is not declared")


def test_all_presence_settings_have_tooltip_descriptions():
    tree = ast.parse(Path("server/settings.py").read_text(encoding="utf-8"))
    settings_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PresenceSettings"
    )
    missing = []
    for statement in settings_class.body:
        if not isinstance(statement, ast.AnnAssign):
            continue
        call = statement.value
        if not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Name) or call.func.id != "SettingsField":
            continue
        descriptions = [
            keyword.value for keyword in call.keywords if keyword.arg == "description"
        ]
        if not descriptions or not ast.literal_eval(descriptions[0]).strip():
            missing.append(statement.target.id)

    assert missing == []


def test_dashboard_defaults_to_users_subtab_and_exposes_new_columns():
    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "useState('users')" in source
    assert 'role="tablist"' in source
    assert source.count("label: 'DCC'") == 2
    assert "label: 'Workfile'" in source


def test_dashboard_exposes_projects_report_and_date_controls():
    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "Projects <span>{projects.length}</span>" in source
    assert "label: 'Project'" in source
    assert "label: 'Users'" in source
    assert "label: 'User #'" in source
    assert "row.users.join(', ')" in source
    assert "label: 'Time logged'" in source
    assert 'role="dialog"' in source
    assert 'role="grid"' in source
    assert "calendarDays(visibleMonth, weekStart)" in source
    assert "presetRange(value, weekStart)" in source
    assert "weekStart === 'sunday'" in source
    assert "document.addEventListener('mousedown', closeOutside)" in source
    assert ".projects-panel { overflow: visible; }" in Path(
        "frontend/src/styles.css"
    ).read_text(encoding="utf-8")
    assert "['this_week', 'This Week']" in source
    assert "axios.get('/project-time'" in source


def test_projects_default_date_range_is_configurable():
    settings = Path("server/settings.py").read_text(encoding="utf-8")
    server = Path("server/__init__.py").read_text(encoding="utf-8")
    database = Path("server/database.py").read_text(encoding="utf-8")

    assert "projects_default_date_range: Literal[" in settings
    assert '"projects_default_date_range": "this_week"' in settings
    assert 'self.add_endpoint("project-time"' in server
    assert (
        '"projects_default_date_range": settings.projects_default_date_range' in server
    )
    assert "enum_resolver=timezone_enum_resolver" in settings
    assert '"timezone": "Europe/Prague"' in settings
    assert "raw_event_retention_days: int = SettingsField(\n        90" in settings
    assert 'projects_week_start: Literal["monday", "sunday"]' in settings
    assert '"projects_week_start": "monday"' in settings
    assert '"projects_week_start": settings.projects_week_start' in server
    assert "ARRAY_AGG(DISTINCT user_name ORDER BY user_name) AS users" in database
    assert "COUNT(DISTINCT user_name)::integer AS user_count" in database


def test_events_debug_tab_is_lazy_and_configurable():
    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")
    settings = Path("server/settings.py").read_text(encoding="utf-8")
    server = Path("server/__init__.py").read_text(encoding="utf-8")
    database = Path("server/database.py").read_text(encoding="utf-8")

    assert "raw_events_debug_enabled" in settings
    assert 'self.add_endpoint("raw-events"' in server
    assert "Raw event inspection requires manager access" in server
    assert "ORDER BY id DESC" in database
    assert "WHERE ($2::bigint IS NULL OR id < $2)" in database
    assert "Events <span>{events.length}{nextEventCursor ? '+' : ''}</span>" in source
    assert "Load 50 more" in source
    assert 'initialDirection="desc"' in source
    assert "value === null || value === undefined || value === ''" in source


def test_dashboard_is_square_edged_and_uses_available_width():
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert "border-radius: 0 !important" in styles
    assert "main { width: 100%; max-width: none" in styles
    assert ".users-panel table { min-width: 1540px; }" in styles
    assert "td { min-width: 0;" in styles


def test_foreground_reporting_is_opt_in_encrypted_and_visible():
    settings = Path("server/settings.py").read_text(encoding="utf-8")
    database = Path("server/database.py").read_text(encoding="utf-8")
    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert '"foreground_application_enabled": False' in settings
    assert '"foreground_title_enabled": False' in settings
    assert '"foreground_title_max_length": 32' in settings
    assert "enum_resolver=secrets_enum_resolver" in settings
    assert 'exclude={"foreground_title"}' in database
    assert "foreground_title_ciphertext BYTEA" in database
    assert "presence_title_keys" in database
    assert source.count("label: 'Foreground App'") == 2
    assert source.count("label: 'Window Title'") == 2
