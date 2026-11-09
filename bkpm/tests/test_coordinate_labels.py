import unittest
from bkpm.investment_inventory import parse_detail
from bkpm.spatial_opportunities import project_feature

URL = "https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/868"

class CoordinateLabelTests(unittest.TestCase):
    def test_html_with_colons(self):
        html="<main><div>Longitude: 131.248628</div><div>Latitude: -0.877469</div></main>"
        result=parse_detail(html,URL)
        point,status=project_feature(result)
        self.assertEqual(status,"ok")
        self.assertEqual(point["geometry"]["coordinates"],[131.248628,-0.877469])

    def test_html_without_colons(self):
        html="<main><span>Longitude</span><span>131.248628</span><span>Latitude</span><span>-0.877469</span></main>"
        result=parse_detail(html,URL)
        point,status=project_feature(result)
        self.assertEqual(status,"ok")
        self.assertEqual(point["geometry"]["coordinates"],[131.248628,-0.877469])

if __name__=="__main__":
    unittest.main()
