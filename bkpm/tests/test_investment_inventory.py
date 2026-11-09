import unittest
from bkpm.investment_inventory import safe_url, links_from, parse_detail

class PublicInventoryTests(unittest.TestCase):
    def test_allowlist(self):
        self.assertEqual(safe_url("/dataset-detail/abc", "https://data.bkpm.go.id/dataset"),
                         "https://data.bkpm.go.id/dataset-detail/abc")
        for url in ["http://data.bkpm.go.id/dataset",
                    "https://example.com/dataset",
                    "https://data.bkpm.go.id/admin",
                    "https://regionalinvestment.bkpm.go.id/api/internal"]:
            self.assertIsNone(safe_url(url))

    def test_discovered_links(self):
        html = '<a href="/dataset-detail/test">a</a><a href="https://example.com/x">b</a>'
        self.assertEqual(links_from(html, "https://data.bkpm.go.id/dataset"),
                         ["https://data.bkpm.go.id/dataset-detail/test"])

    def test_project_metadata_not_invented(self):
        url = "https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/868"
        html = '<h1>Contoh</h1><div>Nilai Investasi: Rp 5,4T IRR: 11,5% Longitude: 131.248 Latitude: -0.877</div>'
        result = parse_detail(html, url)
        self.assertEqual(result["investment_raw"], "Rp 5,4T")
        self.assertEqual(result["irr_raw"], "11,5%")
        self.assertEqual(result["coordinate_qc"], "range_ok_location_unverified")
        self.assertIsNone(result["npv_raw"])

    def test_not_confuse_download_button_with_file(self):
        html = '<h2>Realisasi</h2><p>Format (CSV)</p><button>Unduh Data</button>'
        rec = parse_detail(html, "https://data.bkpm.go.id/dataset-detail/example")
        self.assertTrue(rec["download_label_visible"])
        self.assertFalse(rec["direct_file_href_visible"])
        self.assertEqual(rec["advertised_formats"], "CSV")

if __name__ == "__main__":
    unittest.main()
