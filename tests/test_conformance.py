"""The guarantees the format makes, one case each, with the failure it prevents.

A guarantee that is not one of these cases is not yet a guarantee. Read them
before changing what a bundle looks like: each states something an author or a
running agent is entitled to rely on, and the docstring says what goes wrong
when it stops holding.
"""

from __future__ import annotations

import posixpath
import shutil
import tempfile
import unittest
from pathlib import Path

from degardis.build import build_skills
from degardis.bundlepaths import PROFILE_INDEX, ROOT, principle_path, profile_path, task_path
from degardis.markdown import MARKDOWN_LINK, EXTERNAL_TARGET, unwrap_paragraphs
from degardis.validate import compile_skill
from degardis.model import Diagnostics
from degardis.registry import load_skill_path
from degardis.sources import TASK_FIELDS

from tests.support import (
    alpha,
    compiled,
    copy_skills,
    edit_frontmatter,
    folder_names,
    folder_text,
    pages,
)
from tests.support import task_path as source_task


class BundleShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.root = copy_skills(self.workspace)
        self.artifact = build_skills(alpha(self.root), self.workspace / "out")[0]

    def test_the_root_routes_directly_to_a_task_page(self):
        """No generated hop may sit between the root and the page it names.

        An index every run passes through is a load that answers no question
        the run had: the compiler already knows which knowledge belongs to which
        task, so an agent that has to look it up is paying for the compiler's
        indecision.
        """
        text = folder_text(self.artifact, ROOT)
        for name in ("repair", "review", "document"):
            with self.subTest(task=name):
                self.assertIn(f"({task_path(name)})", text)

    def test_the_bundle_holds_no_routing_layer_of_its_own(self):
        """Every generated principle page must be reachable from the root."""
        generated = {
            name
            for name in folder_names(self.artifact)
            if name.endswith(".md")
            and not name.startswith(("references/guides/", "assets/"))
        }
        expected = {ROOT, PROFILE_INDEX}
        expected |= {task_path(name) for name in ("repair", "review", "document")}
        expected |= {
            principle_path(name)
            for name in ("evidence", "expenditure", "reporting", "delegation", "provenance")
        }
        expected |= {profile_path(name) for name in ("python", "legacy", "urgent")}
        self.assertEqual(expected, generated)

    def test_a_task_page_carries_its_closure_rather_than_a_link_to_it(self):
        """A source decomposition is for whoever maintains it, not a route.

        If a page linked to its knowledge instead of carrying it, the agent
        would follow the author's filing system at run time, and a unit it
        failed to open would be a gap nothing reports.
        """
        page = folder_text(self.artifact, task_path("review"))
        self.assertIn("The surface is what someone outside the change", page)
        self.assertNotIn("knowledge/change-surface.md", page)

    def test_every_generated_link_resolves_to_a_file_the_bundle_ships(self):
        """A link an installed reader cannot open is a dead end at run time."""
        shipped = folder_names(self.artifact)
        for name in sorted(page for page in shipped if page.endswith(".md")):
            text = folder_text(self.artifact, name)
            here = Path(name).parent
            for match in MARKDOWN_LINK.finditer(text):
                target = match.group("target")
                if EXTERNAL_TARGET.match(target):
                    continue
                with self.subTest(page=name, target=target):
                    resolved = posixpath.normpath(
                        posixpath.join(here.as_posix(), target.partition("#")[0])
                    )
                    self.assertIn(resolved, shipped)

    def test_a_rebuild_is_byte_identical(self):
        """Nothing in the generated text may depend on the machine it ran on.

        A bundle that differs between two builds of one source makes every
        downstream comparison — a review, a digest, a cache — useless.
        """
        again = build_skills(alpha(self.root), self.workspace / "again")[0]
        for name in sorted(folder_names(self.artifact)):
            with self.subTest(name=name):
                self.assertEqual(
                    (self.artifact / name).read_bytes(), (again / name).read_bytes()
                )

    def test_the_bundle_emits_no_machine_interface_beside_the_document(self):
        """The report is the only machine interface.

        A source map or a plan file written beside the pages would become an
        interface the compiler has to keep, and an agent would read it instead
        of the document the checks actually cover.
        """
        self.assertEqual(
            [],
            sorted(
                name
                for name in folder_names(self.artifact)
                if name.endswith((".json", ".sourcemap", ".plan"))
            ),
        )


class PlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.pages = pages(alpha(self.root))

    def test_start_lists_every_skill_principle_once_before_task_routes(self):
        """The skill declares principles once, so task pages cannot disagree.

        Start puts those links before routing, so an agent reads skill-wide
        guidance before choosing the page for a particular class of work.
        """
        title = "Report the result, not the work that produced it"
        root = self.pages[ROOT]
        principle = f"[{title}]({principle_path('reporting')})"
        self.assertIn("## Start", root)
        self.assertNotIn("## Principles", root)
        self.assertEqual(1, root.count(principle))
        self.assertLess(root.index(principle), root.index(f"({task_path('review')})"))
        for name in ("repair", "review", "document"):
            with self.subTest(task=name):
                self.assertNotIn(title, self.pages[task_path(name)])

    def test_a_task_cannot_select_a_principle(self):
        """Principles are skill-wide, so their selection cannot vary by task."""
        title = "Delegate only a bounded, authorized, disjoint slice"
        self.assertIn(title, self.pages[ROOT])
        self.assertNotIn(title, self.pages[task_path("repair")])
        self.assertNotIn(title, self.pages[task_path("review")])

    def test_a_task_never_selects_a_profile(self):
        """Which profiles apply depends on the situation, which no task sees.

        The schema is asserted as well as the pages, because a task page with
        no profile link today and a `profiles` field tomorrow is the same
        failure arriving a release later.
        """
        self.assertNotIn("profiles", TASK_FIELDS)
        skill = load_skill_path(alpha(self.root))
        result = compile_skill(skill, Diagnostics())
        for item in result.plan.tasks:
            with self.subTest(task=item.id):
                self.assertNotIn(PROFILE_INDEX, self.pages[item.page])
                self.assertNotIn("references/profiles/", self.pages[item.page])

    def test_the_profile_index_remains_a_situational_lookup(self):
        """It survives because applicability is a question only the agent can
        answer; the root's principle links do not make that selection."""
        self.assertIn(PROFILE_INDEX, self.pages[ROOT])
        self.assertLess(
            self.pages[ROOT].index("## Start"),
            self.pages[ROOT].index("## Profiles"),
        )
        index = self.pages[PROFILE_INDEX]
        self.assertIn("Load every applicable profile and no others", index)

    def test_removing_every_profile_leaves_the_task_pages_unchanged(self):
        """Profiles are auxiliary. A profile missed, or matched wrongly, cannot
        change what a task requires or whether the source is valid."""
        before = {
            name: text
            for name, text in self.pages.items()
            if name.startswith("references/tasks/")
        }
        shutil.rmtree(alpha(self.root) / "profiles")
        from tests.support import edit_yaml

        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"].pop("profiles")
        after = pages(alpha(self.root))
        for name, text in before.items():
            with self.subTest(page=name):
                self.assertEqual(text, after[name])


class AuthoredMaterialTests(unittest.TestCase):
    """Ordinary compilation never rewrites what an author wrote."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_every_sentence_of_a_unit_reaches_the_page_that_carries_it(self):
        """Silently dropping part of a unit would ship a page whose knowledge
        nobody reviewed, and nothing in the bundle would show what was lost."""
        _, result, _ = compiled(alpha(self.root))
        rendered = result.rendered.pages
        for item in result.plan.tasks:
            page = rendered[item.page]
            for unit in item.closure:
                for line in unit.body.splitlines():
                    if not line.strip() or line.lstrip().startswith(("#", "|")):
                        continue
                    with self.subTest(task=item.id, unit=unit.key):
                        self.assertIn(line.strip(), page)

    def test_the_column_an_author_wrapped_to_does_not_reach_the_page(self):
        """A wrap is the width of the editor it was written in, and the page is
        read somewhere else. Carrying it breaks lines across the middle of a
        window that is not that wide, and shows a reflowed paragraph in a diff as
        every line changed. Folding is reformatting, so what is guaranteed is
        that the author's material still arrives whole: every folded line of
        every unit reaches the page that carries it."""
        _, result, _ = compiled(alpha(self.root))
        folded_any = False
        for item in result.plan.tasks:
            page = result.rendered.pages[item.page]
            for unit in item.closure:
                folded = unwrap_paragraphs(unit.body)
                folded_any = folded_any or folded != unit.body
                for line in folded.splitlines():
                    if not line.strip() or line.lstrip().startswith(("#", "|")):
                        continue
                    with self.subTest(task=item.id, unit=unit.key):
                        self.assertIn(line.strip(), page)
        self.assertTrue(folded_any, "no fixture unit is wrapped, so nothing was folded")

    def test_a_unit_two_tasks_need_reaches_both_pages_in_full(self):
        """Each page is complete for its own work; neither is a partial copy."""
        page_pages = pages(alpha(self.root))
        marker = "Edited lines are not the surface."
        self.assertIn(marker, page_pages[task_path("review")])
        self.assertIn(marker, page_pages[task_path("document")])

    def test_a_principle_reaches_the_page_exactly_as_its_own_source_states_it(self):
        """A principle is authored in the skill that uses it, so the compiler
        supplies none and rewords none. A page carrying text nobody in the
        source wrote is text nobody in the source can correct."""
        _, result, _ = compiled(alpha(self.root))
        body = result.content.sources.principles["provenance"].body
        page = pages(alpha(self.root))[principle_path("provenance")]
        for line in body.splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                with self.subTest(line=line[:40]):
                    self.assertIn(line.strip(), page)

    def test_a_guide_title_names_its_link_and_page(self):
        """A conditional page needs one author-controlled name at both ends.

        Inferring a title from a body heading would make a body without one
        appear anonymous in its task, while writing the title only on the task
        would leave the page the link opens unidentified.
        """
        title = "Published interface checklist"
        task = pages(alpha(self.root))[task_path("review")]
        _, result, _ = compiled(alpha(self.root))
        guide = result.rendered.pages["references/guides/checklist.md"]
        self.assertIn(f"[{title}](../guides/checklist.md)", task)
        self.assertTrue(guide.startswith(f"# {title}\n"))


class IdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_no_source_file_declares_an_id(self):
        """Two spellings of one name can disagree, and nothing would say which
        the compiler used."""
        for path in sorted(alpha(self.root).rglob("*.md")):
            if path.parts[-2] == "assets":
                continue
            with self.subTest(path=path.name):
                self.assertNotIn("\nid:", path.read_text(encoding="utf-8"))

    def test_renaming_a_file_renames_the_construct(self):
        """The stem is the identity, so a move keeps it and a rename changes it."""
        source = alpha(self.root) / "knowledge" / "change-surface.md"
        source.rename(source.with_name("surface.md"))
        for name in ("review", "document"):
            with edit_frontmatter(source_task(self.root, "alpha", name)) as fields:
                fields["knowledge"] = [
                    reference.replace("change-surface", "surface")
                    for reference in fields.get("knowledge", [])
                ]
        with edit_frontmatter(
            alpha(self.root) / "knowledge" / "order-findings.md"
        ) as fields:
            fields["requires"] = ["surface"]
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.errors)
        self.assertIn("surface", result.content.sources.knowledge)

    def test_a_generated_page_path_follows_from_the_id_alone(self):
        """A path a reader cannot predict is a link the compiler has to keep in
        step with three other places."""
        self.assertEqual("references/tasks/review.md", task_path("review"))
        self.assertEqual("references/profiles/python.md", profile_path("python"))


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_the_checks_collect_rather_than_stopping_at_the_first_problem(self):
        """An author repairing one finding per run pays a full cycle for each."""
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        from tests.support import edit_yaml

        with edit_yaml(alpha(self.root) / "skill.yaml") as fields:
            fields["principles"].append("clear-reporting")
        with edit_frontmatter(source_task(self.root, "alpha", "repair")) as fields:
            fields["knowledge"] = ["also-nowhere"]
        _, _, diagnostics = compiled(alpha(self.root))
        found = [record.code for record in diagnostics.select("error")]
        self.assertEqual(
            [
                "manifest.unknown-principle",
                "task.unknown-knowledge",
                "task.unknown-knowledge",
            ],
            found,
        )

    def test_two_findings_of_one_code_are_kept_apart(self):
        """A message naming only the file makes two findings identical, and one
        of them is dropped before the author ever sees it."""
        from tests.support import edit_yaml

        with edit_yaml(alpha(self.root) / "skill.yaml") as fields:
            fields["principles"].append("clear-reporting")
        _, _, diagnostics = compiled(alpha(self.root))
        records = [
            record
            for record in diagnostics.records
            if record.code == "manifest.unknown-principle"
        ]
        self.assertEqual(1, len(records))

    def test_every_finding_carries_the_check_that_found_it(self):
        """Without the code a reader has the message and nothing to look up."""
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        _, _, diagnostics = compiled(alpha(self.root))
        self.assertTrue(diagnostics.records)
        for record in diagnostics.records:
            with self.subTest(message=record.message[:40]):
                self.assertTrue(record.code)


if __name__ == "__main__":
    unittest.main()
