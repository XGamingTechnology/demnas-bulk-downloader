import unittest
from bkpm.spatial_quality import audit_records

class SpatialQualityTests(unittest.TestCase):
    def test_flags_missing_coords_and_shared_points(self):
        records = [
            {"id_peluang": 1, "nama": "Proyek A", "lon": 111, "lat": -7},
            {"id_peluang": 2, "nama": "Proyek B", "lon": 111, "lat": -7},
            {"id_peluang": 3, "nama": "Proyek C", "lon": None, "lat": None},
        ]
        features = [
            {"type": "Feature", "properties": {"source_project_id": 1},
             "geometry": {"type": "Point", "coordinates": [111.0, -7.0]}},
            {"type": "Feature", "properties": {"source_project_id": 2},
             "geometry": {"type": "Point", "coordinates": [111.0, -7.0]}},
        ]
        report, missing, shared, coverage = audit_records(records, features)
        self.assertEqual(report["source_record_count"], 3)
        self.assertEqual(report["expected_valid_points"], 2)
        self.assertEqual(report["geojson_point_count"], 2)
        self.assertEqual(report["coordinate_failure_count"], 1)
        self.assertEqual(missing[0]["id_peluang"], "3")
        self.assertEqual(report["shared_coordinate_groups"], 1)
        self.assertEqual(shared[0]["project_count"], 2)
        self.assertFalse(report["expected_points_missing_from_geojson"])
        self.assertFalse(report["coordinate_mismatch_ids"])

    def test_detects_missing_exported_point(self):
        records = [{"id_peluang": 123, "lon": 111, "lat": -7}]
        report, _, _, _ = audit_records(records, [])
        self.assertEqual(report["expected_points_missing_from_geojson"], [123])

if __name__ == "__main__":
    unittest.main()
