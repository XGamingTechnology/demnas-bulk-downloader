import unittest
from bkpm.project_discovery import accepted_project_url, observed_links

class ProjectDiscoveryTests(unittest.TestCase):
    def test_observed_public_links_only(self):
        base = "https://regionalinvestment.bkpm.go.id/peluang_investasi"
        html = '<a href="/peluang_investasi/detailed/1267">Bioetanol</a><a href="https://example.org/peluang_investasi/detailed/5">External</a>'
        rows = observed_links(html, base)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"],
                         "https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/1267")

    def test_reject_unsafe_and_unobserved(self):
        self.assertIsNone(accepted_project_url("https://example.org/peluang_investasi/detailed/1267"))
        self.assertIsNone(accepted_project_url("http://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/1267"))
        self.assertIsNone(accepted_project_url("https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/foo"))
        self.assertEqual(observed_links("<h1>185 proyek</h1>",
                          "https://regionalinvestment.bkpm.go.id/peluang_investasi"), [])

if __name__ == "__main__":
    unittest.main()
