import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import download_minerba as catalog
import download_wiup as core
import shapefile


def args(**kwargs):
    values = dict(dataset=['all'], all=True, province=None, company=None, wiup=None,
                  commodity=None, permit_type=None, delay=0, batch_size=100,
                  output=Path('.'), count_only=False, resume=False)
    values.update(kwargs)
    return SimpleNamespace(**values)


class Tests(unittest.TestCase):
    def test_catalog_selection(self):
        self.assertEqual(len(catalog.select_datasets(['all'])), 11)
        self.assertEqual(len(catalog.select_datasets(['batas-laut'])), 6)
        self.assertEqual(catalog.select_datasets(['wiup', 'wiup']), ['wiup'])
        with self.assertRaises(core.DownloadError):
            catalog.select_datasets(['all', 'wiup'])

    def test_unsupported_filter_fails_before_requests(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(catalog, 'Client') as factory:
                with self.assertRaises(core.DownloadError):
                    catalog.run(args(province='Sumatera Barat', all=False, output=Path(d)), factory)
                factory.assert_not_called()
                self.assertFalse((Path(d) / 'index.json').exists())

    def test_iup_filter_escape(self):
        where = catalog.filter_where(args(all=False, permit_type='IUP', company="a'b"), catalog.CATALOG['wiup'])
        self.assertIn("UPPER(jenis_izin) = 'IUP'", where)
        self.assertIn("'A''B'", where)

    def test_all_reports_partial_failure_and_continues(self):
        with tempfile.TemporaryDirectory() as d:
            def fake_download(client, where, output, batch, resume, prefix):
                if prefix == 'batubara':
                    raise core.DownloadError('test rejected')
                return {'count': 1}
            with patch.object(catalog, 'download', side_effect=fake_download) as call:
                code = catalog.run(args(output=Path(d)), lambda *a: object())
                self.assertEqual(call.call_count, 11)
            report = json.loads((Path(d) / 'index.json').read_text())
            self.assertEqual(code, 1)
            self.assertEqual(report['status'], 'incomplete')
            self.assertEqual(report['datasets']['batubara']['status'], 'failed')
            self.assertEqual(report['datasets']['laut-zona-tambahan']['status'], 'complete')

    def test_point_line_and_empty_export(self):
        cases = [('esriGeometryPoint', {'x': 100, 'y': -1}, shapefile.POINT, 'Point'),
                 ('esriGeometryPolyline', {'paths': [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]},
                  shapefile.POLYLINE, 'MultiLineString')]
        for kind, geometry, expected, geo_type in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                metadata = {'geometryType': kind, 'fields': [{'name': 'id', 'type': 'esriFieldTypeOID'},
                            {'name': 'shape', 'type': 'esriFieldTypeGeometry'}]}
                path = Path(d)
                core.export(path, [{'attributes': {'id': 1}, 'geometry': geometry}], metadata, 'sample')
                with shapefile.Reader(str(path / 'sample')) as reader:
                    self.assertEqual(reader.shapeType, expected)
                    self.assertEqual(len(reader), 1)
                    self.assertEqual(len(reader.fields), 2)  # deletion flag plus id, no Shape DBF field
                data = json.loads((path / 'sample.geojson').read_text())
                self.assertEqual(data['features'][0]['geometry']['type'], geo_type)
                core.export(path, [], metadata, 'empty')
                with shapefile.Reader(str(path / 'empty')) as reader:
                    self.assertEqual(len(reader), 0)

    def test_invalid_point_or_line_fails(self):
        for kind, source in [('esriGeometryPoint', {'x': float('nan'), 'y': 1}),
                             ('esriGeometryPolyline', {'paths': [[[1, 1]]]})]:
            with self.assertRaises(core.DownloadError):
                core.feature_geometry(source, kind)

    def test_invalid_polygon_and_null_preserved_with_report(self):
        ring = [[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]
        features = [{'attributes': {'objectid': 1}, 'geometry': {'rings': [ring]}},
                    {'attributes': {'objectid': 2}, 'geometry': None}]
        metadata = {'geometryType': 'esriGeometryPolygon',
                    'fields': [{'name': 'objectid', 'type': 'esriFieldTypeOID'}]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            issues = core.export(path, features, metadata, 'sample')
            self.assertEqual(len(issues), 2)
            with shapefile.Reader(str(path / 'sample')) as reader:
                self.assertEqual(len(reader), 2)
                self.assertEqual([list(p) for p in reader.shape(0).points], ring)
                self.assertEqual(reader.shape(1).shapeType, shapefile.NULL)
            raw = json.loads((path / 'sample_raw.json').read_text())
            self.assertEqual(raw['features'], features)
            geo = json.loads((path / 'sample.geojson').read_text())
            self.assertIsNone(geo['features'][1]['geometry'])


if __name__ == '__main__':
    unittest.main()
