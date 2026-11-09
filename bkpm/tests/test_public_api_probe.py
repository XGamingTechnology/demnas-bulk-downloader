import unittest
from bkpm.public_api_probe import describe_json, ENDPOINTS

class PublicAPIProbeTests(unittest.TestCase):
    def test_object_schema_not_values(self):
        result = describe_json({"data": [{"id": 1234, "nama": "Rahasia"}], "count": 1})
        self.assertEqual(result["fields"]["data"]["length"], 1)
        self.assertEqual(result["fields"]["data"]["first_item_structure"]["keys"], ["id", "nama"])
        self.assertNotIn("Rahasia", str(result))
        self.assertNotIn("1234", str(result))
    def test_fixed_observed_endpoints(self):
        self.assertEqual(len(ENDPOINTS), 4)
        self.assertIn("/be/peluang/peluang_investasi_card/", ENDPOINTS.values())

if __name__ == "__main__":
    unittest.main()
