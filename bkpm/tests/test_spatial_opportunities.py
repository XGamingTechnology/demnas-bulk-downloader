import unittest
from bkpm.spatial_opportunities import project_feature

class ProjectPointTests(unittest.TestCase):
    def record(self, lon="111.72", lat="-7.15"):
        return {"url":"https://regionalinvestment.bkpm.go.id/peluang_investasi/detailed/1267",
                "kind":"peluang_proyek_detail",
                "longitude_raw":lon, "latitude_raw":lat,
                "investment_raw":"Rp 2,8T", "year_raw":"2022"}

    def test_coordinates_are_longitude_latitude(self):
        feature, status = project_feature(self.record())
        self.assertEqual(status, "ok")
        self.assertEqual(feature["geometry"]["coordinates"], [111.72, -7.15])
        self.assertEqual(feature["properties"]["investment_kind"], "investment_opportunity_not_realization")
        self.assertEqual(feature["properties"]["location_quality"], "published_coordinate_not_site_validated")

    def test_do_not_fabricate_missing_coordinates(self):
        feature, status = project_feature(self.record(lat=None))
        self.assertIsNone(feature)
        self.assertEqual(status, "coordinates_missing_or_invalid")

    def test_reject_invalid_range_and_non_project(self):
        self.assertEqual(project_feature(self.record(lon="200"))[1], "coordinates_out_of_range")
        self.assertEqual(project_feature(self.record(lon="0", lat="0"))[1], "coordinates_outside_indonesia_bbox")
        rec=self.record()
        rec["kind"]="realisasi_dataset_detail"
        self.assertEqual(project_feature(rec)[1],"not_project")

if __name__=="__main__":
    unittest.main()
