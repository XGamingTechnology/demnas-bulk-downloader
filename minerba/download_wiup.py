#!/usr/bin/env python3
"""Snapshot the public ESDM WIUP polygon layer; never uses browser credentials."""
import argparse
import csv
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import shapefile
from shapely.geometry import Polygon, MultiPolygon, mapping

SERVICE = ('https://geoportal.esdm.go.id/monaresia/sharing/servers/'
           '3b305b4113384b41b7490479e0702093/rest/services/Pusat/WIUP_Publish/MapServer/0')
REFERER = 'https://geoportal.esdm.go.id/minerba/'
PRJ = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'


class DownloadError(RuntimeError):
    pass


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


class Client:
    def __init__(self, service=SERVICE, delay=0.5, attempts=4):
        self.service, self.delay, self.attempts = service.rstrip('/'), delay, attempts

    def request(self, params, query=True):
        url = self.service + ('/query' if query else '')
        payload = urllib.parse.urlencode(dict(params, f='json'))
        request = urllib.request.Request(
            url, data=payload.encode() if query else None,
            headers={'Referer': REFERER, 'User-Agent': 'WIUP-public-downloader/1.0'})
        if not query:
            request = urllib.request.Request(url + '?' + payload, headers=dict(request.headers))
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    result = json.load(response)
                if 'error' in result:
                    error = result['error']
                    code = error.get('code')
                    if code in (401, 403, 498, 499):
                        raise DownloadError(f'Akses ditolak ({code}); hentikan. Tidak mencoba melewati autentikasi.')
                    if not isinstance(code, int) or code < 500:
                        raise DownloadError(f'ArcGIS error: {error}')
                    raise OSError(f'ArcGIS sementara gagal: {error}')
                time.sleep(self.delay)
                return result
            except urllib.error.HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504):
                    raise DownloadError(f'HTTP {error.code}: unduhan dihentikan.') from error
                retry = error.headers.get('Retry-After', '')
                pause = min(60, int(retry)) if retry.isdigit() else min(30, 2 ** attempt)
                if attempt + 1 == self.attempts:
                    raise DownloadError(f'HTTP {error.code} setelah retry.') from error
                time.sleep(pause)
            except (OSError, ValueError) as error:
                if attempt + 1 == self.attempts:
                    raise DownloadError(f'Request gagal setelah retry: {error}') from error
                time.sleep(min(30, 2 ** attempt))
        raise DownloadError('Request gagal.')

    def ids(self, where):
        result = self.request({'where': where, 'returnIdsOnly': 'true'})
        ids = result.get('objectIds')
        field = result.get('objectIdFieldName')
        if not isinstance(ids, list) or not field or result.get('exceededTransferLimit'):
            raise DownloadError('Respons daftar ID tidak lengkap/valid.')
        if len(ids) != len(set(ids)):
            raise DownloadError('Daftar ID duplikat.')
        return field, sorted(ids)


def check_batch(data, ids, oid):
    features = data.get('features')
    if not isinstance(features, list):
        raise DownloadError('Respons fitur tidak valid.')
    actual = [f.get('attributes', {}).get(oid) for f in features]
    if len(actual) != len(set(actual)) or set(actual) != set(ids):
        raise DownloadError(f'Batch tidak lengkap: diharapkan {len(ids)}, diterima {len(actual)}.')
    if data.get('exceededTransferLimit'):
        raise DownloadError('Batch terpotong oleh layanan.')
    return features


def fetch_batch(client, ids, oid):
    data = client.request({'objectIds': ','.join(map(str, ids)), 'outFields': '*',
                           'returnGeometry': 'true', 'outSR': 4326})
    if data.get('exceededTransferLimit') and len(ids) > 1:
        middle = len(ids) // 2
        return fetch_batch(client, ids[:middle], oid) + fetch_batch(client, ids[middle:], oid)
    return check_batch(data, ids, oid)


def geometry(rings):
    """Ring nesting determines shells/holes, independent of source orientation."""
    polygons = [Polygon(r) for r in rings]
    if not polygons or any(p.is_empty or not p.is_valid for p in polygons):
        raise DownloadError('Ring polygon kosong atau tidak valid; raw tetap tersedia.')
    parent = []
    for i, p in enumerate(polygons):
        candidates = [j for j, q in enumerate(polygons)
                      if j != i and q.area > p.area and q.contains(p)]
        parent.append(min(candidates, key=lambda j: polygons[j].area) if candidates else None)
    def depth(i):
        return 0 if parent[i] is None else 1 + depth(parent[i])
    parts = [Polygon(rings[i], [rings[j] for j in range(len(rings))
                               if parent[j] == i and depth(j) % 2 == 1])
             for i in range(len(rings)) if depth(i) % 2 == 0]
    result = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    if not result.is_valid:
        raise DownloadError('Polygon gabungan tidak valid; raw tetap tersedia, tanpa perbaikan otomatis.')
    return mapping(result)


def text_bytes(value, limit=254):
    return str(value).encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def export(output, features, metadata):
    """Raw source is authoritative; SHP field map records DBF limitations."""
    fields = [f['name'] for f in metadata['fields']]
    save_json(output / 'wiup_raw.json', {'features': features, 'fields': metadata['fields'],
                                        'spatialReference': {'wkid': 4326}})
    converted = []
    for feature in features:
        attrs = feature['attributes']
        source = feature.get('geometry')
        if not source or not source.get('rings'):
            raise DownloadError(f'Geometry kosong untuk {attrs}; raw disimpan, ekspor dihentikan.')
        converted.append({'type': 'Feature', 'properties': attrs,
                          'geometry': geometry(source['rings'])})
    save_json(output / 'wiup.geojson', {'type': 'FeatureCollection', 'features': converted})
    with (output / 'wiup.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='raise')
        writer.writeheader()
        writer.writerows(f['attributes'] for f in features)
    field_map = {f'F{i:03d}': name for i, name in enumerate(fields)}
    truncated = []
    with shapefile.Writer(str(output / 'wiup'), shapeType=shapefile.POLYGON, encoding='utf-8') as writer:
        # String fields preserve original identifiers and epochs. Full values in raw/GeoJSON/CSV.
        for short in field_map:
            writer.field(short, 'C', size=254)
        for feature in features:
            writer.poly(feature['geometry']['rings'])
            values = []
            for field in fields:
                value = feature['attributes'].get(field)
                value = '' if value is None else str(value)
                if len(value.encode('utf-8')) > 254:
                    truncated.append({'id': feature['attributes'].get('objectid'), 'field': field})
                values.append(text_bytes(value))
            writer.record(*values)
    (output / 'wiup.prj').write_text(PRJ, encoding='ascii')
    (output / 'wiup.cpg').write_text('UTF-8', encoding='ascii')
    save_json(output / 'field_map.json', {'fields': field_map, 'truncated_values': truncated,
                                         'nulls': 'DBF null menjadi string kosong; lihat GeoJSON/raw.'})
    with zipfile.ZipFile(output / 'wiup_shp.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['wiup.shp', 'wiup.shx', 'wiup.dbf', 'wiup.prj', 'wiup.cpg', 'field_map.json']:
            archive.write(output / name, name)


def download(client, where, output, batch_size, resume=False):
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    metadata = client.request({}, query=False)
    if metadata.get('geometryType') != 'esriGeometryPolygon':
        raise DownloadError('Layer harus berupa polygon.')
    signature = {'service': client.service, 'where': where, 'fields': metadata.get('fields')}
    if manifest_path.exists():
        if not resume:
            raise DownloadError('Folder sudah memiliki snapshot. Gunakan --resume atau folder baru.')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('signature') != signature:
            raise DownloadError('Sumber/filter/schema berbeda dari snapshot tersimpan.')
        ids, oid = manifest['ids'], manifest['object_id_field']
    else:
        oid, ids = client.ids(where)
        count = client.request({'where': where, 'returnCountOnly': 'true'}).get('count')
        if count != len(ids):
            raise DownloadError('Jumlah ID berbeda dari count; layanan berubah, coba ulang.')
        manifest = {'signature': signature, 'ids': ids, 'object_id_field': oid,
                    'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'downloading'}
    manifest['status'] = 'downloading'
    save_json(manifest_path, manifest)
    cache = output / 'cache'
    cache.mkdir(exist_ok=True)
    batch_size = min(batch_size, metadata.get('maxRecordCount', 100))
    features = []
    for start in range(0, len(ids), batch_size):
        batch = ids[start:start + batch_size]
        key = hashlib.sha256(json.dumps(batch).encode()).hexdigest()
        path = cache / (key + '.json')
        if path.exists():
            try:
                found = check_batch(json.loads(path.read_text(encoding='utf-8')), batch, oid)
            except (ValueError, DownloadError):
                found = fetch_batch(client, batch, oid)
                save_json(path, {'features': found})
        else:
            found = fetch_batch(client, batch, oid)
            save_json(path, {'features': found})
        features.extend(found)
        print(f'{len(features)}/{len(ids)} fitur', flush=True)
    current_oid, current_ids = client.ids(where)
    if current_oid != oid or current_ids != ids:
        raise DownloadError('Daftar ID berubah selama unduhan. Gunakan folder baru untuk snapshot baru.')
    check_batch({'features': features}, ids, oid)
    export(output, features, metadata)
    manifest.update(status='complete', count=len(features),
                    finished_utc=datetime.now(timezone.utc).isoformat(),
                    consistency='ID set stable; attributes may change during collection')
    save_json(manifest_path, manifest)
    print(f'Selesai: {output / "wiup_shp.zip"}', flush=True)


def make_where(args):
    filters = []
    for option, field in [('province', 'nama_prov'), ('company', 'nama_usaha'),
                          ('wiup', 'kode_wiup'), ('commodity', 'komoditas')]:
        value = getattr(args, option)
        if value:
            filters.append(f"{field} = '{value.upper().replace(chr(39), chr(39) * 2)}'")
    if args.all and filters:
        raise DownloadError('--all tidak dapat digabung dengan filter.')
    if not args.all and not filters:
        raise DownloadError('Pilih --all atau minimal satu filter.')
    return ' AND '.join(filters) or '1=1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true', help='Semua fitur layer WIUP publik')
    for field in ['province', 'company', 'wiup', 'commodity']:
        parser.add_argument('--' + field, help='Filter sama persis (dapat digabung)')
    parser.add_argument('--output', type=Path, default=Path('minerba/output'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--count-only', action='store_true')
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--service', default=SERVICE, help='URL layer polygon ArcGIS publik')
    args = parser.parse_args()
    try:
        if args.batch_size < 1 or args.delay < 0 or not math.isfinite(args.delay):
            raise DownloadError('Batch harus positif dan delay harus finite >= 0.')
        where = make_where(args)
        client = Client(args.service, args.delay)
        if args.count_only:
            print(client.request({'where': where, 'returnCountOnly': 'true'}))
        else:
            download(client, where, args.output, args.batch_size, args.resume)
    except (DownloadError, OSError, ValueError, KeyError) as error:
        print(f'GAGAL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
