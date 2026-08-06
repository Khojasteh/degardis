"""Read the check codes the diagnostic modules can report, from their source."""

from __future__ import annotations

import ast
import re

from tests.support import REPO_ROOT


# model.py reports no code itself, but defines Diagnostic and Diagnostics, whose
# `code` parameters tell the coverage check which arguments carry a check code.
DIAGNOSTIC_MODULES = (
    "icons.py",
    "model.py",
    "registry.py",
    "resolver.py",
    "validate.py",
    "yamlsource.py",
)

# A check code is a namespace and a hyphenated name. A dotted literal whose name
# is a file suffix is a filename, such as skill.yaml or the desktop.ini a content
# filter names, and not a code.
CHECK_CODE_PATTERN = re.compile(r"[a-z][a-z0-9]*\.[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*")
FILENAME_SUFFIXES = frozenset(
    {"yaml", "yml", "md", "py", "json", "zip", "png", "svg", "ico", "txt", "db", "ini"}
)


def diagnostic_trees() -> dict[str, ast.Module]:
    return {
        name: ast.parse((REPO_ROOT / "degardis" / name).read_text(encoding="utf-8"))
        for name in DIAGNOSTIC_MODULES
    }


def emitted_check_codes() -> set[str]:
    """Every check code the diagnostic modules can report."""
    codes: set[str] = set()
    for tree in diagnostic_trees().values():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if (
                CHECK_CODE_PATTERN.fullmatch(value)
                and value.rsplit(".", 1)[1] not in FILENAME_SUFFIXES
            ):
                codes.add(value)
    return codes


def code_parameter_positions(trees: dict[str, ast.Module]) -> dict[str, int]:
    """Every callable that takes a `code`, and where in its arguments it takes it."""
    positions: dict[str, int] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = [arg.arg for arg in node.args.args if arg.arg != "self"]
                names += [arg.arg for arg in node.args.kwonlyargs]
            elif isinstance(node, ast.ClassDef):
                names = [
                    item.target.id
                    for item in node.body
                    if isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                ]
            else:
                continue
            if "code" in names:
                positions[node.name] = names.index("code")
    return positions


def computed_code_arguments() -> list[str]:
    """Report every check code that is built at runtime instead of written out.

    A code passed on as a name or an attribute is still a literal somewhere in
    these modules, where the coverage check reads it. A code assembled from
    pieces is not, so the coverage check cannot see it and it is reported here.
    """
    trees = diagnostic_trees()
    positions = code_parameter_positions(trees)
    computed: list[str] = []
    for name, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            index = positions.get(called)
            if index is None:
                continue
            argument = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "code"),
                node.args[index] if len(node.args) > index else None,
            )
            if argument is None or isinstance(argument, (ast.Name, ast.Attribute)):
                continue
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                continue
            computed.append(f"{name}:{node.lineno} passes {type(argument).__name__}")
    return computed
