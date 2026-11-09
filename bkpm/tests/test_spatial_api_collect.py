import unittest
from bkpm.spatial_api_collect import make_point, parse_region_payload, export_commodities

class SpatialAPICollectTests(unittest.TestCase):
    def test_valid_project_point_preserves_original_fields(self):
        row={"id_peluang":1267,"nama":"Industri Bioetanol",
             "lon":111.7199,"lat":-7.1548,"nilai_investasi":"Rp 2,8T"}
        f,status=make_point(row)
        self.assertEqual(status,"ok")
        self.assertEqual(f["geometry"]["coordinates"],[111.7199,-7.1548])
        self.assertEqual(f["properties"]["nama"],"Industri Bioetanol")
        self.assertEqual(f["properties"]["dataset_role"],"investment_opportunity_not_realization")

    def test_invalid_coordinates_not_guessed(self):
        for lon,lat in [(None,1), (999,0), (0,0), (float("nan"),2)]:
            f,_=make_point({"id_peluang":1,"lon":lon,"lat":lat})
            self.assertIsNone(f)

    def test_pagination_metadata_validation(self):
        rows,meta=parse_region_payload({"success":True,"data":[{"id_peluang":1}],
                         "page":1,"pageSize":9,"totalPage":21,"totalRecords":185})
        self.assertEqual(len(rows),1)
        self.assertEqual(meta["totalPage"],21)
        with self.assertRaises(ValueError):
            parse_region_payload({"success":True,"data":[],"page":"1"})

    def test_original_commodity_structure(self):
        summary=export_commodities({"type":"FeatureCollection",
           "crs":{"type":"name","properties":{"name":"EPSG:4326"}},
           "features":[{"type":"Feature","properties":{"Komoditas":"Padi"},
                        "geometry":{"type":"Point","coordinates":[111,-7]}}]})
        self.assertEqual(summary["features"],1)
        self.assertEqual(summary["geometry_counts"]["Point"],1)
        self.assertEqual(summary["declared_crs"],"EPSG:4326")

if __name__=="__main__":
    unittest.main()
