from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import yaml
from PIL import Image

from degardis import __version__
from degardis.build import SkillCompiler, build_skills
from degardis.cli import main, parser
from degardis.model import DegardisError, DegardisWarning
from degardis.package import ArtifactWriter
from degardis.registry import discover_skill_paths, load_profile, load_skill_path
from degardis.resolver import collect_skills
from degardis.validate import validate


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "skills" / "demo"
CANONICAL_EXAMPLE = REPO_ROOT / "examples" / "structured-summary"


def zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def zip_text(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def folder_names(path: Path) -> set[str]:
    return {
        entry.relative_to(path).as_posix()
        for entry in path.rglob("*")
        if entry.is_file()
    }


def folder_text(path: Path, name: str) -> str:
    return (path / name).read_text(encoding="utf-8")


def copy_skills(destination: Path) -> Path:
    root = destination / "demo"
    shutil.copytree(FIXTURES, root)
    return root


def write_raster_icon(
    path: Path,
    color: tuple[int, int, int, int],
    *,
    format_name: str = "PNG",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 192), color)
    if format_name == "ICO":
        image = Image.new("RGBA", (256, 256), color)
        image.save(
            path,
            format=format_name,
            sizes=[(32, 32), (128, 128), (256, 256)],
        )
    else:
        image.save(path, format=format_name)


def set_interface_icons(root: Path, skill_name: str, **icons: str) -> None:
    source = root / skill_name / "skill.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data["interface"].update(icons)
    source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def make_skill_markdown_cross_warning_boundary(root: Path) -> None:
    workflow = root / "gamma" / "workflows" / "run.yaml"
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    data["steps"][0]["instruction"] = "\n".join(["Line"] * 480)
    workflow.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    profile = root / "gamma" / "profiles" / "extra.yaml"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "extra",
                "label": "Extra",
                "description": "Use this extra profile.",
                "instructions": ["Apply the extra profile."],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


class CliTests(unittest.TestCase):
    def test_source_and_output_paths_use_the_same_normalization(self):
        args = parser().parse_args(
            [
                "build",
                "relative-source",
                "--output",
                "relative-output",
            ]
        )

        self.assertEqual(Path("relative-source").resolve(), args.paths[0])
        self.assertEqual(Path("relative-output").resolve(), args.output)

    def test_help_describes_skill_paths_without_removed_commands(self):
        help_text = parser().format_help()
        self.assertIn("self-contained agent skills", help_text)
        self.assertIn("examples/structured-summary", help_text)
        self.assertNotIn("--suite", help_text)
        self.assertNotIn("route", help_text)

    def test_version_option_displays_the_tool_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual(f"degardis {__version__}\n", stdout.getvalue())

    def test_build_accepts_collection_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual(3, len([p for p in output.iterdir() if p.is_dir()]))
            report = stdout.getvalue()
            self.assertIn("Build\n", report)
            self.assertIn("[BUILT] Alpha (alpha)", report)
            self.assertIn("[BUILT] Beta (beta)", report)
            self.assertIn("[BUILT] Gamma (gamma)", report)
            self.assertIn("Summary: 3 skills built as folders.", report)

    def test_build_recursively_discovers_nested_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            nested = root / "teams" / "editing"
            nested.mkdir(parents=True)
            (root / "beta").rename(nested / "beta")
            (root / "gamma").rename(root / "teams" / "gamma")
            output = Path(directory) / "artifacts"

            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["build", str(root), "--output", str(output)])

            self.assertEqual(0, code)
            self.assertEqual(
                {"alpha", "beta", "gamma"},
                {path.name for path in output.iterdir()},
            )

    def test_build_requires_output(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser().parse_args(["build", str(FIXTURES)])

        self.assertEqual(2, raised.exception.code)
        self.assertIn(
            "the following arguments are required: --output",
            stderr.getvalue(),
        )

    def test_build_accepts_zip_option(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES),
                        "--output",
                        str(output),
                        "--zip",
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual(3, len(list(output.glob("*.zip"))))
            self.assertIn(
                "Summary: 3 skills built as archives.",
                stdout.getvalue(),
            )

    def test_build_allows_all_profile_when_skill_has_none(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "gamma"),
                        "--profile",
                        "all",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(0, code)
            self.assertTrue((output / "gamma" / "SKILL.md").is_file())

    def test_build_reports_domain_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifacts"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "gamma"),
                        "--profile",
                        "al",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(1, code)
            self.assertEqual(
                "[ERROR] Profile selector matched no selected skill: al\n",
                stderr.getvalue(),
            )
            self.assertFalse(output.exists())

    def test_malformed_yaml_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            manifest.write_text("name: alpha\ninterface: [\n", encoding="utf-8")

            for command in ("list", "validate", "build"):
                with self.subTest(command=command):
                    stderr = io.StringIO()
                    arguments = [command, str(root / "alpha")]
                    if command == "build":
                        arguments.extend(["--output", str(root / "output")])
                    with contextlib.redirect_stderr(stderr):
                        code = main(arguments)

                    self.assertEqual(1, code)
                    self.assertIn("[ERROR]", stderr.getvalue())
                    self.assertIn("Invalid YAML", stderr.getvalue())

    def test_filesystem_error_is_reported_without_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(
            SkillCompiler,
            "build",
            side_effect=PermissionError("injected permission failure"),
        ):
            with contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "build",
                        str(FIXTURES / "alpha"),
                        "--output",
                        "unused",
                    ]
                )

        self.assertEqual(1, code)
        self.assertEqual(
            "[ERROR] injected permission failure\n",
            stderr.getvalue(),
        )

    def test_list_accepts_multiple_explicit_skills(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(
                [
                    "list",
                    str(FIXTURES / "alpha"),
                    str(FIXTURES / "gamma"),
                ]
            )
        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("Skills (2)", report)
        self.assertIn("Alpha (alpha)  v1.0.0", report)
        self.assertIn("Gamma (gamma)  v1.0.0", report)
        self.assertNotIn("Beta (beta)", report)
        self.assertIn("Description", report)
        self.assertIn("Profiles", report)
        self.assertIn("License", report)
        self.assertIn("Copyright", report)
        self.assertIn("Source", report)

    def test_list_reports_whether_skill_uses_scripts(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["list", str(FIXTURES / "alpha"), str(FIXTURES / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertRegex(report, r"Scripts\s+(Yes|No)")

    def test_list_reports_missing_optional_metadata_and_profiles(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["list", str(FIXTURES / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("Skills (1)", report)
        self.assertIn("Profiles    None", report)
        self.assertIn("License     Not specified", report)
        self.assertIn("Copyright   Not specified", report)

    def test_list_reports_legal_metadata_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["license"] = "MIT"
            data["copyright"] = "Copyright (c) Example"
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["list", str(root / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("License     MIT", report)
        self.assertIn("Copyright   Copyright (c) Example", report)

    def test_route_is_not_a_command(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser().parse_args(["route", "anything"])

    def test_validate_command_returns_nonzero_for_invalid_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["missing-profile"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "alpha")])

            self.assertEqual(1, code)
            report = stdout.getvalue()
            self.assertIn("Validation\n", report)
            self.assertIn("[FAIL] Alpha (alpha)", report)
            self.assertIn("1. Unknown default profiles for alpha: missing-profile", report)
            self.assertIn("Summary: 0 passed, 1 failed, 1 total.", report)

    def test_validate_command_reports_each_skill_like_a_test_run(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["validate", str(FIXTURES)])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("[PASS] Alpha (alpha)", report)
        self.assertIn("[PASS] Beta (beta)", report)
        self.assertIn("[PASS] Gamma (gamma)", report)
        self.assertIn("Summary: 3 passed, 0 failed, 3 total.", report)

    def test_validate_reports_oversized_skill_markdown_as_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            make_skill_markdown_cross_warning_boundary(root)
            manifest = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["extra"]
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["validate", str(root / "gamma")])

        self.assertEqual(0, code)
        report = stdout.getvalue()
        self.assertIn("[PASS] Gamma (gamma)", report)
        self.assertIn(
            "Warning: gamma: generated SKILL.md has 507 lines; the recommended",
            report,
        )
        self.assertIn("Warnings: 1.", report)

    def test_build_reports_oversized_selected_output_as_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            make_skill_markdown_cross_warning_boundary(root)
            output = Path(directory) / "output"
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = main(
                    [
                        "build",
                        str(root / "gamma"),
                        "--profile",
                        "all",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(0, code)
            self.assertTrue((output / "gamma" / "SKILL.md").is_file())
            self.assertEqual(
                (
                    "[WARNING] gamma: generated SKILL.md has 507 lines; "
                    "the recommended maximum is 500\n"
                ),
                stderr.getvalue(),
            )


class DiscoveryTests(unittest.TestCase):
    def test_collection_discovers_skill_descendants_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            nested = root / "groups" / "team"
            nested.mkdir(parents=True)
            (root / "beta").rename(nested / "beta")

            paths = discover_skill_paths([root])

            self.assertEqual(
                ["alpha", "gamma", "beta"],
                [path.name for path in paths],
            )

    def test_collection_discovery_stops_at_skill_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            embedded = root / "alpha" / "assets" / "embedded"
            shutil.copytree(root / "beta", embedded)

            paths = discover_skill_paths([root])

            self.assertEqual(
                ["alpha", "beta", "gamma"],
                [path.name for path in paths],
            )

    def test_collection_discovers_immediate_children(self):
        paths = discover_skill_paths([FIXTURES])
        self.assertEqual(["alpha", "beta", "gamma"], [path.name for path in paths])

    def test_explicit_and_collection_inputs_are_deduplicated(self):
        paths = discover_skill_paths([FIXTURES, FIXTURES / "alpha"])
        self.assertEqual(["alpha", "beta", "gamma"], [path.name for path in paths])

    def test_directory_must_match_manifest_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["name"] = "wrong"
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(DegardisError, "does not match"):
                discover_skill_paths([root / "alpha"])


class ResolutionTests(unittest.TestCase):
    def test_each_bundle_contains_exactly_one_skill(self):
        bundles = collect_skills(discover_skill_paths([FIXTURES]))
        self.assertEqual(3, len(bundles))
        for bundle in bundles:
            self.assertEqual([bundle.primary.name], bundle.resolved_names)

    def test_building_one_skill_does_not_pull_another(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "gamma", Path(directory))[0]
            names = folder_names(path)
            self.assertIn("SKILL.md", names)
            self.assertFalse(any("alpha" in name or "beta" in name for name in names))

    def test_profiles_apply_only_to_selected_skills(self):
        paths = discover_skill_paths([FIXTURES])
        bundles = collect_skills(paths, ["shared", "beta:beta-only"])
        selected = {
            bundle.primary.name: {
                profile.name
                for profile in bundle.content(bundle.primary.name).profiles
            }
            for bundle in bundles
        }
        self.assertEqual({"shared"}, selected["alpha"])
        self.assertEqual({"shared", "beta-only"}, selected["beta"])
        self.assertEqual(set(), selected["gamma"])

    def test_qualified_profile_requires_selected_owner(self):
        with self.assertRaisesRegex(DegardisError, "unselected skill"):
            collect_skills([FIXTURES / "alpha"], ["beta:beta-only"])

    def test_default_profiles_are_applied_when_defined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["alpha-only"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            bundles = collect_skills(discover_skill_paths([root]))
            selected = {
                bundle.primary.name: {
                    profile.name
                    for profile in bundle.content(bundle.primary.name).profiles
                }
                for bundle in bundles
            }

            self.assertEqual({"alpha-only"}, selected["alpha"])
            self.assertEqual(set(), selected["beta"])
            self.assertEqual(set(), selected["gamma"])

    def test_unknown_default_profiles_raise_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["profiles"]["defaults"] = ["missing-profile"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            with self.assertRaisesRegex(DegardisError, "Unknown default profiles"):
                collect_skills(discover_skill_paths([root]))

    def test_all_selector_matches_every_available_profile(self):
        bundles = collect_skills(discover_skill_paths([FIXTURES]), ["all"])
        selected = {
            bundle.primary.name: {
                profile.name
                for profile in bundle.content(bundle.primary.name).profiles
            }
            for bundle in bundles
        }

        self.assertEqual({"alpha-only", "shared"}, selected["alpha"])
        self.assertEqual({"beta-only", "shared"}, selected["beta"])
        self.assertEqual(set(), selected["gamma"])

    def test_unknown_named_profile_selector_raises_error(self):
        with self.assertRaisesRegex(DegardisError, "matched no selected skill"):
            collect_skills([FIXTURES / "gamma"], ["missing-profile"])


class ValidationTests(unittest.TestCase):
    def test_fixture_collection_validates(self):
        self.assertEqual([], validate(FIXTURES))

    def test_validate_skill_does_not_mask_internal_compiler_failures(self):
        with mock.patch(
            "degardis.validate.collect_skills",
            side_effect=RuntimeError("injected compiler defect"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "injected compiler defect",
            ):
                validate(FIXTURES / "gamma")

    def test_validate_does_not_mask_internal_discovery_failures(self):
        with mock.patch(
            "degardis.validate.discover_skill_paths",
            side_effect=RuntimeError("injected discovery defect"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "injected discovery defect",
            ):
                validate(FIXTURES)

    def test_validate_collects_expected_discovery_failures(self):
        with mock.patch(
            "degardis.validate.discover_skill_paths",
            side_effect=OSError("injected filesystem failure"),
        ):
            self.assertEqual(
                ["injected filesystem failure"],
                validate(FIXTURES),
            )

    def test_missing_primary_workflow_remains_a_source_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "gamma" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["primary_workflow"] = "gamma.missing"
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(root / "gamma")

            self.assertTrue(
                any(
                    "primary workflow not found: gamma.missing" in error
                    for error in errors
                )
            )

    def test_dependencies_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["dependencies"] = ["beta"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            self.assertTrue(
                any("dependencies is not supported" in error for error in validate(source.parent))
            )

    def test_legal_metadata_fields_must_be_non_empty_strings(self):
        for field, value in (
            ("license", ""),
            ("license", ["Apache-2.0"]),
            ("copyright", ""),
            ("copyright", {"holder": "Example Corp"}),
        ):
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha" / "skill.yaml"
                    data = yaml.safe_load(source.read_text(encoding="utf-8"))
                    data[field] = value
                    source.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    errors = validate(source.parent)

                    self.assertTrue(
                        any(
                            f"{field} must be a non-empty string" in error
                            for error in errors
                        )
                    )
                    with self.assertRaisesRegex(
                        DegardisError,
                        f"{field} must be a non-empty string",
                    ):
                        build_skills(source.parent, root / "output")

    def test_manifest_fields_enforce_documented_types(self):
        cases = (
            (
                "format_version",
                lambda data: data.__setitem__("format_version", "1"),
                "format_version must be an integer",
            ),
            (
                "version",
                lambda data: data.__setitem__("version", 1),
                "version must be a non-empty string",
            ),
            (
                "description",
                lambda data: data.__setitem__("description", ["invalid"]),
                "description must be a non-empty string",
            ),
            (
                "primary_workflow",
                lambda data: data.__setitem__("primary_workflow", 7),
                "primary_workflow must be a non-empty string",
            ),
            (
                "title",
                lambda data: data.__setitem__("title", []),
                "title must be a non-empty string",
            ),
            (
                "entry_kinds",
                lambda data: data.__setitem__("entry_kinds", "policy"),
                "entry_kinds must be a list of strings",
            ),
            (
                "profile_defaults",
                lambda data: data["profiles"].__setitem__("defaults", "extra"),
                "profiles.defaults must be a list of strings",
            ),
            (
                "interface",
                lambda data: data.__setitem__("interface", []),
                "interface must be a mapping",
            ),
            (
                "display_name",
                lambda data: data["interface"].__setitem__("display_name", 123),
                "interface.display_name must be a non-empty string",
            ),
            (
                "brand_color",
                lambda data: data["interface"].__setitem__("brand_color", {}),
                "interface.brand_color must be a non-empty string",
            ),
        )
        for field, mutate, message in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    manifest = root / "gamma" / "skill.yaml"
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                    mutate(data)
                    manifest.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    errors = validate(root / "gamma")

                    self.assertTrue(any(message in error for error in errors))
                    with self.assertRaises(DegardisError):
                        build_skills(root / "gamma", root / "output")
                    self.assertFalse((root / "output").exists())

    def test_unsupported_format_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            data["format_version"] = 2
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(manifest.parent)

            self.assertTrue(
                any(
                    "unsupported format_version 2; supported versions: 1" in error
                    for error in errors
                )
            )

    def test_unsupported_content_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["documents"] = ["documents/*.md"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            errors = validate(source.parent)

            self.assertTrue(
                any(
                    "unsupported content fields: documents" in error
                    for error in errors
                )
            )

    def test_cross_skill_workflow_use_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "workflows" / "run.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["steps"].append({"use": "beta.run"})
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            self.assertTrue(
                any("cross-skill or unknown" in error for error in validate(root / "alpha"))
            )

    def test_duplicate_workflow_ids_are_rejected_by_validate_and_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            duplicate = root / "alpha" / "workflows" / "duplicate.yaml"
            duplicate.write_text(
                "id: alpha.run\nsteps:\n- Repeat the primary workflow.\n",
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(
                any("duplicate workflow id alpha.run" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "duplicate workflow id alpha.run"
            ):
                build_skills(root / "alpha", root / "output")

    def test_malformed_workflow_steps_are_rejected(self):
        invalid_steps = (
            (42, "must be a string or mapping"),
            ({"use": 42}, "use must be a non-empty string"),
            (
                {"use": "alpha.run", "action": "also-run"},
                "use cannot be combined with action or instruction",
            ),
        )
        for step, message in invalid_steps:
            with self.subTest(step=step):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha" / "workflows" / "run.yaml"
                    data = yaml.safe_load(source.read_text(encoding="utf-8"))
                    data["steps"] = [step]
                    source.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    errors = validate(root / "alpha")

                    self.assertTrue(any(message in error for error in errors))
                    with self.assertRaisesRegex(DegardisError, message):
                        build_skills(root / "alpha", root / "output")

    def test_content_globs_must_stay_inside_skill_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            outside = root / "outside.yaml"
            outside.write_text(
                "id: alpha.outside\nrule: Outside content\n",
                encoding="utf-8",
            )
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["entries"] = ["../outside.yaml"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(source.parent)

            self.assertTrue(
                any("content patterns must stay within" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "content patterns must stay within"
            ):
                build_skills(source.parent, root / "output")

    def test_generated_reference_filenames_must_be_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            entries = root / "alpha" / "entries"
            (entries / "hyphen.yaml").write_text(
                "id: alpha.foo-bar\nrule: Hyphen form\n",
                encoding="utf-8",
            )
            (entries / "dot.yaml").write_text(
                "id: alpha.foo.bar\nrule: Dot form\n",
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(any("output path collision" in error for error in errors))
            with self.assertRaisesRegex(DegardisError, "output path collision"):
                build_skills(root / "alpha", root / "output")

    def test_entry_list_fields_reject_scalar_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "entries" / "rule-one.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["require"] = "Do the whole requirement."
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            errors = validate(root / "alpha")

            self.assertTrue(
                any("require must be a list of strings" in error for error in errors)
            )
            with self.assertRaisesRegex(
                DegardisError, "require must be a list of strings"
            ):
                build_skills(root / "alpha", root / "output")

    def test_icon_paths_must_be_non_empty_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            absolute = (root / "icon.png").resolve()
            write_raster_icon(absolute, (255, 0, 0, 255))

            for field, value, message in (
                ("icon", "", "must be a non-empty relative path"),
                ("icon_small", str(absolute), "must be relative"),
                ("icon_large", "missing.png", "icon not found"),
            ):
                with self.subTest(field=field):
                    copied = Path(directory) / f"{field}-skill"
                    shutil.copytree(root / "alpha", copied)
                    manifest = copied / "skill.yaml"
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                    data["name"] = copied.name
                    data["interface"]["default_prompt"] = (
                        f"Use ${copied.name} to run the example."
                    )
                    data["interface"][field] = value
                    manifest.write_text(
                        yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8",
                    )

                    errors = validate(copied)

                    self.assertTrue(any(message in error for error in errors))

    def test_invalid_and_unsafe_icon_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            invalid = root / "invalid.png"
            invalid.write_text("not an image", encoding="utf-8")
            unsafe = root / "unsafe.svg"
            unsafe.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                encoding="utf-8",
            )

            for source, message in (
                ("../invalid.png", "Cannot convert icon source"),
                ("../unsafe.svg", "script is not allowed"),
            ):
                with self.subTest(source=source):
                    set_interface_icons(root, "alpha", icon=source)
                    errors = validate(root / "alpha")
                    self.assertTrue(any(message in error for error in errors))


class BuildTests(unittest.TestCase):
    def test_build_rejects_unsupported_content_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["content"]["unknown"] = ["unknown/**/*"]
            source.write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                DegardisError, "unsupported content fields: unknown"
            ):
                build_skills(source.parent, Path(directory) / "output")

    def test_build_rejects_invalid_interface_before_replacing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            output = root / "output"
            artifact = build_skills(root / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            manifest = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            del data["interface"]
            manifest.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                DegardisError, "interface.display_name is required"
            ):
                build_skills(root / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_folder_writer_failure_preserves_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            stale_zip = output / "alpha.zip"
            stale_zip.write_bytes(b"existing zip")

            with mock.patch(
                "degardis.build.ArtifactWriter.write_skill",
                side_effect=OSError("injected write failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    build_skills(FIXTURES / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))
            self.assertEqual(b"existing zip", stale_zip.read_bytes())

    def test_zip_packager_failure_preserves_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            existing_zip = artifact.read_bytes()
            stale_folder = output / "alpha"
            stale_folder.mkdir()
            marker = stale_folder / "existing.txt"
            marker.write_text("keep", encoding="utf-8")

            with mock.patch(
                "degardis.build.ArchivePackager.create",
                side_effect=OSError("injected package failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected package failure"):
                    build_skills(FIXTURES / "alpha", output, as_zip=True)

            self.assertEqual(existing_zip, artifact.read_bytes())
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_install_copy_failure_restores_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("keep", encoding="utf-8")
            stale_zip = output / "alpha.zip"
            stale_zip.write_bytes(b"existing zip")
            original_copytree = shutil.copytree
            failed = False

            def copytree(source, destination, *args, **kwargs):
                nonlocal failed
                if destination == artifact and not failed:
                    failed = True
                    raise OSError("injected install failure")
                return original_copytree(source, destination, *args, **kwargs)

            with mock.patch(
                "degardis.package.shutil.copytree",
                side_effect=copytree,
            ):
                with self.assertRaisesRegex(OSError, "injected install failure"):
                    build_skills(FIXTURES / "alpha", output)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))
            self.assertEqual(b"existing zip", stale_zip.read_bytes())

    def test_rebuild_does_not_rename_installed_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            artifact = build_skills(FIXTURES / "alpha", output)[0]
            marker = artifact / "existing.txt"
            marker.write_text("replace", encoding="utf-8")

            with mock.patch(
                "degardis.package.Path.replace",
                side_effect=PermissionError("Windows denied directory rename"),
            ):
                rebuilt = build_skills(FIXTURES / "alpha", output)[0]

            self.assertEqual(artifact, rebuilt)
            self.assertFalse(marker.exists())

    def test_build_stages_outside_the_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            compiler = SkillCompiler(FIXTURES / "alpha")
            original_write = compiler.writer.write_skill
            destinations = []

            def write_skill(bundle, destination, skill_name=None):
                destinations.append(destination)
                return original_write(bundle, destination, skill_name)

            with mock.patch.object(
                compiler.writer,
                "write_skill",
                side_effect=write_skill,
            ):
                compiler.build(output)

            self.assertEqual(1, len(destinations))
            self.assertFalse(
                destinations[0].resolve().is_relative_to(output.resolve())
            )

    def test_multi_skill_failure_commits_only_completed_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            build_skills(FIXTURES, output)
            markers = {}
            for name in ("alpha", "beta", "gamma"):
                marker = output / name / "existing.txt"
                marker.write_text("keep", encoding="utf-8")
                markers[name] = marker
            original_write = ArtifactWriter.write_skill

            def write_skill(writer, bundle, destination, skill_name=None):
                if bundle.primary.name == "beta":
                    raise OSError("injected second-skill failure")
                return original_write(writer, bundle, destination, skill_name)

            with mock.patch.object(
                ArtifactWriter,
                "write_skill",
                autospec=True,
                side_effect=write_skill,
            ):
                with self.assertRaisesRegex(
                    OSError, "injected second-skill failure"
                ):
                    build_skills(FIXTURES, output)

            self.assertFalse(markers["alpha"].exists())
            self.assertEqual("keep", markers["beta"].read_text(encoding="utf-8"))
            self.assertEqual("keep", markers["gamma"].read_text(encoding="utf-8"))

    def test_explicit_profiles_warn_for_oversized_selected_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            make_skill_markdown_cross_warning_boundary(root)
            output = Path(directory) / "output"

            with self.assertWarnsRegex(
                DegardisWarning,
                "generated SKILL.md has 507 lines",
            ):
                artifact = SkillCompiler(root / "gamma").build(
                    output,
                    profiles=["all"],
                )[0]

            self.assertTrue(artifact.is_dir())
            self.assertEqual(
                507,
                len(
                    (artifact / "SKILL.md")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
            )

    def test_build_emits_one_flat_folder_per_skill_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = build_skills(FIXTURES, output)
            self.assertEqual(3, len(paths))
            for path in paths:
                self.assertEqual(output / path.name, path)
                self.assertTrue(path.is_dir())

    def test_folder_has_no_target_specific_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory))[0]
            names = folder_names(path)
            self.assertIn("SKILL.md", names)
            self.assertIn("agents/openai.yaml", names)
            self.assertFalse(any(name.startswith(".") for name in names))
            text = folder_text(path, "SKILL.md")
            self.assertNotIn("Related Skills", text)

    def test_legal_metadata_is_emitted_in_spec_compliant_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "skill.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["license"] = "Apache-2.0"
            data["copyright"] = "Copyright 2026 Example Corp"
            source.write_text(
                yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )

            path = build_skills(source.parent, root / "output")[0]
            text = folder_text(path, "SKILL.md")
            frontmatter = yaml.safe_load(text.split("---", 2)[1])

            self.assertEqual("Apache-2.0", frontmatter["license"])
            self.assertEqual(
                "Copyright 2026 Example Corp",
                frontmatter["metadata"]["copyright"],
            )
            self.assertEqual("1.0.0", frontmatter["metadata"]["version"])
            self.assertEqual(
                "degardis/1.0.0",
                frontmatter["metadata"]["generated_by"],
            )
            self.assertNotIn("format_version", frontmatter["metadata"])
            self.assertNotIn("copyright", frontmatter)

    def test_scripts_and_assets_are_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory))[0]
            names = folder_names(path)
            self.assertIn("scripts/greet.py", names)
            self.assertIn("assets/template.md", names)
            text = folder_text(path, "SKILL.md")
            self.assertIn("scripts/greet.py", text)
            self.assertIn("assets/template.md", text)
            self.assertNotIn("## Documents", text)
            self.assertFalse(
                any(name.startswith("references/documents/") for name in names)
            )

    def test_rebuild_replaces_only_selected_skill_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_skills(FIXTURES, output)
            stale_zip = output / "alpha.zip"
            stale_zip.write_text("stale", encoding="utf-8")
            paths = build_skills(FIXTURES / "alpha", output)
            self.assertFalse(stale_zip.exists())
            self.assertTrue((output / "beta" / "SKILL.md").is_file())
            self.assertTrue((output / "gamma" / "SKILL.md").is_file())
            self.assertEqual({"alpha"}, {path.name for path in paths})

    def test_rebuild_replaces_existing_skill_folder_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = build_skills(FIXTURES / "alpha", output)[0]
            stray = path / "stray.md"
            stray.write_text("stray", encoding="utf-8")
            build_skills(FIXTURES / "alpha", output)
            self.assertFalse(stray.exists())

    def test_build_rejects_output_that_overlaps_sources_without_deleting_them(self):
        for output_kind in ("source", "parent"):
            with self.subTest(output_kind=output_kind):
                with tempfile.TemporaryDirectory() as directory:
                    root = copy_skills(Path(directory))
                    source = root / "alpha"
                    output = source if output_kind == "source" else root
                    with self.assertRaisesRegex(
                        DegardisError, "must not overlap skill source"
                    ):
                        build_skills(source, output)
                    self.assertTrue((source / "skill.yaml").is_file())
                    self.assertTrue((source / "scripts" / "greet.py").is_file())

    def test_build_emits_one_zip_archive_per_skill_with_zip_option(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = build_skills(FIXTURES, output, as_zip=True)
            self.assertEqual(3, len(paths))
            for path in paths:
                self.assertEqual(output / f"{path.stem}.zip", path)

    def test_zip_archive_has_no_target_specific_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory), as_zip=True)[0]
            names = zip_names(path)
            self.assertIn("SKILL.md", names)
            self.assertIn("agents/openai.yaml", names)
            self.assertFalse(any(name.startswith(".") for name in names))
            text = zip_text(path, "SKILL.md")
            self.assertNotIn("Related Skills", text)

    def test_scripts_and_assets_are_packaged_in_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_skills(FIXTURES / "alpha", Path(directory), as_zip=True)[0]
            names = zip_names(path)
            self.assertIn("scripts/greet.py", names)
            self.assertIn("assets/template.md", names)
            text = zip_text(path, "SKILL.md")
            self.assertIn("scripts/greet.py", text)
            self.assertIn("assets/template.md", text)
            with zipfile.ZipFile(path) as archive:
                script_mode = archive.getinfo("scripts/greet.py").external_attr >> 16
                asset_mode = archive.getinfo("assets/template.md").external_attr >> 16
            self.assertTrue(script_mode & 0o100)
            self.assertFalse(asset_mode & 0o100)

    def test_zip_rebuild_replaces_only_selected_skill_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_skills(FIXTURES, output, as_zip=True)
            stale_folder = output / "alpha"
            stale_folder.mkdir()
            paths = build_skills(FIXTURES / "alpha", output, as_zip=True)
            self.assertFalse(stale_folder.exists())
            self.assertTrue((output / "beta.zip").is_file())
            self.assertTrue((output / "gamma.zip").is_file())
            self.assertEqual({"alpha"}, {path.stem for path in paths})

    def test_archives_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            content = first.read_bytes()
            second = build_skills(FIXTURES / "alpha", output, as_zip=True)[0]
            self.assertEqual(content, second.read_bytes())
            with zipfile.ZipFile(second) as archive:
                self.assertIsNone(archive.testzip())

    def test_shared_ico_generates_both_icons_for_multiple_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.ico"
            write_raster_icon(shared, (30, 120, 220, 255), format_name="ICO")
            set_interface_icons(root, "alpha", icon="../shared.ico")
            set_interface_icons(root, "beta", icon="../shared.ico")

            paths = build_skills(root, Path(directory) / "output")

            for path in paths[:2]:
                small = path / "assets" / "icon-small.png"
                large = path / "assets" / "icon-large.png"
                self.assertTrue(small.is_file())
                self.assertTrue(large.is_file())
                with Image.open(small) as image:
                    self.assertEqual(("PNG", (32, 32)), (image.format, image.size))
                with Image.open(large) as image:
                    self.assertEqual(("PNG", (256, 256)), (image.format, image.size))
                metadata = yaml.safe_load(
                    folder_text(path, "agents/openai.yaml")
                )["interface"]
                self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
                self.assertEqual("./assets/icon-large.png", metadata["icon_large"])
                self.assertNotIn("icon", metadata)

    def test_explicit_role_overrides_fallback_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            fallback = root / "fallback.png"
            small = root / "alpha" / "small.png"
            write_raster_icon(fallback, (220, 20, 20, 255))
            write_raster_icon(small, (20, 40, 220, 255))
            set_interface_icons(
                root,
                "alpha",
                icon="../fallback.png",
                icon_small="small.png",
            )

            path = build_skills(root / "alpha", root / "output")[0]

            with Image.open(path / "assets" / "icon-small.png") as image:
                self.assertEqual((20, 40, 220, 255), image.getpixel((128, 96)))
            with Image.open(path / "assets" / "icon-large.png") as image:
                self.assertEqual((220, 20, 20, 255), image.getpixel((128, 96)))

    def test_one_explicit_icon_role_does_not_create_the_other(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            small = root / "small.png"
            write_raster_icon(small, (10, 180, 80, 255))
            set_interface_icons(root, "alpha", icon_small="../small.png")

            path = build_skills(root / "alpha", root / "output")[0]

            self.assertTrue((path / "assets" / "icon-small.png").is_file())
            self.assertFalse((path / "assets" / "icon-large.png").exists())
            metadata = yaml.safe_load(
                folder_text(path, "agents/openai.yaml")
            )["interface"]
            self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
            self.assertNotIn("icon_large", metadata)

    def test_svg_icon_is_rendered_to_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            svg = root / "icon.svg"
            svg.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" '
                    'viewBox="0 0 40 20">'
                    '<rect width="40" height="20" fill="#7c3aed"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            set_interface_icons(root, "alpha", icon="../icon.svg")

            path = build_skills(root / "alpha", root / "output")[0]

            with Image.open(path / "assets" / "icon-large.png") as image:
                self.assertEqual(("PNG", (40, 20)), (image.format, image.size))
                self.assertEqual((124, 58, 237, 255), image.getpixel((20, 10)))

    def test_generated_icon_path_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.png"
            generated_path = root / "alpha" / "assets" / "icon-small.png"
            write_raster_icon(shared, (255, 0, 0, 255))
            write_raster_icon(generated_path, (0, 0, 255, 255))
            set_interface_icons(root, "alpha", icon="../shared.png")

            with self.assertRaisesRegex(DegardisError, "output path collision"):
                build_skills(root / "alpha", root / "output")

    def test_generated_icons_are_packaged_in_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            shared = root / "shared.webp"
            write_raster_icon(shared, (90, 40, 180, 255), format_name="WEBP")
            set_interface_icons(root, "alpha", icon="../shared.webp")

            path = build_skills(
                root / "alpha",
                root / "output",
                as_zip=True,
            )[0]

            names = zip_names(path)
            self.assertIn("assets/icon-small.png", names)
            self.assertIn("assets/icon-large.png", names)
            metadata = yaml.safe_load(zip_text(path, "agents/openai.yaml"))[
                "interface"
            ]
            self.assertEqual("./assets/icon-small.png", metadata["icon_small"])
            self.assertEqual("./assets/icon-large.png", metadata["icon_large"])


class StructuredProfileTests(unittest.TestCase):
    def test_external_markdown_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            source = root / "alpha" / "profiles" / "alpha-only.yaml"
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            data["details_files"] = ["details/extra.md"]
            source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            details = source.parent / "details" / "extra.md"
            details.parent.mkdir()
            details.write_text("## Extra\n\nResolved content.\n", encoding="utf-8")
            profile = load_profile(source, "alpha", root / "alpha")
            self.assertIn("## Extra", profile.text)
            self.assertIn("Resolved content.", profile.text)


class CanonicalExampleTests(unittest.TestCase):
    def test_repository_has_one_public_example(self):
        manifests = sorted((REPO_ROOT / "examples").glob("*/skill.yaml"))
        self.assertEqual([CANONICAL_EXAMPLE / "skill.yaml"], manifests)

    def test_example_validates_and_builds_all_documented_features(self):
        self.assertEqual([], validate(CANONICAL_EXAMPLE))
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_skills(
                CANONICAL_EXAMPLE,
                Path(directory),
                profiles=["detailed"],
            )[0]
            names = folder_names(artifact)
            self.assertTrue(
                {
                    "SKILL.md",
                    "agents/openai.yaml",
                    "assets/icon-large.png",
                    "assets/icon-small.png",
                    "assets/template.md",
                    "references/entries/audience.md",
                    "references/entries/fidelity.md",
                    "references/profiles/detailed.md",
                    "references/workflows/inspect.md",
                    "scripts/list_headings.py",
                }.issubset(names)
            )

    def test_example_script_lists_markdown_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "material.md"
            source.write_text(
                "# Subject\n\nContext\n\n## Main point\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(CANONICAL_EXAMPLE / "scripts" / "list_headings.py"),
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                ["Subject", "Main point"],
                result.stdout.splitlines(),
            )


if __name__ == "__main__":
    unittest.main()
