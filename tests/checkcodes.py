"""Read the check codes the diagnostic modules can report, from their source."""

from __future__ import annotations

import ast
import re

from tests.support import REPO_ROOT


# Every module that can report a finding. model.py reports no code itself, but
# defines Diagnostic, Diagnostics, and the errors, whose `code` parameters tell
# the coverage check which arguments carry a check code. build.py collects
# nothing, and is listed because the one failure it raises before any check runs
# — an output path overlapping a source — still names a code an author can look
# up.
DIAGNOSTIC_MODULES = (
    "build.py",
    "content.py",
    "dexpr.py",
    "graph.py",
    "icons.py",
    "lowering.py",
    "model.py",
    "registry.py",
    "render.py",
    "sources.py",
    "validate.py",
    "yamlsource.py",
)

# A check code is a namespace and a hyphenated name. A dotted literal whose name
# is a file suffix is a filename, such as skill.yaml or the desktop.ini a content
# filter names, and not a code.
CHECK_CODE_PATTERN = re.compile(r"[a-z][a-z0-9]*\.[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*")
FILENAME_SUFFIXES = frozenset(
    {
        "yaml",
        "yml",
        "md",
        "markdown",
        "py",
        "json",
        "zip",
        "png",
        "svg",
        "ico",
        "txt",
        "db",
        "ini",
    }
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


def code_parameter_positions(trees: dict[str, ast.Module]) -> dict[str, set[int]]:
    """Every callable that takes a `code`, and where in its arguments it takes it.

    A name can carry more than one position, because two classes may each
    declare a method of that name with a `code` parameter in a different place
    — `Diagnostics.error(message, code)` and a mode's own
    `error(workflow, message, code)`. A call site names the method and not its
    class, so every candidate position is kept and a positional argument counts
    as computed only where it is computed at all of them.
    """
    positions: dict[str, set[int]] = {}
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
                positions.setdefault(node.name, set()).add(names.index("code"))
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
            indices = positions.get(called)
            if indices is None:
                continue
            keyed = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "code"),
                None,
            )
            candidates = (
                [keyed]
                if keyed is not None
                else [
                    node.args[index]
                    for index in sorted(indices)
                    if len(node.args) > index
                ]
            )
            if not candidates or any(_written_out(item) for item in candidates):
                continue
            computed.append(
                f"{name}:{node.lineno} passes {type(candidates[0]).__name__}"
            )
    return computed


def _written_out(argument: ast.expr) -> bool:
    """Whether one argument leaves a check code the coverage check can read.

    A literal is read directly. A name or an attribute is a code that is a
    literal somewhere else in these modules, where the same scan finds it.
    """
    if isinstance(argument, (ast.Name, ast.Attribute)):
        return True
    if isinstance(argument, ast.BoolOp):
        # `code or self.code` picks between two codes, each written out where
        # it is set, so the scan still finds both.
        return all(_written_out(value) for value in argument.values)
    return isinstance(argument, ast.Constant) and isinstance(argument.value, str)
