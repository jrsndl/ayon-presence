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
