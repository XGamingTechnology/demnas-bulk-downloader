import unittest
from bkpm.project_title import get_project_title

class TitleTests(unittest.TestCase):
    def test_specific_heading_over_generic(self):
        html = '<h1>Peluang Investasi</h1><main><h2>Industri Bioetanol</h2><p>Kabupaten Bojonegoro</p><h3>Informasi</h3></main>'
        self.assertEqual(get_project_title(html), ("Industri Bioetanol", "detail_heading"))

    def test_breadcrumb_over_generic(self):
        html = '<h1>Peluang Investasi</h1><nav aria-label="breadcrumb"><ol><li>Beranda</li><li>Industri Fatty Amine</li></ol></nav><div>Informasi</div>'
        self.assertEqual(get_project_title(html), ("Industri Fatty Amine", "breadcrumb"))

    def test_prose_before_information(self):
        html = '<h1>Peluang Investasi</h1><section>Industri Fatty Amine</section><div>Kota Bontang</div><div>Kalimantan Timur</div><div>Industri</div><div>Informasi</div>'
        self.assertEqual(get_project_title(html), ("Industri Fatty Amine", "pre_information_text"))

    def test_no_placeholder_title(self):
        self.assertEqual(get_project_title("<h1>Peluang Investasi</h1><div>Informasi</div>"),
                         (None, "not_found"))

if __name__ == "__main__":
    unittest.main()
