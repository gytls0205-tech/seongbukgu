"""성북구 재개발 구술 지도 — Python 표준 라이브러리 웹서버.
실행: python app.py  (기본 http://localhost:5000)
카카오 지도는 클라이언트의 Kakao Maps JavaScript SDK가 표시합니다.
행정동 경계는 파이썬이 공개 GeoJSON을 한 번 받아 캐시합니다.
"""

# https://developers.kakao.com 에서 받은 JavaScript Key입니다.
# 사용 설정: 카카오맵 > 사용 설정 ON / JavaScript SDK 도메인 http://localhost:8000
from __future__ import annotations

HOST="127.0.0.1"
PORT=5000


import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
STATIC = BASE / 'static'
RECORDS = DATA / 'records.json'
BOUNDARIES = DATA / 'seongbuk_boundaries_20261001.geojson'
BOUNDARY_SOURCE = (
    'https://raw.githubusercontent.com/vuski/admdongkor/master/'
    'ver20261001/HangJeongDong_ver20261001.geojson'
)
REGIONS = {
    '정릉동': ['정릉1동', '정릉2동', '정릉3동', '정릉4동'],
    '길음동': ['길음1동', '길음2동'],
    '장위동': ['장위1동', '장위2동', '장위3동'],
}
VALID_SUBDONGS = {name: region for region, items in REGIONS.items() for name in items}


def read_env():
    """선택적 .env 읽기. 키는 서버에서 SDK URL을 만들 때 브라우저에 전달됩니다."""
    d = {}
    envfile = BASE / '.env'
    if envfile.exists():
        for raw in envfile.read_text(encoding='utf-8-sig').splitlines():
            if not raw.strip() or raw.lstrip().startswith('#') or '=' not in raw:
                continue
            k, v = raw.split('=', 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    d.update(os.environ)
    return d


def load_records():
    records = json.loads(RECORDS.read_text(encoding='utf-8'))
    assert len(records) == 14, '구술 기록이 13개여야 합니다.'
    return records


def select_seongbuk_features(all_features):
    """2026-10-01 경계 중 성북구 정릉/길음/장위 9개 행정동만 선택."""
    selected = {}
    for feature in all_features:
        props = feature.get('properties') or {}
        fullname = str(props.get('adm_nm') or props.get('adm_nm2') or props.get('name') or '')
        m = re.search(r'(정릉[1-4]동|길음[12]동|장위[1-3]동)$', fullname)
        if not m:
            continue
        subdong = m.group(1)
        code = str(props.get('adm_cd2') or props.get('adm_cd_10') or '')
        sgg = str(props.get('sggnm') or props.get('sgg_nm') or '')
        if '성북구' not in fullname and '성북구' not in sgg and not code.startswith('11290'):
            continue
        geometry = feature.get('geometry') or {}
        if geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            continue
        if subdong in selected:
            raise ValueError(f'중복 행정동 경계: {subdong}')
        selected[subdong] = {
            'type': 'Feature',
            'properties': {'name': subdong, 'region': VALID_SUBDONGS[subdong]},
            'geometry': geometry,
        }
    missing = set(VALID_SUBDONGS) - set(selected)
    if missing:
        raise ValueError(f'2026년 경계에서 일부 행정동을 찾지 못했습니다: {sorted(missing)}')
    return {
        'type': 'FeatureCollection',
        'features': [selected[name] for names in REGIONS.values() for name in names],
        'metadata': {
            'reference_date': '2026-10-01',
            'source': '통계청 SGIS, 가공: vuski/admdongkor, CC BY 4.0',
            'source_url': 'https://github.com/vuski/admdongkor',
            'geometry_note': '9개 행정동을 3개 구술 지역으로 묶어 표시. 구술 기록을 개별 세부 행정동에 임의 배정하지 않음',
        },
    }


def get_boundaries():
    if BOUNDARIES.exists():
        return json.loads(BOUNDARIES.read_text(encoding='utf-8'))
    req = urllib.request.Request(
        BOUNDARY_SOURCE,
        headers={'User-Agent': 'SeongbukOralMap/1.0 (education/research)', 'Accept': 'application/geo+json,application/json'},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        # 원본 약 33 MB. 비정상적으로 큰 응답을 방지합니다.
        content = response.read(55 * 1024 * 1024 + 1)
    if len(content) > 55 * 1024 * 1024:
        raise ValueError('행정경계 응답 크기가 제한을 초과했습니다.')
    raw = json.loads(content.decode('utf-8-sig'))
    if raw.get('type') != 'FeatureCollection':
        raise ValueError('행정동 경계 원본이 GeoJSON FeatureCollection이 아닙니다.')
    reduced = select_seongbuk_features(raw.get('features', []))
    tmp = BOUNDARIES.with_suffix('.tmp')
    tmp.write_text(json.dumps(reduced, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(BOUNDARIES)
    return reduced


def summarize(records):
    return {r: {
        'records': sum(x['region'] == r for x in records),
        'positive': sum(x['region'] == r and '긍정' in x['stances'] for x in records),
        'negative': sum(x['region'] == r and '부정' in x['stances'] for x in records),
    } for r in REGIONS}


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200, mime='application/json; charset=utf-8', no_cache=False):
        if isinstance(data, (dict, list)):
            buf = json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif isinstance(data, str):
            buf = data.encode('utf-8')
        else:
            buf = data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(buf)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store' if no_cache else 'public, max-age=1800')
        self.end_headers()
        self.wfile.write(buf)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path in ('/', '/index.html'):
                return self.reply((STATIC/'index.html').read_bytes(), mime='text/html; charset=utf-8', no_cache=True)
            if path.startswith('/static/'):
                target = (STATIC/path.removeprefix('/static/')).resolve()
                if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                    return self.reply({'error':'파일을 찾지 못했습니다.'}, 404)
                suffix = target.suffix
                mt = {'.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}.get(suffix, 'application/octet-stream')
                return self.reply(target.read_bytes(), mime=mt, no_cache=True)
            if path == '/api/config':
                key = read_env().get('KAKAO_JAVASCRIPT_KEY', '').strip()
                return self.reply({'kakao_js_key': key, 'has_key': bool(key), 'regions': REGIONS}, no_cache=True)
            if path == '/api/records':
                qs = parse_qs(url.query)
                region = qs.get('region', ['전체'])[0]
                stance = qs.get('stance', ['전체'])[0]
                records = load_records()
                if region not in ('전체', *REGIONS):
                    return self.reply({'error':'올바르지 않은 지역입니다.'}, 400)
                if stance not in ('전체', '긍정', '부정'):
                    return self.reply({'error':'올바르지 않은 반응 유형입니다.'}, 400)
                return self.reply([r for r in records if (region == '전체' or r['region'] == region) and (stance == '전체' or stance in r['stances'])])
            if path == '/api/summary':
                records = load_records()
                return self.reply({'by_region':summarize(records),'total_records':len(records),'total_positive':sum('긍정' in r['stances'] for r in records),'total_negative':sum('부정' in r['stances'] for r in records)})
            if path == '/api/boundaries':
                try:
                    return self.reply(get_boundaries())
                except Exception as e:
                    return self.reply({'error':'공개 행정경계 데이터를 받아오지 못했습니다.', 'detail':str(e), 'source_url':BOUNDARY_SOURCE}, 503, no_cache=True)
            if path == '/source.pdf':
                return self.reply((DATA/'source.pdf').read_bytes(), mime='application/pdf')
            if path == '/health':
                return self.reply({'status':'ok', 'records':len(load_records())})
            return self.reply({'error':'요청한 페이지를 찾지 못했습니다.'}, 404)
        except Exception as e:
            print(f'[ERROR] {path}: {e}', file=sys.stderr)
            return self.reply({'error':'서버 처리 중 오류가 발생했습니다.', 'detail':str(e)}, 500, no_cache=True)


def main():
    env = read_env()
    host = env.get('HOST','127.0.0.1')
    port = int(env.get('PORT', '5000'))
    print(f'성북구 재개발 구술 지도: http://localhost:{port}')
    if not env.get('KAKAO_JAVASCRIPT_KEY'):
        print('KAKAO_JAVASCRIPT_KEY 미설정: 구술 자료는 열람 가능, 지도 표시에는 키가 필요합니다.')
    print('지도를 처음 실행할 때 공개 GeoJSON을 내려받아 9개 행정동 경계만 로컬에 캐시합니다.')
    with ThreadingHTTPServer((host, port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\n서버를 종료합니다.')

if __name__ == '__main__':
    main()
