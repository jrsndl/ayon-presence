import ast
from pathlib import Path


def test_presence_implements_all_tray_lifecycle_methods():
    tree = ast.parse(
        Path("client/ayon_presence/addon.py").read_text(encoding="utf-8")
    )
    required_methods = {"tray_init", "tray_menu", "tray_start", "tray_exit"}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "PresenceAddon":
            continue
        implemented_methods = {
            statement.name
            for statement in node.body
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert required_methods <= implemented_methods
        return

    raise AssertionError("PresenceAddon is not declared")
