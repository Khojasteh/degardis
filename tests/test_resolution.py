"""Which skills and profiles one request resolves to."""

from __future__ import annotations

import unittest

from degardis.model import DegardisError
from degardis.registry import discover_skill_paths
from degardis.resolver import collect_skills

from tests.support import FIXTURES


class ResolutionTests(unittest.TestCase):
    def test_each_bundle_contains_exactly_one_skill(self):
        bundles = collect_skills(discover_skill_paths([FIXTURES]))
        self.assertEqual(3, len(bundles))
        for bundle in bundles:
            self.assertEqual([bundle.primary.name], bundle.resolved_names)

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

    def test_a_build_that_names_no_profile_selects_none(self):
        """A profile is optional, so only the command that builds can ask for one."""
        bundles = collect_skills(discover_skill_paths([FIXTURES]))
        selected = {
            bundle.primary.name: {
                profile.name
                for profile in bundle.content(bundle.primary.name).profiles
            }
            for bundle in bundles
        }

        self.assertEqual({"alpha": set(), "beta": set(), "gamma": set()}, selected)

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
