import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from leadmap import ca_sos, estimates, manual, overpass, scoring, website_check  # noqa: E402
from leadmap.categories import categorize  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "overpass_fixture.json")


class TestOverpass(unittest.TestCase):
    def setUp(self):
        self.bs = {b["name"]: b for b in overpass.collect("2026-01-01", FIXTURE)}

    def test_filters_and_dedupes(self):
        self.assertNotIn("Fixture Supermarket", self.bs)  # big-box skipped
        self.assertEqual(len([n for n in self.bs if n == "Fixture Family Dental"]), 1)
        self.assertEqual(len(self.bs), 6)  # unnamed restaurant dropped too

    def test_fields_and_provenance(self):
        b = self.bs["Fixture Taqueria"]
        self.assertEqual(b["phone"], "(805) 555-0101")
        self.assertEqual(b["address"], "1 Test St, Santa Barbara, CA, 93101")
        self.assertEqual(b["year_founded"], 1998)
        self.assertEqual(b["provenance"]["phone"]["source"], "OpenStreetMap (node/1)")
        self.assertIsNone(b["owner_name"])
        self.assertNotIn("owner_name", b["provenance"])

    def test_city_guess_is_marked_estimated(self):
        b = self.bs["Fixture Auto Repair"]
        self.assertEqual(b["city"], "Carpinteria")
        self.assertEqual(b["provenance"]["city"]["status"], "estimated")

    def test_chain_and_website(self):
        self.assertTrue(self.bs["Big Chain Coffee"]["chain"])
        self.assertEqual(self.bs["Fixture Hair Studio"]["website"], "http://example.com")
        self.assertEqual(self.bs["Fixture Plumbing"]["social_url"], "https://facebook.com/fixtureplumbing")


class TestCategorize(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(categorize({"leisure": "fitness_centre"})[0], "fitness")
        self.assertEqual(categorize({"shop": "nails"})[0], "salon")
        self.assertEqual(categorize({"craft": "electrician"})[0], "home")
        self.assertEqual(categorize({"office": "lawyer"})[0], "professional")
        self.assertEqual(categorize({"office": "government"}), (None, None))


class TestWebsiteCheck(unittest.TestCase):
    def test_no_site_and_social(self):
        self.assertEqual(website_check.check(None)["rating"], "none")
        self.assertEqual(website_check.check("https://www.facebook.com/x")["rating"], "weak")

    def test_analyze_html(self):
        good = '<html><meta name="viewport" content="width=device-width">' + "x" * 300 + "© 2026</html>"
        self.assertEqual(website_check.analyze_html(good, "https://a.com", 0.5, this_year=2026), [])
        bad = "<html>Copyright 2014 Joe's" + "y" * 300 + "</html>"
        issues = website_check.analyze_html(bad, "http://a.com", 6, this_year=2026)
        self.assertIn("No HTTPS", issues)
        self.assertIn("Not mobile-friendly (no viewport tag)", issues)
        self.assertIn("Outdated (latest © 2014)", issues)
        self.assertTrue(any(i.startswith("Slow") for i in issues))


class TestEstimates(unittest.TestCase):
    def test_unknown_without_basis(self):
        b = {"category": "salon", "provenance": {}}
        estimates.estimate_revenue(b)
        self.assertIsNone(b["revenue_low"])
        self.assertNotIn("revenue", b["provenance"])

    def test_estimate_from_employees(self):
        b = {"category": "salon", "employees": 6, "provenance": {"employees": {"source": "Manual: phone call"}}}
        estimates.estimate_revenue(b)
        self.assertLess(b["revenue_low"], b["revenue_high"])
        self.assertEqual(b["provenance"]["revenue"]["status"], "estimated")
        self.assertIn("6 employees", b["provenance"]["revenue"]["note"])


class TestScoring(unittest.TestCase):
    def test_scores(self):
        hot = {"website_check": {"rating": "none"}, "chain": False, "phone": "x"}
        self.assertEqual(scoring.score(hot), 5)
        chain = {"website_check": {"rating": "none"}, "chain": True, "phone": "x"}
        self.assertEqual(scoring.score(chain), 1)


class TestManual(unittest.TestCase):
    def test_apply(self):
        b = {"id": "osm-node-1", "name": "Fixture Taqueria", "provenance": {}}
        rows = {"fixture taqueria": {"owner_name": "Pat Example", "employees": "12", "source": "Called 10/1"}}
        self.assertTrue(manual.apply(b, rows, "2026-01-01"))
        self.assertEqual(b["owner_name"], "Pat Example")
        self.assertEqual(b["employees"], 12)
        self.assertEqual(b["provenance"]["owner_name"]["source"], "Manual: Called 10/1")


class TestCaSos(unittest.TestCase):
    def setUp(self):
        os.environ["CA_SOS_API_KEY"] = "test"
        self._orig = ca_sos._get

    def tearDown(self):
        ca_sos._get = self._orig

    def test_exact_single_match_only(self):
        ca_sos._get = lambda *a: {"RecordCount": 2, "Results": [
            {"EntityName": "FIXTURE TAQUERIA, LLC", "EntityNumber": "202012345678", "EntityStatus": "Active",
             "RegistrationDate": "03/14/2012", "AgentName": "Agent Person"},
            {"EntityName": "FIXTURE TAQUERIA NORTH LLC", "EntityStatus": "Active"}]}
        b = {"name": "Fixture Taqueria", "provenance": {}}
        self.assertTrue(ca_sos.enrich(b, "2026-01-01"))
        self.assertEqual(b["year_founded"], 2012)
        self.assertEqual(b["registered_agent"], "Agent Person")
        self.assertNotIn("owner_name", b)  # agent is never treated as owner

    def test_ambiguous_is_skipped(self):
        ca_sos._get = lambda *a: [{"EntityName": "Fixture Taqueria Inc", "EntityStatus": "Active"},
                                  {"EntityName": "Fixture Taqueria LLC", "EntityStatus": "Active"}]
        b = {"name": "Fixture Taqueria", "provenance": {}}
        self.assertFalse(ca_sos.enrich(b, "2026-01-01"))
        self.assertNotIn("year_founded", b)


if __name__ == "__main__":
    unittest.main()
