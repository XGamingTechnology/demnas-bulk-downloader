import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import shapefile
from shapely.geometry import shape

spec = importlib.util.spec_from_file_location('wiup', Path(__file__).parents[1] / 'download_wiup.py')
wiup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiup)


def feature(i):
    return {'attributes': {'objectid': i, 'nama': 'LUMPO'},
            'geometry': {'rings': [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}


class FakeClient:
    service = 'https://example.test/MapServer/0'
    def __init__(self):
        self.calls = []
        self.drift = False
    def ids(self, where):
        return 'objectid', [1, 2, 3] if self.drift else [1, 2]
    def request(self, params, query=True):
        if not query:
            return {'geometryType': 'esriGeometryPolygon', 'maxRecordCount': 100,
                    'fields': [{'name': 'objectid'}, {'name': 'nama'}]}
        if params.get('returnCountOnly'):
            return {'count': 2}
        ids = list(map(int, params['objectIds'].split(',')))
        self.calls.append(ids)
        if len(ids) > 1:
            return {'features': [feature(ids[0])], 'exceededTransferLimit': True}
        return {'features': [feature(ids[0])]}


class Tests(unittest.TestCase):
    def test_transfer_limit_split(self):
        client = FakeClient()
        found = wiup.fetch_batch(client, [1, 2], 'objectid')
        self.assertEqual([f['attributes']['objectid'] for f in found], [1, 2])
        self.assertEqual(client.calls, [[1, 2], [1], [2]])

    def test_missing_duplicate_and_unexpected_fail(self):
        for fs in [[feature(1)], [feature(1), feature(1)], [feature(1), feature(3)]]:
            with self.assertRaises(wiup.DownloadError):
                wiup.check_batch({'features': fs}, [1, 2], 'objectid')

    def test_holes_and_disjoint_shells(self):
        rings = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                 [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]],
                 [[20, 0], [21, 0], [21, 1], [20, 1], [20, 0]]]
        result = shape(wiup.geometry(rings))
        self.assertEqual(result.geom_type, 'MultiPolygon')
        self.assertEqual(result.area, 97)

    def test_resume_exports_and_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            client = FakeClient()
            wiup.download(client, '1=1', path, 100)
            with shapefile.Reader(str(path / 'wiup')) as reader:
                self.assertEqual(len(reader), 2)
            client.calls.clear()
            wiup.download(client, '1=1', path, 100, True)
            self.assertEqual(client.calls, [])
            next((path / 'cache').glob('*.json')).write_text('{broken')
            wiup.download(client, '1=1', path, 100, True)
            self.assertTrue(client.calls)
            with self.assertRaises(wiup.DownloadError):
                wiup.download(client, "nama_usaha = 'OTHER'", path, 100, True)

    def test_drift_blocks_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            original = client.ids
            n = [0]
            def ids(where):
                n[0] += 1
                client.drift = n[0] > 1
                return original(where)
            client.ids = ids
            path = Path(directory)
            with self.assertRaises(wiup.DownloadError):
                wiup.download(client, '1=1', path, 100)
            self.assertEqual(json.loads((path / 'manifest.json').read_text())['status'], 'downloading')
            self.assertFalse((path / 'wiup_shp.zip').exists())

    def test_utf8_byte_limit(self):
        self.assertLessEqual(len(wiup.text_bytes('é' * 200).encode()), 254)

    def test_auth_error_no_retry(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"error":{"code":499,"message":"Token Required"}}'
        with patch.object(wiup.urllib.request, 'urlopen', return_value=Response()) as request:
            with self.assertRaises(wiup.DownloadError):
                wiup.Client(delay=0).request({'where': '1=1'})
            self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
