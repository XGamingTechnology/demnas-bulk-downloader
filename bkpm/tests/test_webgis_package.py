import json
import tempfile
import unittest
from pathlib import Path

from bkpm.webgis_package import create_package

class WebGISPackageTests(unittest.TestCase):
    def test_packages_valid_snapshot_and_preserves_missing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input"
            output = Path(tmp) / "site"
            source.mkdir()
            rows = [{"id_peluang": 1, "nama": "A", "lon": 111, "lat": -7},
                    {"id_peluang": 2, "nama": "B", "lon": None, "lat": 0}]
            feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [111., -7.]},
                       "properties": {"source_project_id": 1, "nama": "A"}}
            data = {
              "region_records.json": {"records": rows},
              "bkpm_opportunities_api_points.geojson": {"type": "FeatureCollection", "features": [feature]},
              "bkpm_komoditas_original.geojson": {"type": "FeatureCollection", "features": []},
              "audit.json": {"reported_total_records": 2, "pagination_status": "all_reported_pages_reached"},
            }
            for filename, contents in data.items():
                (source / filename).write_text(json.dumps(contents), encoding="utf-8")
            result = create_package(source, output)
            self.assertEqual(result["mapped_project_count"], 1)
            self.assertEqual(result["missing_project_coordinate_count"], 1)
            missing = json.loads((output / "data/projects_without_coordinates.json").read_text())
            self.assertEqual(missing[0]["id_peluang"], "2")

    def test_refuses_incomplete_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input"
            source.mkdir()
            data = {
              "region_records.json": {"records": []},
              "bkpm_opportunities_api_points.geojson": {"type": "FeatureCollection", "features": []},
              "bkpm_komoditas_original.geojson": {"type": "FeatureCollection", "features": []},
              "audit.json": {"reported_total_records": 185, "pagination_status": "max_pages_reached_not_complete"},
            }
            for filename, contents in data.items():
                (source / filename).write_text(json.dumps(contents), encoding="utf-8")
            with self.assertRaises(ValueError):
                create_package(source, Path(tmp) / "site")

if __name__ == "__main__":
    unittest.main()
