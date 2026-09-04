"""The curated platform catalog (data/sites.yaml)."""
from __future__ import annotations

import pytest

from autowebpost.catalog import Site, by_slug, load_sites, sites_table


@pytest.fixture(scope="module")
def sites():
    return load_sites()


class TestLoadSites:
    def test_loads_a_populated_catalog(self, sites):
        assert len(sites) > 10

    def test_every_entry_is_a_site(self, sites):
        assert all(isinstance(s, Site) for s in sites)

    def test_slugs_are_unique(self, sites):
        slugs = [s.slug for s in sites]
        assert len(slugs) == len(set(slugs))

    def test_every_site_has_a_name_and_url(self, sites):
        for s in sites:
            assert s.slug and s.name and s.url

    def test_domain_authority_is_sane(self, sites):
        for s in sites:
            assert 0 <= s.da <= 100

    def test_api_field_uses_the_known_vocabulary(self, sites):
        for s in sites:
            assert s.api in ("free", "pro", "none", "manual-assist"), s.slug

    def test_by_slug_finds_a_site(self):
        assert by_slug("devto").name == "DEV.to"

    def test_by_slug_raises_for_unknown(self):
        with pytest.raises(KeyError, match="Unknown site slug"):
            by_slug("not-a-site")


class TestAutoPostable:
    def test_requires_both_a_publisher_and_a_usable_api(self):
        assert Site(slug="x", name="X", url="u", api="free", publisher="x").auto_postable
        assert not Site(slug="x", name="X", url="u", api="free").auto_postable
        assert not Site(slug="x", name="X", url="u", api="pro", publisher="x").auto_postable

    def test_at_least_seven_sites_are_auto_postable(self, sites):
        assert sum(1 for s in sites if s.auto_postable) >= 7

    def test_every_implemented_publisher_exists_in_the_registry(self, sites):
        from autowebpost.platforms import PUBLISHERS
        for s in sites:
            if s.publisher:
                assert s.publisher in PUBLISHERS, f"{s.slug}: missing adapter"

    def test_every_registered_publisher_is_in_the_catalog(self, sites):
        from autowebpost.platforms import PUBLISHERS
        catalog_publishers = {s.publisher for s in sites if s.publisher}
        assert set(PUBLISHERS) == catalog_publishers

    def test_known_high_da_platforms_are_present(self, sites):
        slugs = {s.slug for s in sites}
        assert {"githubpages", "devto", "telegraph", "wordpress", "blogger"} <= slugs


class TestSitesTable:
    def test_contains_headers_and_rows(self, sites):
        table = sites_table(sites)
        assert "SLUG" in table and "PLATFORM" in table
        assert "devto" in table

    def test_sorted_by_descending_da(self, sites):
        rows = [s for s in sorted(sites, key=lambda x: -x.da)]
        assert rows[0].da >= rows[-1].da

    def test_api_only_filters_out_non_auto_postable(self, sites):
        table = sites_table(sites, only_api=True)
        # match the SLUG column only - slugs also appear inside prose
        # ("reddit" is a substring of "subreddits", "hubpages" of "githubpages")
        slugs = {line.split()[0] for line in table.splitlines()[2:] if line.strip()}
        for s in sites:
            assert (s.slug in slugs) == s.auto_postable, s.slug

    def test_api_only_includes_telegraph(self, sites):
        assert "telegraph" in sites_table(sites, only_api=True)
