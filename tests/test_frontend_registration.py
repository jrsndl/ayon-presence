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
    assert "label: 'Time logged'" in source
    assert "type=\"date\"" in source
    assert "['this_week', 'This Week']" in source
    assert "axios.get('/project-time'" in source


def test_projects_default_date_range_is_configurable():
    settings = Path("server/settings.py").read_text(encoding="utf-8")
    server = Path("server/__init__.py").read_text(encoding="utf-8")

    assert 'projects_default_date_range: Literal[' in settings
    assert '"projects_default_date_range": "this_week"' in settings
    assert 'self.add_endpoint("project-time"' in server
    assert '"projects_default_date_range": settings.projects_default_date_range' in server


def test_dashboard_is_square_edged_and_uses_available_width():
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert "border-radius: 0 !important" in styles
    assert "main { width: 100%; max-width: none" in styles
    assert ".users-panel table { min-width: 1280px; }" in styles
    assert "td { min-width: 0;" in styles
