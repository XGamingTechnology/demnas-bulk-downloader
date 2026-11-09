import unittest
from bkpm.investment_inventory import prioritize_detail_links

class PrioritizationTests(unittest.TestCase):
    def test_recent_before_archives_and_project(self):
        base = "https://data.bkpm.go.id/dataset-detail/"
        links = [
            base + "data-realisasi-investasi-triwulan-i-tahun-2010-abc",
            "https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/868",
            base + "nilai-investasi-ekraf-tahun-2025",
            base + "data-realisasi-investasi-triwulan-iii-tahun-2026",
        ]
        result = prioritize_detail_links(links)
        self.assertIn("tahun-2026", result[0])
        self.assertIn("tahun-2025", result[1])
        self.assertIn("detailed/868", result[2])
        self.assertIn("tahun-2010", result[3])

    def test_deduplicate_without_creating_urls(self):
        urls = ["https://data.bkpm.go.id/dataset-detail/x"] * 2
        self.assertEqual(prioritize_detail_links(urls), urls[:1])

if __name__ == "__main__":
    unittest.main()
