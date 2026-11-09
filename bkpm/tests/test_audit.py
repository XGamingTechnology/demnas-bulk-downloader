import unittest
from bkpm.audit import validate_collection

class AuditValidationTests(unittest.TestCase):
    def test_valid_geojson_metadata(self):
        doc = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "NAME_0": "Indonesia",
                    "NAME_1": "Contoh",
                    "KODE": "00",
                    "Wilayah": "Tengah"
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[110, -7], [111, -7], [111, -6], [110, -7]]]]
                }
            }]
        }
        features, report = validate_collection(doc, "wilayah_tengah.geojson")
        self.assertEqual(len(features), 1)
        self.assertEqual(report["feature_count"], 1)
        self.assertEqual(report["wrong_region_label_count"], 0)
        self.assertEqual(report["geometry_types"], {"MultiPolygon": 1})

    def test_wrong_region_not_silently_accepted(self):
        doc = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "NAME_0": "Indonesia", "NAME_1": "X",
                    "KODE": "00", "Wilayah": "Barat"
                },
                "geometry": None
            }]
        }
        _, report = validate_collection(doc, "wilayah_tengah.geojson")
        self.assertEqual(report["wrong_region_label_count"], 1)
        self.assertEqual(report["geometry_types"], {"null": 1})

    def test_non_collection_rejected(self):
        with self.assertRaises(ValueError):
            validate_collection({"type": "Feature"}, "wilayah_barat.geojson")

if __name__ == "__main__":
    unittest.main()
