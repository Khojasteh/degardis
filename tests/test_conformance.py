"""The guarantees the format makes, one case each, with the failure it prevents.

A guarantee that is not one of these cases is not yet a guarantee. Read them
before changing what a bundle looks like: each states something an author or a
running agent is entitled to rely on, and the docstring says what goes wrong
when it stops holding.
"""

from __future__ import annotations

import posixpath
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from degardis import wording
from degardis.build import build_skills
from degardis.bundlepaths import (
    AGENTS_DIRECTORY,
    FACET_INDEX,
    GUIDES_DIRECTORY,
    PRINCIPLES_DIRECTORY,
    REFERENCES_DIRECTORY,
    REGISTER,
    ROOT,
    TASKS_DIRECTORY,
    facet_path,
    guide_path,
    principle_path,
    task_path,
)
from degardis.markdown import (
    EXTERNAL_TARGET,
    INLINE_REFERENCE,
    link_destinations,
    read_markdown,
    unwrap_paragraphs,
)
from degardis.validate import compile_skill
from degardis.model import Diagnostics
from degardis.registry import load_skill_path

from tests.support import (
    alpha,
    compiled,
    copy_skills,
    edit_frontmatter,
    edit_yaml,
    field_of,
    folder_names,
    folder_text,
    pages,
    write_text,
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

    def test_a_hand_off_links_one_task_page_to_another_with_no_generated_hop(self):
        """A task may send the work to another task, and the link goes straight
        to that task's page: the same complete page the root routes to, with
        nothing generated between the two.
        """
        self.assertIn("(repair.md)", folder_text(self.artifact, task_path("review")))
        self.assertIn(f"({task_path('repair')})", folder_text(self.artifact, ROOT))

    def test_the_bundle_holds_no_routing_layer_of_its_own(self):
        """Every generated principle page must be reachable from the root."""
        generated = {
            name
            for name in folder_names(self.artifact)
            if name.endswith(".md")
            and not name.startswith(("references/guides/", "assets/"))
        }
        expected = {ROOT, FACET_INDEX}
        expected |= {task_path(name) for name in ("repair", "review", "document")}
        expected |= {
            principle_path(name)
            for name in ("evidence", "expenditure", "reporting", "delegation", "provenance")
        }
        expected |= {facet_path(name) for name in ("python", "legacy", "urgent")}
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
            for target in link_destinations(text):
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

    # Every location docs/artifact-format.md says a bundle contains. A build
    # writes into these and nowhere else, so a file that table does not account
    # for is a file a reader of that document does not know exists.
    DOCUMENTED_LOCATIONS = (
        f"{REFERENCES_DIRECTORY}/tasks/",
        f"{REFERENCES_DIRECTORY}/principles/",
        f"{REFERENCES_DIRECTORY}/facets/",
        f"{REFERENCES_DIRECTORY}/guides/",
        "scripts/",
        "assets/",
        f"{AGENTS_DIRECTORY}/",
    )

    def test_the_bundle_emits_no_machine_interface_beside_the_document(self):
        """The report is the only machine interface.

        A source map, a plan, a closure, or a coverage file written beside the
        pages would become an interface the compiler has to keep, and an agent
        would read it instead of the document the checks actually cover.

        The comparison is closed rather than a list of suffixes to refuse: any
        file a build starts writing fails this until the documented layout
        accounts for it, whatever it is called.
        """
        unaccounted = sorted(
            name
            for name in folder_names(self.artifact)
            if name != ROOT and not name.startswith(self.DOCUMENTED_LOCATIONS)
        )
        self.assertEqual(
            [],
            unaccounted,
            "these bundle files sit outside every location "
            "docs/artifact-format.md describes",
        )


class PlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))
        self.pages = pages(alpha(self.root))

    def test_the_root_lists_every_skill_principle_once_before_task_routes(self):
        """The skill declares principles once, so task pages cannot disagree.

        The root states those links above its routing, so an agent reads
        skill-wide guidance before choosing the page for a particular class of
        work.
        """
        title = "Report the result, not the work that produced it"
        root = self.pages[ROOT]
        principle = f"[{title}]({principle_path('reporting')})"
        self.assertIn(f"## {wording.PRINCIPLES_HEADING}", root)
        self.assertIn(f"## {wording.TASKS_HEADING}", root)
        self.assertEqual(1, root.count(principle))
        self.assertLess(root.index(principle), root.index(f"({task_path('review')})"))
        for name in ("repair", "review", "document"):
            with self.subTest(task=name):
                self.assertNotIn(title, self.pages[task_path(name)])

    def test_a_skill_principle_is_stated_on_the_root_and_on_no_task_page(self):
        """A principle every task needs is named once, at skill level, so no
        task page can carry a copy that disagrees with the root's."""
        for name in ("evidence", "expenditure", "reporting", "delegation", "provenance"):
            title = field_of(alpha(self.root) / "principles" / f"{name}.md", "title")
            with self.subTest(principle=name):
                self.assertIn(title, self.pages[ROOT])
                for task in ("repair", "review", "document"):
                    self.assertNotIn(title, self.pages[task_path(task)])

    def test_hand_offs_never_reach_the_root(self):
        """The root routes by cues alone. A situation that arises during one
        task is that task's hand-off, paid for by the runs doing that task and
        not startup cost paid by every run."""
        before = self.pages[ROOT]
        for name in ("review", "repair"):
            with edit_frontmatter(source_task(self.root, "alpha", name)) as fields:
                fields.pop("handoffs")
        self.assertEqual(before, pages(alpha(self.root))[ROOT])

    def test_a_task_never_selects_a_facet(self):
        """Which facets apply depends on the situation, which no task sees."""
        skill = load_skill_path(alpha(self.root))
        result = compile_skill(skill, Diagnostics())
        for item in result.plan.tasks:
            with self.subTest(task=item.id):
                self.assertNotIn(FACET_INDEX, self.pages[item.page])
                self.assertNotIn("references/facets/", self.pages[item.page])

    def test_the_facet_index_remains_a_situational_lookup(self):
        """It survives because applicability is a question only the agent can
        answer; the root's principle links do not make that selection."""
        self.assertIn(FACET_INDEX, self.pages[ROOT])
        self.assertLess(
            self.pages[ROOT].index(f"## {wording.PRINCIPLES_HEADING}"),
            self.pages[ROOT].index(f"## {wording.FACETS_HEADING}"),
        )
        index = self.pages[FACET_INDEX]
        self.assertIn(wording.FACET_INDEX_LEAD, index)

    def test_removing_every_facet_leaves_the_task_pages_unchanged(self):
        """Facets are auxiliary. A facet missed, or matched wrongly, cannot
        change what a task requires or whether the source is valid."""
        before = {
            name: text
            for name, text in self.pages.items()
            if name.startswith("references/tasks/")
        }
        shutil.rmtree(alpha(self.root) / "facets")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["content"].pop("facets")
        after = pages(alpha(self.root))
        for name, text in before.items():
            with self.subTest(page=name):
                self.assertEqual(text, after[name])

    def test_a_guide_knowledge_references_is_listed_on_every_page_carrying_it(self):
        """A knowledge unit is written once for every task that carries it, so
        it names no owner, and each page carrying it owns what it references.

        The page lists the guide among its own guides, where its register row
        is kept, and the unit's text names it rather than opening a second route
        to it from mid-paragraph. A page that did not list it would send its
        reader to a separately loaded page no list on that page accounts for.
        The fixture's repair task names no guide and carries a unit that
        references the checklist.
        """
        self.assertNotIn(
            "guides", read_markdown(source_task(self.root, "alpha", "repair")).fields
        )
        page = self.pages[task_path("repair")]
        link = f"]({posixpath.relpath(guide_path('checklist'), TASKS_DIRECTORY)})"
        text, _, guides = page.partition(f"\n## {wording.GUIDES_HEADING}\n")
        self.assertEqual(1, guides.count(link))
        self.assertIn("`guide:checklist`", text)
        self.assertNotIn(link, text)

    def test_a_guide_a_task_references_is_listed_on_its_own_page(self):
        """A task's text lands on its page the way the knowledge it carries
        does, so a guide it references is the task's own, as if its `guides`
        named it, and the reference is no finding.

        The page lists the guide among its guides, where its register row is
        kept, and the text names it rather than opening a second route to it
        from mid-paragraph. The fixture's document task names no guide, and
        its text references the toolchain guide.
        """
        source = source_task(self.root, "alpha", "document")
        self.assertNotIn("guides", read_markdown(source).fields)
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.records)
        self.assertEqual(("toolchain",), result.plan.task("document").guides)
        page = self.pages[task_path("document")]
        link = f"]({posixpath.relpath(guide_path('toolchain'), TASKS_DIRECTORY)})"
        text, _, guides = page.partition(f"\n## {wording.GUIDES_HEADING}\n")
        self.assertEqual(1, guides.count(link))
        self.assertIn("`guide:toolchain`", text)
        self.assertNotIn(link, text)

    def test_a_principle_knowledge_references_gains_no_task_owner(self):
        """A principle holds across every task, so the skill is its one owner
        and the root its one list. Knowledge that references one places it
        nowhere: the page carrying the unit keeps no principle list and no
        second route to the page, and the text names the principle at the step
        where it matters, by the id its register row is kept under."""
        unit = alpha(self.root) / "knowledge" / "failure-modes.md"
        write_text(
            unit,
            unit.read_text(encoding="utf-8")
            + "\nRecord the shape you saw, as [[principle:evidence]] asks.\n",
        )
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.records)
        texts = result.rendered.page_texts()
        page = texts[task_path("repair")]
        knowledge = page.partition(f"\n## {wording.KNOWLEDGE_HEADING}\n")[2]
        self.assertNotIn(f"\n## {wording.PRINCIPLES_HEADING}\n", page)
        self.assertIn("as `principle:evidence` asks.", knowledge)
        self.assertNotIn("principles/evidence.md", page)
        self.assertEqual(1, texts[ROOT].count(f"({principle_path('evidence')})"))

    def test_a_principle_only_knowledge_references_ships_no_page(self):
        """Without the skill naming it, nothing places it: no page, no register
        row, the source is told the principle is unused, and the reference
        names nothing the bundle ships."""
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data["principles"].remove("delegation")
        unit = alpha(self.root) / "knowledge" / "change-surface.md"
        write_text(
            unit,
            unit.read_text(encoding="utf-8")
            + "\nHand work over only as [[principle:delegation]] allows.\n",
        )
        _, result, diagnostics = compiled(alpha(self.root))
        reported = {record.code for record in diagnostics.records}
        self.assertIn("inline.unknown-target", reported)
        self.assertIn("principle.unused", reported)
        self.assertNotIn(principle_path("delegation"), result.rendered.pages)
        self.assertNotIn("|delegation|", result.rendered.pages[REGISTER])

    def test_a_guide_another_guide_requires_is_listed_on_that_guide_page_only(self):
        """A guide that cannot be understood without another sends its reader
        there, so its own page lists the other guide, with its own conditions.

        The pages that lead to the first guide do not list the second. Their
        reader has not yet decided the first applies, so a row there would ask
        for a verdict on a guide out of the context that needs it. No owner
        names the fixture's compatibility guide: the checklist requires it, and
        the review task, the repair task's knowledge, and both language facets
        reach the checklist, so it still reaches a reader.
        """
        self.assertNotIn(
            "compatibility",
            "".join(
                path.read_text(encoding="utf-8")
                for folder in ("tasks", "knowledge", "facets")
                for path in (alpha(self.root) / folder).glob("*.md")
            ),
        )
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertNotIn(
            "content.unconsumed", {record.code for record in diagnostics.records}
        )
        texts = result.rendered.page_texts()
        guides = texts[guide_path("checklist")].partition(
            f"\n## {wording.GUIDES_HEADING}\n"
        )[2]
        self.assertEqual(1, guides.count("](compatibility.md)"))
        for condition in result.content.sources.guides["compatibility"].applicability:
            self.assertIn(condition, guides)
        for page in (
            task_path("review"),
            task_path("repair"),
            task_path("document"),
            facet_path("legacy"),
            facet_path("python"),
        ):
            with self.subTest(page=page):
                self.assertNotIn("compatibility.md", texts[page])

    def test_each_page_lists_only_the_guides_it_owns(self):
        """Ownership does not pass along a chain: a guide a required guide
        requires is listed on the page that requires it, so a reader follows
        the chain one page at a time and meets each guide where it is needed."""
        with edit_frontmatter(alpha(self.root) / "guides" / "compatibility.md") as fields:
            fields["requires"] = ["toolchain"]
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertEqual([], diagnostics.records)
        plan = result.plan
        self.assertEqual(("checklist",), plan.task("review").guides)
        facets = {item.id: item.guides for item in plan.facets}
        self.assertEqual(("toolchain", "checklist"), facets["python"])
        self.assertEqual(("compatibility",), plan.guide("checklist").guides)
        self.assertEqual(("toolchain",), plan.guide("compatibility").guides)

    def test_a_guide_another_guide_references_is_listed_on_its_page(self):
        """A guide's text is read by whoever decided the guide applies, so a
        guide it references is the guide's own, as if it required it.

        The page lists the referenced guide where its register row is kept,
        and the text names it rather than opening a second route to it from
        mid-paragraph. The fixture's toolchain guide requires nothing, and its
        text references the compatibility guide.
        """
        source = alpha(self.root) / "guides" / "toolchain.md"
        self.assertNotIn("requires", read_markdown(source).fields)
        page = self.pages[guide_path("toolchain")]
        text, _, guides = page.partition(f"\n## {wording.GUIDES_HEADING}\n")
        self.assertEqual(1, guides.count("](compatibility.md)"))
        self.assertIn("`guide:compatibility`", text)
        self.assertNotIn("](compatibility.md)", text)

    def test_a_guide_a_facet_references_is_listed_after_the_guides_it_names(self):
        """A facet's text is read by whoever decided the facet applies, so a
        guide it references is the facet's own, as if its `guides` named it.

        The page lists the guide after the ones the facet names, where its
        register row is kept, and the text names it rather than opening a
        second route to it from mid-paragraph. A page whose text linked a guide
        its list did not carry would send its reader to a separately loaded
        page no list on that page accounts for. The fixture's python facet
        names the toolchain guide and its text references the checklist.
        """
        source = alpha(self.root) / "facets" / "python.md"
        self.assertEqual(["toolchain"], read_markdown(source).fields["guides"])
        page = self.pages[facet_path("python")]
        text, _, guides = page.partition(f"\n## {wording.GUIDES_HEADING}\n")
        here = posixpath.dirname(facet_path("python"))
        named, referenced = (
            f"]({posixpath.relpath(guide_path(name), here)})"
            for name in ("toolchain", "checklist")
        )
        for link in (named, referenced):
            with self.subTest(link=link):
                self.assertEqual(1, guides.count(link))
                self.assertNotIn(link, text)
        self.assertLess(guides.index(named), guides.index(referenced))
        self.assertIn("`guide:checklist`", text)

    def test_a_skill_read_only_by_situation_still_carries_required_reading(self):
        """The register holds reading whose applicability can change, and what
        a facet selects is the only reading the situation can change under the
        agent mid-run.

        A valid skill reaches that shape with no principle and no task guide,
        and that was the one shape whose root carried no Required reading
        section at all — leaving the agent with the most revisable reading the
        only one asked to keep no record of it.
        """
        shutil.rmtree(alpha(self.root) / "principles")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data.pop("principles")
            data["content"].pop("principles")
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields.pop("guides")
        for source, reference in (
            (alpha(self.root) / "knowledge" / "failure-modes.md", "[[guide:checklist]]"),
            (source_task(self.root, "alpha", "document"), "[[guide:toolchain]]"),
        ):
            write_text(
                source, source.read_text(encoding="utf-8").replace(reference, "it")
            )
        _, result, _ = compiled(alpha(self.root))
        self.assertFalse(result.plan.principles)
        self.assertFalse([item for item in result.plan.tasks if item.guides])
        self.assertTrue(result.plan.facets)
        assert result.rendered is not None
        root = result.rendered.page_texts()[ROOT]
        self.assertIn(f"## {wording.REGISTER_HEADING}", root)

    def test_the_register_holds_every_principle_and_guide_page_shipped(self):
        """The register is the compiler's answer to an enumeration, so it has
        to be the complete one.

        The root asks the agent to track every page under `references/principles`
        and `references/guides`. Left to list those directories itself, an agent
        pays for two lookups and can still come back short, and nothing in the
        bundle would show what it missed. A register that omits a shipped page
        is that same silent gap with the compiler's name on it.
        """
        _, result, _ = compiled(alpha(self.root))
        register = result.rendered.pages[REGISTER]
        rows = {
            line.split("|")[1].strip()
            for line in register.split(f"## {wording.PRINCIPLES_HEADING}", 1)[1]
            .split(f"## {wording.CONFORMANCE_HEADING}", 1)[0]
            .splitlines()
            if line.startswith("|") and not line.startswith(("|Id|", "|---|"))
        }
        shipped = {item.id for item in result.plan.principles}
        shipped |= set(result.content.sources.guides)
        self.assertNotEqual(set(), shipped)
        self.assertEqual(shipped, rows)

    def test_alternative_conditions_stay_apart_and_in_authored_order(self):
        """Each item of an `applicability` list is one condition an agent judges on
        its own, and any one holding is enough. Folded into one line or one
        register row, alternatives read as a conjunction, and one that holds
        could no longer be recorded while the others do not; reordered, they
        stop being the author's.

        So every owner link names its target once, followed by each condition
        in authored order, and a principle or guide takes one register row per
        condition, adjacent, in that same order.
        """
        _, result, _ = compiled(alpha(self.root))
        assert result.rendered is not None
        texts = result.rendered.page_texts()
        sources = result.content.sources
        cases = [
            (ROOT, principle_path(item.id), item.applicability)
            for item in result.plan.principles
        ]
        for plan in result.plan.tasks:
            cases += [(plan.page, guide_path(name), sources.guides[name].applicability)
                      for name in plan.guides]
            cases += [(plan.page, task_path(item.task), item.applicability)
                      for item in plan.task.handoffs]
        for facet in result.plan.facets:
            cases += [(facet_path(facet.id), guide_path(name), sources.guides[name].applicability)
                      for name in facet.guides]
        for guide in result.plan.guides:
            cases += [(guide_path(guide.id), guide_path(name), sources.guides[name].applicability)
                      for name in guide.guides]
        self.assertTrue(any(len(conditions) > 1 for _, _, conditions in cases))
        for page, target, conditions in cases:
            link = f"]({posixpath.relpath(target, posixpath.dirname(page) or '.')})"
            text = texts[page]
            with self.subTest(page=page, target=target):
                self.assertEqual(1, text.count(link))
                start = text.index(link)
                ends = [text.find(mark, start) for mark in ("\n- ", "\n\n")]
                entry = text[start : min([end for end in ends if end >= 0] + [len(text)])]
                position = 0
                for condition in conditions:
                    position = entry.index(condition, position) + len(condition)
        register = result.rendered.pages[REGISTER]
        rows = [
            line.strip("|").split("|")[:2]
            for line in register.splitlines()
            if line.startswith("|") and not line.startswith(("|Id|", "|---|"))
        ]
        for item in (*result.plan.principles, *sources.guides.values()):
            with self.subTest(construct=item.id):
                expected = [[item.id, condition] for condition in item.applicability]
                expected = expected or [[item.id, wording.REGISTER_UNCONDITIONAL]]
                start = rows.index(expected[0])
                self.assertEqual(expected, rows[start : start + len(expected)])
                self.assertEqual(len(expected), [row[0] for row in rows].count(item.id))

    def test_the_register_records_the_route_before_any_page_row(self):
        """Routing is decided before any principle or guide can be named, and
        the tasks still to do are register facts rather than memory, so the
        record is a route table ahead of the page rows, resting at one empty
        row until routing fills it.
        """
        _, result, _ = compiled(alpha(self.root))
        register = result.rendered.pages[REGISTER]
        record = register.split(f"## {wording.ROUTE_HEADING}\n", 1)[1]
        record = record.split("\n## ", 1)[0]
        rows = [line for line in record.splitlines() if line.startswith("|")]
        columns = list(wording.ROUTE_COLUMNS)
        self.assertEqual(
            [
                "|" + "|".join(columns) + "|",
                "|" + "|".join(["---"] * len(columns)) + "|",
                "|" + "|".join([wording.REGISTER_EMPTY] * len(columns)) + "|",
            ],
            rows,
        )
        self.assertLess(
            register.index(f"## {wording.ROUTE_HEADING}\n"),
            register.index(f"## {wording.PRINCIPLES_HEADING}\n"),
        )

    def test_a_route_row_records_why_its_task_was_chosen(self):
        """A task joins the route for a requested outcome or through a
        hand-off, one task may occur in more than one row, and each occurrence
        does only its own outcome. Which one a row serves is therefore a
        register fact rather than memory, kept in the field a page row keeps
        its own reason in, so one rule reads both.
        """
        _, result, _ = compiled(alpha(self.root))
        register = result.rendered.pages[REGISTER]
        record = register.split(f"## {wording.ROUTE_HEADING}\n", 1)[1]
        header = next(line for line in record.splitlines() if line.startswith("|"))
        columns = header.strip("|").split("|")
        basis = wording.REGISTER_COLUMNS[3]
        self.assertIn(basis, columns)

    def test_listing_a_construct_in_the_register_does_not_make_it_wanted(self):
        """A reference is how the bundle says one thing needs another, and the
        register would generate one for everything.

        Were a row a reference, every principle and guide would look wanted by
        something, and the compiler could no longer tell an author that a file
        no task, facet, or body names is a file nothing uses — the one warning
        that finds material an edit somewhere else left behind.
        """
        spare = "---\ntitle: Spare\n---\n\n# Spare\n"
        write_text(alpha(self.root) / "guides" / "spare.md", spare)
        write_text(alpha(self.root) / "principles" / "spare.md", spare)
        _, result, diagnostics = compiled(alpha(self.root))
        self.assertIn("spare", result.rendered.pages[REGISTER])
        reported = {record.code for record in diagnostics.records}
        self.assertIn("content.unconsumed", reported)
        self.assertIn("principle.unused", reported)

    def test_the_register_emits_no_reference_of_its_own(self):
        """The rows are identities, not links.

        The file is copied into a record this bundle cannot address, where a
        relative link resolves to nothing, and a link nobody can follow is
        worse than the id it replaced.
        """
        _, result, _ = compiled(alpha(self.root))
        self.assertEqual(
            [], [link for link in result.rendered.links if link.page == REGISTER]
        )
        self.assertEqual(
            [], link_destinations(result.rendered.pages[REGISTER])
        )

    def test_a_bundle_with_nothing_to_register_carries_neither_half(self):
        """The pointer and the page it names appear together or not at all.

        A root naming a register the build did not write sends the agent to a
        file that is not there, and a register nothing points at is a page no
        run opens.
        """
        shutil.rmtree(alpha(self.root) / "principles")
        shutil.rmtree(alpha(self.root) / "guides")
        with edit_yaml(alpha(self.root) / "skill.yaml") as data:
            data.pop("principles")
            data["content"].pop("principles")
            data["content"].pop("guides")
        for name in ("review", "repair", "document"):
            with edit_frontmatter(source_task(self.root, "alpha", name)) as fields:
                fields.pop("guides", None)
        for facet in sorted((alpha(self.root) / "facets").glob("*.md")):
            with edit_frontmatter(facet) as fields:
                fields.pop("guides", None)
        rebuilt = pages(alpha(self.root))
        self.assertNotIn(REGISTER, rebuilt)
        self.assertNotIn(f"## {wording.REGISTER_HEADING}", rebuilt[ROOT])
        self.assertNotIn(REGISTER, rebuilt[ROOT])
        tasks = {
            name: code
            for name, code in self.read_codes(rebuilt).items()
            if name.startswith(TASKS_DIRECTORY + "/")
        }
        self.assertNotEqual({}, tasks)
        self.assertEqual({None}, set(tasks.values()))

    @staticmethod
    def read_codes(rendered: dict[str, str]) -> dict[str, str | None]:
        """The code each register-tracked page ends with, or None if its last
        line is anything else or is not set apart from what precedes it."""
        code_line = re.compile(
            re.escape(wording.READ_CODE_LINE).replace(
                re.escape("{code}"), "(?P<code>[^`]+)"
            )
        )
        found: dict[str, str | None] = {}
        for name, text in rendered.items():
            if name.startswith(
                (TASKS_DIRECTORY + "/", PRINCIPLES_DIRECTORY + "/", GUIDES_DIRECTORY + "/")
            ):
                lines = [line for line in text.splitlines() if line.strip()]
                match = code_line.fullmatch(lines[-1])
                found[name] = match["code"] if match and lines[-2] == "---" else None
        return found

    def test_a_tracked_page_ends_with_a_read_code_no_other_file_shows(self):
        """A register row closes with a code the agent can only get by opening
        that page.

        Printed last, a whole read reaches it, and a thematic break above it
        keeps the compiler's line from reading as the author's closing
        sentence. Printed anywhere else — the root, the register, another
        tracked page — the row could be closed without the page ever being
        opened, which is the one thing the code exists to rule out. Task pages
        are tracked too, so the task row names a task only once its page has
        been read.
        """
        rendered = pages(alpha(self.root))
        codes = self.read_codes(rendered)
        self.assertNotEqual({}, codes)
        self.assertNotIn(None, codes.values())
        self.assertEqual(len(codes), len(set(codes.values())))
        for name, text in rendered.items():
            for page, code in codes.items():
                if page != name:
                    with self.subTest(code_of=page, found_in=name):
                        self.assertNotIn(code, text)

    def test_a_read_code_changes_with_its_page_and_only_its_page(self):
        """A register filled before an edit then shows exactly which rows the
        edit made stale, and no row the edit left alone."""
        before = self.read_codes(pages(alpha(self.root)))
        guide = alpha(self.root) / "guides" / "checklist.md"
        write_text(guide, guide.read_text(encoding="utf-8") + "\nOne more line.\n")
        after = self.read_codes(pages(alpha(self.root)))
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual({guide_path("checklist")}, changed)


def carried(line: str) -> str:
    """One line of a knowledge unit as a task page carries it.

    A unit's guide references name their target in inline code rather than
    linking it, because the page links it among its own guides. Any other
    reference is left as written, so a fixture unit that starts carrying one
    fails the comparison rather than passing unexamined.
    """
    return INLINE_REFERENCE.sub(
        lambda match: (
            f"`{match['kind']}:{match['target']}`"
            if match["kind"] == "guide"
            else match[0]
        ),
        line,
    )


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
                        self.assertIn(carried(line.strip()), page)

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
                        self.assertIn(carried(line.strip()), page)
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
        title = field_of(alpha(self.root) / "guides" / "checklist.md", "title")
        task = pages(alpha(self.root))[task_path("review")]
        _, result, _ = compiled(alpha(self.root))
        guide = result.rendered.pages["references/guides/checklist.md"]
        self.assertIn(f"[{title}](../guides/checklist.md)", task)
        self.assertEqual(f"# {title}", guide.splitlines()[0])


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
        self.assertEqual("references/facets/python.md", facet_path("python"))


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = copy_skills(Path(self.directory.name))

    def test_the_checks_collect_rather_than_stopping_at_the_first_problem(self):
        """An author repairing one finding per run pays a full cycle for each."""
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
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
        of them is dropped before the author ever sees it.

        Two principles the manifest names and no file answers are two repairs,
        so the collector owes the author both, told apart by what each refused.
        """
        with edit_yaml(alpha(self.root) / "skill.yaml") as fields:
            fields["principles"] += ["clear-reporting", "bounded-delegation"]
        _, _, diagnostics = compiled(alpha(self.root))
        messages = sorted(
            record.message
            for record in diagnostics.records
            if record.code == "manifest.unknown-principle"
        )
        self.assertEqual(2, len(messages))
        self.assertIn("principles names 'bounded-delegation'", messages[0])
        self.assertIn("principles names 'clear-reporting'", messages[1])
        self.assertNotIn("principles/", "\n".join(messages))

    def test_every_finding_carries_the_check_that_found_it(self):
        """Without the code a reader has the message and nothing to look up."""
        with edit_frontmatter(source_task(self.root, "alpha", "review")) as fields:
            fields["knowledge"] = ["nowhere"]
        _, _, diagnostics = compiled(alpha(self.root))
        # A source reporting nothing at all would pass the comparison below
        # while establishing nothing, so the edit above has to have produced a
        # finding for it to read.
        self.assertNotEqual([], diagnostics.records)
        self.assertEqual(
            [],
            [record.message for record in diagnostics.records if not record.code],
            "these findings name no check for a reader to look up",
        )


if __name__ == "__main__":
    unittest.main()
