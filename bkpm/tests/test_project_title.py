import unittest
from bkpm.project_title import get_project_title

class TitleTests(unittest.TestCase):
    def test_current_breadcrumb_over_unrelated_recommendations(self):
        html = """
          <h1>Peluang Investasi</h1>
          <nav class="breadcrumb"><ol>
          <li>Beranda</li><li>Peluang Investasi</li>
          <li>Industri Bioetanol</li></ol></nav>
          <main><h3>Informasi</h3><p>Nilai Investasi: Rp 2,8T</p></main>
          <section><h2>Smart Eco-Industrial Park (SEIP) Lamongan</h2></section>
        """
        self.assertEqual(get_project_title(html),
                         ("Industri Bioetanol", "dom_breadcrumb"))

    def test_jsonld_breadcrumb_over_recommendation(self):
        html = """
          <script type="application/ld+json">{
            "@type": "BreadcrumbList",
            "itemListElement": [
              {"position":1,"name":"Beranda"},
              {"position":2,"name":"Peluang Investasi"},
              {"position":3,"name":"Industri Fatty Amine"}
            ]
          }</script>
          <h3>Smart Eco-Industrial Park (SEIP) Lamongan</h3>
        """
        self.assertEqual(get_project_title(html),
                         ("Industri Fatty Amine", "jsonld_breadcrumb"))

    def test_breadcrumb_text_near_details(self):
        html = """
        <header><p>Beranda</p><p>Peluang Investasi</p>
        <p>Potensi Pelabuhan Sorong Sebagai Simpul Tol Laut</p></header>
        <main><div>Informasi</div><div>Kode KBLI: Data Tidak Tersedia</div>
        <div>Nilai Investasi: Rp 5,4T</div></main>
        <section><h2>Terminal Dan Regasifikasi Liquefied Natural Gas (LNG)</h2></section>
        """
        self.assertEqual(get_project_title(html),
                         ("Potensi Pelabuhan Sorong Sebagai Simpul Tol Laut",
                          "breadcrumb_text_near_details"))

    def test_no_breadcrumb_never_guess_from_recommendations(self):
        html = """<h1>Peluang Investasi</h1>
        <main><div>Informasi</div><p>Nilai Investasi: Rp 5,4T</p></main>
        <h3>Smart Eco-Industrial Park (SEIP) Lamongan</h3>"""
        self.assertEqual(get_project_title(html), (None, "not_found"))

    def test_unusable_breadcrumb_fails_closed(self):
        html = """<nav class="breadcrumb"><ol><li>Beranda</li>
        <li>Peluang Investasi</li></ol></nav>
        <h2>Peternakan Unggas Terintegrasi</h2>"""
        self.assertEqual(get_project_title(html), (None, "not_found"))

if __name__ == "__main__":
    unittest.main()
