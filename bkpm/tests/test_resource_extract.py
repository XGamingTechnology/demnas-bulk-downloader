import unittest
from bkpm.resource_extract import extract_resources

PAGE = "https://data.bkpm.go.id/dataset-detail/example"

class SourceResourceTests(unittest.TestCase):
    def test_two_advertised_files_without_links(self):
        html = """
        <h3>Sumber data</h3>
        <h6>Realisasi_Triwulan_III_2026 (CSV)</h6>
        <p>Tipe Data: Upload File (CSV)</p><button>Unduh Data</button>
        <h6>Realisasi_Triwulan_III_2026 (JSON)</h6>
        <a href="#">Unduh Data</a>
        <h3>Metadata</h3>
        """
        rows = extract_resources(html, PAGE)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["resource_format"] for r in rows}, {"CSV", "JSON"})
        self.assertTrue(all(not r["direct_file_url_candidate"] for r in rows))

    def test_explicit_file_link_only(self):
        html = """
        <section><h6>Project_data (CSV)</h6>
        <a href="/files/example.csv">Unduh</a></section>
        """
        rows = extract_resources(html, PAGE)
        self.assertEqual(rows[0]["direct_file_url_candidate"],
                         "https://data.bkpm.go.id/files/example.csv")
        self.assertFalse(rows[0]["file_download_verified"])

    def test_foreign_file_link_rejected(self):
        html = """<section><h6>Project_data (CSV)</h6>
        <a href="https://example.com/file.csv">Unduh</a></section>"""
        self.assertEqual(extract_resources(html, PAGE)[0]["direct_file_url_candidate"], "")

if __name__ == "__main__":
    unittest.main()
