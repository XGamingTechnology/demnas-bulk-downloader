#!/usr/bin/env python3
"""Download the verified public Minerba catalog into separate dataset folders."""
import argparse
import sys
import math
from datetime import datetime, timezone
from pathlib import Path

from download_wiup import Client, DownloadError, SERVICE, download, save_json

ROOT = 'https://geoportal.esdm.go.id/'
GIS4 = ROOT + 'gis4/rest/services/BGD_TU/'
SEA = ROOT + 'gis1/rest/services/SJN/Batas_Laut_Indonesia/MapServer/'
CATALOG = {
    'wiup': {'url': SERVICE, 'title': 'Wilayah Izin Usaha Pertambangan',
             'filters': {'province': 'nama_prov', 'company': 'nama_usaha',
                         'wiup': 'kode_wiup', 'commodity': 'komoditas', 'permit_type': 'jenis_izin'}},
    'wp2025': {'url': ROOT + 'monaresia/sharing/servers/c1b5104a2502497cbdcaa8a8f2f5e8a7/'
               'rest/services/Pusat/Wilayah_Pertambangan_2025/MapServer/0',
               'title': 'Wilayah Pertambangan 2025',
               'filters': {'province': 'provinsi', 'commodity': 'komoditas'}},
    'batubara': {'url': GIS4 + 'Potensi_Batubara/MapServer/0', 'title': 'Potensi Batubara', 'filters': {}},
    'mineral-logam': {'url': GIS4 + 'Potensi_Sumber_Daya_dan_Cadangan_Mineral_Logam/MapServer/0',
                      'title': 'Potensi Mineral Logam', 'filters': {'commodity': 'jnskom'}},
    'mineral-nonlogam': {'url': GIS4 + 'Potensi_Mineral_Bukan_Logam_dan_Batuan/MapServer/0',
                         'title': 'Potensi Mineral Bukan Logam dan Batuan', 'filters': {'commodity': 'jnskombl'}},
}
for i, (key, title) in enumerate([
        ('landas-kontinen', 'Batas Landas Kontinen'), ('mou-perikanan', 'Batas MOU Fisheries'),
        ('teritorial', 'Batas Teritorial'), ('zee', 'Batas ZEE'),
        ('garis-pangkal', 'Garis Pangkal'), ('zona-tambahan', 'Zona Tambahan')]):
    CATALOG['laut-' + key] = {'url': SEA + str(i), 'title': title, 'filters': {}}


def select_datasets(names):
    names = names or ['wiup']
    if 'all' in names:
        if len(names) != 1:
            raise DownloadError('--dataset all harus dipakai sendiri.')
        return list(CATALOG)
    if 'batas-laut' in names:
        names = [n for n in names if n != 'batas-laut'] + [k for k in CATALOG if k.startswith('laut-')]
    return list(dict.fromkeys(names))


def filter_where(args, spec):
    conditions = []
    for option in ['province', 'company', 'wiup', 'commodity', 'permit_type']:
        value = getattr(args, option)
        if value:
            field = spec['filters'].get(option)
            if not field:
                raise DownloadError(f"{spec['title']} tidak mendukung --{option.replace('_', '-')}; gunakan --all.")
            safe = value.upper().replace("'", "''")
            conditions.append(f"UPPER({field}) = '{safe}'")
    if args.all and conditions:
        raise DownloadError('--all tidak dapat digabung dengan filter.')
    if not args.all and not conditions:
        raise DownloadError('Pilih --all untuk seluruh fitur, atau filter yang didukung dataset.')
    return ' AND '.join(conditions) or '1=1'


def run(args, client_factory=Client):
    names = select_datasets(args.dataset)
    # Validate every filter before any network request or output mutation.
    selections = [(name, CATALOG[name], filter_where(args, CATALOG[name])) for name in names]
    index = {'started_utc': datetime.now(timezone.utc).isoformat(),
             'status': 'running', 'datasets': {},
             'scope': 'Public catalog only; not all ESDM historical permits or documents'}
    if not args.count_only:
        args.output.mkdir(parents=True, exist_ok=True)
        save_json(args.output / 'index.json', index)
    failed = False
    for name, spec, where in selections:
        print(f'\n[{name}] {spec["title"]}', flush=True)
        entry = {'title': spec['title'], 'service': spec['url'], 'where': where}
        index['datasets'][name] = entry
        try:
            client = client_factory(spec['url'], args.delay)
            if args.count_only:
                count = client.request({'where': where, 'returnCountOnly': 'true'})
                if not isinstance(count.get('count'), int):
                    raise DownloadError('Respons jumlah fitur tidak valid.')
                entry.update(status='counted', count=count['count'])
                print(f'{count["count"]} fitur', flush=True)
            else:
                manifest = download(client, where, args.output / name,
                                    args.batch_size, args.resume, prefix=name)
                entry.update(status='complete', count=manifest['count'], folder=name)
                entry['geometry_issue_count'] = manifest.get('geometry_issue_count', 0)
        except (DownloadError, OSError, ValueError, KeyError) as error:
            failed = True
            entry.update(status='failed', error=str(error))
            print(f'GAGAL [{name}]: {error}', file=sys.stderr, flush=True)
        if not args.count_only:
            save_json(args.output / 'index.json', index)
    index.update(status='incomplete' if failed else ('counted' if args.count_only else 'complete'),
                 finished_utc=datetime.now(timezone.utc).isoformat())
    if not args.count_only:
        save_json(args.output / 'index.json', index)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', action='append', choices=list(CATALOG) + ['all', 'batas-laut'],
                        help='Default wiup; ulangi untuk beberapa dataset; all = seluruh katalog')
    parser.add_argument('--list-datasets', action='store_true')
    parser.add_argument('--all', action='store_true', help='Seluruh fitur setiap dataset yang dipilih')
    for name in ['province', 'company', 'wiup', 'commodity']:
        parser.add_argument('--' + name)
    parser.add_argument('--permit-type', help='Filter jenis_izin pada WIUP, misalnya IUP')
    parser.add_argument('--output', type=Path, default=Path('minerba/output/catalog'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--count-only', action='store_true')
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--delay', type=float, default=0.5)
    args = parser.parse_args()
    try:
        if args.list_datasets:
            for key, spec in CATALOG.items():
                filters = ', '.join('--' + f.replace('_', '-') for f in spec['filters']) or 'hanya --all'
                print(f'{key}: {spec["title"]}; filter: {filters}')
            return 0
        if args.batch_size < 1 or args.delay < 0 or not math.isfinite(args.delay):
            raise DownloadError('Batch harus positif dan delay harus finite >= 0.')
        return run(args)
    except (DownloadError, OSError, ValueError, KeyError) as error:
        print(f'GAGAL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
