import unittest
from bkpm.download_manifest import accepted_public_link, extract_download_manifest

PAGE = "https://data.bkpm.go.id/dataset-detail/abc"
UID = "a306759c-a624-4fcd-b686-400e42c19396"

class DownloadManifestTests(unittest.TestCase):
    def test_public_html_with_jsonld_and_button(self):
        html = """
        <script type="application/ld+json">
          {"distribution":{"contentUrl":"https://data.bkpm.go.id/dataset/generate-download-zip/a306759c-a624-4fcd-b686-400e42c19396/file"}}
        </script>
        <a onclick="handleUnduhDisclamer(event, 'file', 'a306759c-a624-4fcd-b686-400e42c19396', 830)">Unduh</a>
        <form action="/unduh/store-disclamer"></form>
        """
        rows = extract_download_manifest(html, PAGE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_uuid"], UID)
        self.assertEqual(rows[0]["upload_file_id"], "830")
        self.assertTrue(rows[0]["button_url"].endswith("upload_file_id=830"))
        self.assertTrue(rows[0]["disclaimer_form_present"])
        self.assertFalse(rows[0]["download_verified"])

    def test_reject_foreign_or_guessed(self):
        self.assertIsNone(accepted_public_link("https://evil.example/dataset/generate-download-zip/"+UID+"/file"))
        self.assertIsNone(accepted_public_link("http://data.bkpm.go.id/dataset/generate-download-zip/"+UID+"/file"))
        self.assertIsNone(accepted_public_link("https://data.bkpm.go.id/dataset/generate-download-zip/"+UID+"/file?token=secret"))
        self.assertEqual(extract_download_manifest("<div>Nothing</div>",PAGE), [])

if __name__ == "__main__":
    unittest.main()
