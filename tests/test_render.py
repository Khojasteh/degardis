"""Rendering: compact root, required execution modules, and typed loads.

Expectations here come from the format and from the source under test — the
fixture's own manifest, profiles, and guidance, or the labels `wording.py`
defines — rather than from the renderer. A case that copies a rendered sentence
back records where that sentence currently lives instead of what the document
owes the agent reading it.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from degardis import wording
from degardis.render import MODULE_BUDGET_BYTES, ROOT_BUDGET_BYTES, profile_page

from tests.support import codes, compiled, copy_skills, edit_yaml, write_text


ALPHA = Path("tests/fixtures/skills/demo/alpha")
EXAMPLE = Path("examples/structured-summary")
NODE_HEADING = re.compile(
    r"^### \[`(?P<label>n-[0-9a-f]{10})`\] (?P<command>.+)$",
    re.MULTILINE,
)


def stem(path: str) -> str:
    """How an edge names a module: its filename without directory or suffix."""
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def module_holding(rendered, label: str) -> str:
    """The path of the execution module that renders one node."""
    return next(
        path
        for path, text in rendered.execution_modules.items()
        if f"[`{label}`]" in text
    )


def entry_of(result, workflow_id: str):
    item = next(
        entry for entry in result.lowered.workflows if entry.workflow.id == workflow_id
    )
    return item, next(node for node in item.nodes if node.label == item.entry)


class RootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill, cls.result, cls.diagnostics = compiled(ALPHA)
        cls.rendered = cls.result.rendered
        cls.root = cls.rendered.skill_text
        cls.sources = cls.result.lowered.sources

    def test_frontmatter_carries_the_manifest_identity(self):
        self.assertIn(f"name: {self.skill.name}", self.root)
        self.assertIn(f"description: {self.skill.description}", self.root)

    def test_root_is_a_small_control_plane(self):
        """The root states the contract and the first load, and carries no node.

        A root that inlined a workflow would be paid on every run whether or
        not the agent reached that workflow, which is the cost the whole
        two-layer split exists to avoid.
        """
        self.assertLess(len(self.root.encode("utf-8")), ROOT_BUDGET_BYTES)
        self.assertIn(f"## {wording.CONTRACT_HEADING}", self.root)
        self.assertIn(f"## {wording.START_HEADING}", self.root)
        self.assertNotIn(wording.WORKFLOW_HEADING.format(title=""), self.root)
        self.assertNotRegex(self.root, NODE_HEADING)

    def test_start_names_an_exact_module_entry_and_complete_command(self):
        """Where to begin, in the notation the contract above it defines.

        The start qualifies the entry node by the module holding it and states
        that node's own command, so nothing about the first load is inferred
        from a filename. What loading means, and what to do when it fails, is
        stated once in the contract rather than repeated here.
        """
        _, entry = entry_of(self.result, self.skill.primary_workflow)
        module = module_holding(self.rendered, entry.label)
        start = self.root.split(f"## {wording.START_HEADING}", 1)[1]
        self.assertIn(f"{stem(module)}:{entry.label}", start)
        self.assertIn(entry.command, start)
        self.assertIn("blocked", self.root.split(f"## {wording.START_HEADING}", 1)[0])

    def test_profiles_are_auxiliary_and_the_root_enumerates_none_of_them(self):
        self.assertIn("profiles/index.md", self.root)
        self.assertIn(wording.PROFILES_LEAD, self.root)
        for identifier, profile in self.sources.profiles.items():
            with self.subTest(profile=identifier):
                self.assertNotIn(profile.title, self.root)
                if profile.description:
                    self.assertNotIn(profile.description, self.root)

    def test_one_index_holds_every_profile_the_bundle_ships(self):
        """The catalog is one page, so nothing decides which part to open first.

        The set is compared whole rather than searched, because a page the
        renderer keeps emitting beside the index is exactly what a membership
        check would miss.
        """
        pages = self.rendered.pages
        profiles = self.sources.profiles
        self.assertEqual(
            sorted(
                {
                    "profiles/index.md",
                    *(profile_page(profile, self.skill.root) for profile in profiles.values()),
                }
            ),
            sorted(path for path in pages if path.startswith("profiles/")),
        )

    def test_profile_pages_use_their_source_file_stems(self):
        self.assertEqual(
            {"profiles/index.md", "profiles/quick.md", "profiles/thorough.md"},
            {path for path in self.rendered.pages if path.startswith("profiles/")},
        )

    def test_every_index_row_opens_with_the_link_and_then_the_description(self):
        """The description is optional, so it annotates the link rather than
        leading the row: a profile that declares none still reads as the same
        row, one column of titles, minus its annotation."""
        rows = self.rendered.pages["profiles/index.md"].splitlines()
        for identifier, profile in self.sources.profiles.items():
            target = profile_page(profile, self.skill.root).removeprefix("profiles/")
            link = f"[{profile.title}]({target})"
            row = next((line for line in rows if link in line), "")
            with self.subTest(profile=identifier):
                self.assertTrue(row, f"{identifier} is not linked from the index")
                self.assertTrue(row.startswith(f"- {link}"), row)
                if profile.description:
                    self.assertIn(profile.description, row)
                    self.assertLess(row.index(link), row.index(profile.description))
                else:
                    self.assertEqual(f"- {link}", row)


class ProfileCategoryTests(unittest.TestCase):
    def test_categories_group_only_the_index_when_more_than_one_is_declared(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = copy_skills(Path(directory)) / "alpha"
            _, baseline, _ = compiled(skill)
            for categories, headings in (
                (("", ""), []),
                (("Writing", ""), []),
                (("Writing", "Writing"), []),
                (("Writing", "Analysis"), ["## Analysis", "## Writing"]),
            ):
                with self.subTest(categories=categories):
                    for name, category in zip(("quick", "thorough"), categories):
                        with edit_yaml(skill / "profiles" / f"{name}.yaml") as data:
                            if category:
                                data["category"] = category
                            else:
                                data.pop("category", None)
                    _, result, diagnostics = compiled(skill)
                    self.assertEqual([], diagnostics.errors)
                    index = result.rendered.pages["profiles/index.md"]
                    self.assertEqual(headings, [line for line in index.splitlines() if line.startswith("## ")])
                    if headings:
                        self.assertLess(index.index("## Analysis"), index.index("[Thorough]"))
                        self.assertLess(index.index("[Thorough]"), index.index("## Writing"))
                        self.assertLess(index.index("## Writing"), index.index("[Quick]"))
                    else:
                        self.assertEqual(baseline.rendered.pages["profiles/index.md"], index)
                    self.assertEqual(baseline.rendered.skill_text, result.rendered.skill_text)
                    self.assertEqual(baseline.rendered.execution_modules, result.rendered.execution_modules)
                    self.assertEqual(
                        {path: text for path, text in baseline.rendered.pages.items() if path != "profiles/index.md"},
                        {path: text for path, text in result.rendered.pages.items() if path != "profiles/index.md"},
                    )

            write_text(skill / "profiles" / "general.yaml", "title: General\npoints:\n- Keep it clear.\n")
            write_text(skill / "profiles" / "another.yaml", "title: Another\ncategory: Writing\npoints:\n- Keep it clear.\n")
            _, result, _ = compiled(skill)
            index = result.rendered.pages["profiles/index.md"]
            self.assertLess(index.index("[General]"), index.index("## Analysis"))
            self.assertLess(index.index("## Writing"), index.index("[Another]"))
            self.assertLess(index.index("[Another]"), index.index("[Quick]"))
            self.assertEqual(1, index.count("## Writing"))


class ExecutionModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.result, _ = compiled(ALPHA)
        cls.rendered = cls.result.rendered
        cls.modules = cls.rendered.execution_modules
        cls.all_text = "\n".join(cls.modules.values())

    def test_every_lowered_node_is_rendered_once_in_an_execution_module(self):
        headings = NODE_HEADING.findall(self.all_text)
        labels = [label for label, _ in headings]
        expected = [node.label for node in self.result.lowered.all_nodes()]
        self.assertCountEqual(expected, labels)
        self.assertEqual(len(labels), len(set(labels)))

    def test_debug_provenance_is_not_paid_in_runtime_markdown(self):
        """Full provenance stays on the node for inspection, not in the module."""
        for node in self.result.lowered.all_nodes():
            with self.subTest(node=node.label):
                self.assertNotIn(node.source, self.all_text)

    def test_reads_name_only_the_values_a_node_consumes(self):
        """`Reads` is what the node consumes, not everything live at it.

        A renderer that printed the live set would put values on the line that
        the node never reads, so the rendered lines are compared against the
        lowered nodes' own reads rather than against the absence of a phrase.
        """
        expected = sorted(
            f"**{wording.READS}** " + ", ".join(f"`{name}`" for name in node.available)
            for node in self.result.lowered.all_nodes()
            if node.available
        )
        self.assertTrue(expected)
        rendered = sorted(
            line for line in self.all_text.splitlines() if line.startswith(f"**{wording.READS}** ")
        )
        self.assertEqual(expected, rendered)

    def test_calls_explicitly_load_the_callee_entry(self):
        call = next(
            node for node in self.result.lowered.all_nodes() if node.kind == "call"
        )
        _, entry = entry_of(self.result, call.call_workflow)
        caller = self.modules[module_holding(self.rendered, call.label)]
        target = stem(module_holding(self.rendered, entry.label))
        self.assertIn(f"`{target}:{entry.label}`", caller)
        self.assertIn(entry.command, caller)

    def test_local_transitions_do_not_repeat_destination_commands(self):
        """An edge states its destination command only where a load follows.

        A node in the same module is one heading away, so repeating its
        command buys nothing. A node in another module sits behind a load the
        agent has to decide to perform, which is what the command informs. A
        qualified destination and a stated command therefore go together.
        """
        edges = [line for line in self.all_text.splitlines() if "-> `" in line]
        self.assertTrue(edges)
        for line in edges:
            destination = line.split("-> ", 1)[1]
            with self.subTest(edge=line.strip()[:60]):
                self.assertEqual(":" in destination.split("`")[1], " — " in destination)


class ResourceTests(unittest.TestCase):
    def test_required_resource_use_is_typed_and_fail_closed(self):
        _, result, diagnostics = compiled(EXAMPLE)
        self.assertEqual([], [item for item in diagnostics.records if item.severity == "error"])
        carrying = [
            node for node in result.lowered.all_nodes() if node.resource_operation
        ]
        self.assertTrue(carrying, "the example declares no action resource")
        for node in carrying:
            with self.subTest(node=node.label):
                module = result.rendered.execution_modules[
                    module_holding(result.rendered, node.label)
                ]
                line = next(
                    item
                    for item in module.splitlines()
                    if item.startswith("**Resource** ")
                )
                self.assertIn(f"`{node.resource_path}`", line)
                self.assertIn("return `blocked`", line)


class RenderCheckTests(unittest.TestCase):
    """The checks the renderer owns, each over the source that fails it.

    A heading and a transition are what an agent skims, so a command that does
    not read as one, an edge to a node the graph does not define, a label two
    nodes answer to, and an outbound link inside an execution-bearing field are
    all refused rather than written into a bundle someone later has to read.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.skill = Path(self.directory.name) / "alpha"
        import shutil

        shutil.copytree(ALPHA, self.skill)
        self.run_workflow = self.skill / "workflows" / "run.yaml"

    def replace_in_run(self, old: str, new: str) -> None:
        text = self.run_workflow.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.run_workflow.write_text(text.replace(old, new), encoding="utf-8")

    def test_a_command_that_does_not_close_as_a_sentence_is_reported(self):
        self.replace_in_run(
            "    action: Write the report and name what it does not cover.",
            "    action: Write the report and name what it does not cover",
        )
        self.assertIn("render.incomplete-command", codes(self.skill))

    def test_a_command_of_one_word_is_reported(self):
        self.replace_in_run(
            "    action: Write the report and name what it does not cover.",
            "    action: Report.",
        )
        self.assertIn("render.incomplete-command", codes(self.skill))

    def test_an_outbound_reference_inside_a_command_is_reported(self):
        self.replace_in_run(
            "    action: Write the report and name what it does not cover.",
            "    action: Write the report that references/guidance/run-context-notes.md"
            " describes.",
        )
        self.assertIn("render.load-bearing-reference", codes(self.skill))

    def test_a_transition_leaving_the_generated_graph_is_reported(self):
        """No source writes this edge; the renderer is the last place to catch it."""
        with mock.patch("degardis.render._collect_labels", return_value=()):
            found = codes(self.skill)
        self.assertIn("render.external-execution-link", found)

    def test_two_nodes_answering_to_one_label_is_a_build_error(self):
        """A label is content-derived, so a collision is refused, not renamed."""
        with mock.patch(
            "degardis.lowering.node_label", return_value="run--same"
        ):
            found = codes(self.skill)
        self.assertIn("render.node-label-collision", found)


class AdvisoryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.result, _ = compiled(ALPHA)
        cls.sources = cls.result.lowered.sources

    def test_guidance_summary_is_inline_without_optional_link_boilerplate(self):
        runtime = self.result.rendered.skill_text + "\n" + "\n".join(
            self.result.rendered.execution_modules.values()
        )
        self.assertNotIn("[Optional detail]", runtime)
        for identifier, unit in self.sources.guidance.items():
            with self.subTest(guidance=identifier):
                self.assertIn(unit.summary, runtime)

    def test_guidance_link_closes_the_note_line_not_its_last_point(self):
        """A link trailing the final point reads as that one point's reference.

        The page behind a context note holds the whole unit, so the link belongs
        to the line the note itself wrote. Rendered after the points, it lands
        inside the last bullet and misnames what it opens.
        """
        lines = (
            self.result.rendered.skill_text + "\n"
            + "\n".join(self.result.rendered.execution_modules.values())
        ).splitlines()
        labels = {
            identifier: wording.CONTEXT_NOTE.format(id=identifier)
            for identifier in self.sources.guidance
        }
        linked = above_points = False
        for index, line in enumerate(lines):
            carried = [
                identifier
                for identifier in labels
                if f"guidance/{identifier}.md" in line
            ]
            if not carried:
                continue
            linked = True
            with self.subTest(line=line):
                self.assertTrue(any(labels[name] in line for name in carried), line)
            above_points = above_points or (
                index + 1 < len(lines) and lines[index + 1].startswith("  - ")
            )
        self.assertTrue(linked, "no guidance unit links its page, so nothing is tested")
        self.assertTrue(
            above_points, "no linked note renders points, so the case is untested"
        )

    def test_reference_pages_remain_non_executable(self):
        for path, page in self.result.rendered.pages.items():
            if path.startswith("profiles/"):
                continue
            self.assertNotRegex(page, NODE_HEADING)


class AttentionBudgetTests(unittest.TestCase):
    """What a skill costs to load, reported against the source that raised it.

    The two budgets protect different reader costs. The root is the one file
    an agent always loads, so it is held to the smaller limit; a module is
    loaded whole to reach one node in it, and the partition keeps every module
    inside the larger one. Both report what the partition cannot fix, and both
    warn rather than fail: the remaining repairs are the author's to weigh
    against what the skill needs to say.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.skill = Path(self.directory.name) / "budget"
        (self.skill / "workflows").mkdir(parents=True)

    def write_manifest(self, *, guidance: bool = False) -> None:
        lines = [
            "name: budget",
            "format_version: 2",
            "version: 1.0.0",
            "description: Exercise the attention budgets.",
            "primary_workflow: run",
        ]
        content = ["content:", "  workflows:", "  - workflows/*.yaml"]
        if guidance:
            lines += ["guidance:", "- long"]
            content += ["  guidance:", "  - guidance/*.yaml"]
        lines += [
            *content,
            "interface:",
            "  display_name: Budget",
            "  short_description: Exercise the budgets",
            "  default_prompt: Use {name} for this task.",
        ]
        write_text(self.skill / "skill.yaml", "\n".join(lines) + "\n")

    def write_workflow(self, steps: int, command: str) -> None:
        lines = [
            "title: Run the task",
            "description: Perform the steps and return.",
            "outcomes:",
            "  done: {}",
            "entry: s000",
            "steps:",
        ]
        for index in range(steps):
            following = f"s{index + 1:03d}" if index + 1 < steps else "finish"
            lines += [
                f"  s{index:03d}:",
                f"    action: {command}",
                f"    next: {following}",
            ]
        lines += ["  finish:", "    return:", "      outcome: done"]
        write_text(self.skill / "workflows" / "run.yaml", "\n".join(lines) + "\n")

    def test_a_control_plane_above_its_budget_is_reported(self):
        """An expensive root warns rather than fails.

        The repair is less bound to the run, and a skill can legitimately
        need what it binds, so the budget states the cost and leaves the
        judgment with the author.
        """
        self.write_manifest(guidance=True)
        write_text(
            self.skill / "guidance" / "long.yaml",
            "summary: Lead with the result, "
            + "and keep every qualification beside the claim it bounds, " * 600
            + "as the reader needs it.\n",
        )
        self.write_workflow(2, "Perform the one bounded step this task names.")
        self.assertIn("render.root-budget", codes(self.skill, "warning"))
        self.assertNotIn("render.root-budget", codes(self.skill))

    def test_many_dense_nodes_are_partitioned_rather_than_reported(self):
        """Commands long enough to fill a module split it instead of bursting it.

        Nodes this size once overflowed the module, because the partition
        counted nodes while the check measured bytes. The partition now
        measures the same thing the check does, so the workflow renders across
        as many modules as its size needs and reports nothing.
        """
        self.write_manifest()
        self.write_workflow(
            79,
            "Perform the bounded step this module names, "
            + "recording what it touched and what it left alone, " * 20
            + "then continue.",
        )
        found = codes(self.skill, "warning")
        self.assertNotIn("render.node-budget", found)
        self.assertNotIn("render.module-budget", found)
        modules = compiled(self.skill)[1].rendered.execution_modules
        self.assertGreater(len(modules), 1)
        for path, text in modules.items():
            with self.subTest(path=path):
                self.assertLessEqual(
                    len(text.encode("utf-8")), MODULE_BUDGET_BYTES
                )

    def test_call_destinations_fit_the_module_budget(self):
        """Qualified callee names cost bytes on every call in a packed module."""
        self.write_manifest()
        callee = "verify-the-complete-bounded-result-before-continuing"
        lines = [
            "title: Run the task", "description: Perform the calls and return.",
            "outcomes:", "  done: {}", "entry: s000", "steps:",
        ]
        for index in range(80):
            following = f"s{index + 1:03d}" if index < 79 else "finish"
            lines += [f"  s{index:03d}:", f"    use: {callee}",
                      "    on:", f"      done: {following}"]
        lines += ["  finish:", "    return:", "      outcome: done"]
        write_text(self.skill / "workflows" / "run.yaml", "\n".join(lines) + "\n")
        write_text(
            self.skill / "workflows" / f"{callee}.yaml",
            "title: Verify the result\ndescription: Verify the bounded result.\n"
            "outcomes:\n  done: {}\nentry: finish\nsteps:\n"
            "  finish:\n    return:\n      outcome: done\n",
        )
        _, result, diagnostics = compiled(self.skill)
        self.assertEqual([], diagnostics.errors)
        for path, text in result.rendered.execution_modules.items():
            with self.subTest(path=path):
                self.assertLessEqual(len(text.encode("utf-8")), MODULE_BUDGET_BYTES)

    def test_part_numbers_fit_a_nearly_full_module(self):
        """The part heading must not push an otherwise fitting module over budget."""
        self.write_manifest()
        self.write_workflow(12, "Perform the check " + "record " * 222 + ".")
        _, result, diagnostics = compiled(self.skill)
        self.assertEqual([], diagnostics.errors)
        modules = result.rendered.execution_modules
        self.assertGreater(len(modules), 1)
        for path, text in modules.items():
            with self.subTest(path=path):
                self.assertLessEqual(len(text.encode("utf-8")), MODULE_BUDGET_BYTES)

    def test_one_node_too_large_for_any_module_is_reported(self):
        """The one module the partition cannot keep inside the budget.

        Every other module fits by construction, so this is the only thing
        the budget has left to report. It warns rather than fails: the
        remaining repairs are a shorter command or less bound to that step,
        and a skill can legitimately have neither available.
        """
        self.write_manifest()
        self.write_workflow(
            2,
            "Perform the step this task names, "
            + "reconciling each supplied record against the register of record, " * 260
            + "then continue.",
        )
        found = codes(self.skill, "warning")
        self.assertIn("render.node-budget", found)
        # The module holding it is over as well, which is the same event seen
        # at the level the reader loads.
        self.assertIn("render.module-budget", found)
        self.assertNotIn("render.node-budget", codes(self.skill))

    def test_a_workflow_header_too_large_is_reported_against_the_module(self):
        """A header no node fits around is the module's finding, not a node's.

        Every module of a workflow repeats its header, so a long description
        or bound guidance puts every one of them over the budget while each
        node stays small. Reported at the node this would name whichever node
        happened to be placed first in each module, which is neither the cause
        nor the repair.
        """
        self.write_manifest()
        write_text(
            self.skill / "workflows" / "run.yaml",
            "title: Run the task\n"
            "description: Perform the steps this workflow names, "
            + "reconciling each record against the register of record, " * 300
            + "then report.\n"
            "outcomes:\n  done: {}\nentry: s000\nsteps:\n"
            "  s000:\n    action: Perform the first bounded step.\n    next: s001\n"
            "  s001:\n    action: Perform the second bounded step.\n    next: finish\n"
            "  finish:\n    return:\n      outcome: done\n",
        )
        found = codes(self.skill, "warning")
        self.assertIn("render.module-budget", found)
        self.assertNotIn("render.node-budget", found)


if __name__ == "__main__":
    unittest.main()
