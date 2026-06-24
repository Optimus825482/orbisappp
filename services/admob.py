"""
ORBIS Google AdMob API wrapper.
Server-side reklam raporlarını çek (admin dashboard için).
OAuth2: refresh_token + client_id + client_secret.
Fail-closed: credential yoksa None.
Fail-quiet: 403 (API disabled) / 401 (invalid token) gibi terminal hatalarda
uzun süre (12 saat) tekrar denemeyi durdurur.
"""
import os
import json
import time
import logging
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # 1 dakika — admin dashboard taze veri göstermek için
_cache: Dict[str, tuple] = {}

TOKEN_URL = 'https://oauth2.googleapis.com/token'
ADMob_API = 'https://admob.googleapis.com/v1'

# Terminal hata sonrası cooldown
_FATAL_COOLDOWN = 12 * 3600  # 12 saat
_fatal_until: float = 0.0
_fatal_reason: str = ''


def _is_in_cooldown() -> bool:
    global _fatal_until
    return _fatal_until and time.time() < _fatal_until


def _mark_short_cooldown(seconds: int, reason: str):
    global _fatal_until, _fatal_reason
    _fatal_until = time.time() + seconds
    _fatal_reason = reason
    logger.warning('[AdMob] entering %ss cooldown: %s', seconds, reason)


def _mark_fatal(reason: str):
    global _fatal_until, _fatal_reason
    _fatal_until = time.time() + _FATAL_COOLDOWN
    _fatal_reason = reason
    logger.warning('[AdMob] entering %sh cooldown: %s', int(_FATAL_COOLDOWN/3600), reason)

# AdMob 'DATE' dimension değeri "YYYYMMDD" → "23 Haz" gibi kısa Türkçe etiket
_MONTHS_TR = ['', 'Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz',
              'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']


def _fmt_date(d: str) -> str:
    if not d or len(d) < 8 or not d.isdigit():
        return d
    try:
        day = int(d[6:8])
        month = int(d[4:6])
        return f'{day} {_MONTHS_TR[month]}'
    except (ValueError, IndexError):
        return d


def _get_config() -> Optional[Dict[str, str]]:
    """OAuth2 config. None dönerse admin dashboard 'credentials missing' gösterir."""
    cfg = {
        'client_id': os.environ.get('ADMOB_CLIENT_ID'),
        'client_secret': os.environ.get('ADMOB_CLIENT_SECRET'),
        'refresh_token': os.environ.get('ADMOB_REFRESH_TOKEN'),
        'publisher_id': os.environ.get('ADMOB_PUBLISHER_ID'),
    }
    if all(cfg.values()):
        return cfg
    return None


def _cache_get(key: str):
    if key in _cache:
        expires_at, value = _cache[key]
        if expires_at > time.time():
            return value
        _cache.pop(key, None)
    return None


def _cache_set(key: str, value, ttl: int = CACHE_TTL):
    _cache[key] = (time.time() + ttl, value)


def _get_access_token(cfg: Dict[str, str]) -> Optional[str]:
    if _is_in_cooldown():
        return None
    cache_key = 'access_token'
    cached = _cache_get(cache_key)
    if cached:
        return cached
    try:
        resp = requests.post(TOKEN_URL, data={
            'client_id': cfg['client_id'],
            'client_secret': cfg['client_secret'],
            'refresh_token': cfg['refresh_token'],
            'grant_type': 'refresh_token',
        }, timeout=15)
        if resp.status_code in (401, 403):
            try:
                err = resp.json().get('error_description') or resp.json().get('error') or ''
            except Exception:
                err = resp.text[:200]
            _mark_fatal(f'auth HTTP {resp.status_code}: {err[:150]}')
            return None
        resp.raise_for_status()
        token = resp.json().get('access_token')
        if token:
            _cache_set(cache_key, token, ttl=3500)  # 1h-100s buffer
        return token
    except Exception:
        logger.exception('[AdMob] access_token fetch failed')
        return None


def _api_get(path: str, cfg: Dict[str, str], params: Optional[Dict] = None) -> Optional[Any]:
    if _is_in_cooldown():
        return None
    token = _get_access_token(cfg)
    if not token:
        return None
    try:
        resp = requests.get(
            f'{ADMob_API}{path}',
            params=params or {},
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )
        if resp.status_code in (401, 403):
            _mark_fatal(f'API HTTP {resp.status_code} on GET {path}')
            return None
        if resp.status_code == 400:
            _mark_short_cooldown(300, f'API HTTP 400 on GET {path}: {resp.text[:150]}')
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception('[AdMob] API call failed: %s', path)
        return None


def _api_post(path: str, cfg: Dict[str, str], body: Dict) -> Optional[Any]:
    """AdMob report generate (POST + async polling)."""
    if _is_in_cooldown():
        return None
    token = _get_access_token(cfg)
    if not token:
        return None
    try:
        resp = requests.post(
            f'{ADMob_API}{path}',
            json=body,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code in (401, 403):
            _mark_fatal(f'API HTTP {resp.status_code} on POST {path}')
            return None
        if resp.status_code == 400:
            _mark_short_cooldown(300, f'API HTTP 400 on POST {path}: {resp.text[:150]}')
            return None
        logger.warning('[AdMob] generate HTTP %s: %s', resp.status_code, resp.text[:300])
        return None
    except Exception:
        logger.exception('[AdMob] generate call failed: %s', path)
        return None


def _generate_and_poll(path: str, body: Dict, cfg: Dict[str, str], max_wait: int = 30) -> Optional[Any]:
    """AdMob v1: generateReport async → poll sonucu al.

    AdMob bazı durumlarda senkron olarak doğrudan rows listesi döndürür.
    Bu durumda initial bir list olur; list/dict ayrımını güvenli yap.
    """
    initial = _api_post(path, cfg, body)
    if not initial:
        return None
    if isinstance(initial, list):
        return initial
    if isinstance(initial, dict):
        if initial.get('rows') is not None:
            return initial
        report_name = initial.get('report') or initial.get('name')
        if not report_name:
            return initial
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(2)
            data = _api_get(f'/{report_name}', cfg)
            if not data:
                continue
            state = data.get('state') or data.get('reportState') or 'DONE'
            if state in ('DONE', 'READY', 'COMPLETED', 'SUCCESS', ''):
                return data
            if state in ('FAILED', 'ERROR'):
                logger.error('[AdMob] report failed: %s', data)
                return None
        logger.warning('[AdMob] report poll timeout')
        return None
    logger.warning('[AdMob] generate returned unexpected type: %s', type(initial).__name__)
    return None


def get_overview(date_range: str = '30d') -> Optional[Dict[str, Any]]:
    """Reklam performans özeti: revenue, impressions, eCPM.

    AdMob API v1: networkReport:generate (POST) → async GET aynı name ile.
    Dönen rows: [{ "row": { "dimensionValues": {...}, "metricValues": {...} } }, ...]
    """
    cfg = _get_config()
    if not cfg:
        return None
    if _is_in_cooldown():
        return {
            'range': date_range,
            'revenue_usd': 0.0,
            'impressions': 0,
            'ecpm_usd': 0.0,
            'rows': [],
            'cooldown': True,
        }
    cache_key = f'overview:{date_range}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    import datetime
    days = {'7d': 7, '30d': 30, '90d': 90}.get(date_range, 30)
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)

    parent = cfg['publisher_id'] if cfg['publisher_id'].startswith('pub-') else f'pub-{_strip_pub(cfg["publisher_id"])}'
    spec = {
        'reportSpec': {
            'dateRange': {
                'startDate': {'year': start.year, 'month': start.month, 'day': start.day},
                'endDate': {'year': end.year, 'month': end.month, 'day': end.day},
            },
            'metrics': ['ESTIMATED_EARNINGS', 'IMPRESSIONS', 'IMPRESSION_CTR', 'IMPRESSION_RPM'],
            'dimensions': ['DATE'],
            'localizationSettings': {'currencyCode': 'USD', 'languageCode': 'en-US'},
        }
    }

    data = _generate_and_poll(
        f'/accounts/{parent}/networkReport:generate',
        spec, cfg, max_wait=45,
    )
    rows = []
    if data and isinstance(data, list):
        rows = data
    elif data and isinstance(data, dict):
        rows = data.get('rows', [])

    # Aggregate totals + daily series
    total_revenue = 0.0
    total_impressions = 0
    daily = []
    for r in rows:
        row = r.get('row', r) if isinstance(r, dict) else {}
        mv = row.get('metricValues', {}) or {}
        def _num(d, key):
            cell = d.get(key, {}) or {}
            if 'microsValue' in cell:
                try:
                    return float(cell['microsValue']) / 1e6
                except Exception:
                    return 0.0
            if 'doubleValue' in cell:
                try:
                    return float(cell['doubleValue'])
                except Exception:
                    return 0.0
            if 'intValue' in cell:
                try:
                    return int(cell['intValue'])
                except Exception:
                    return 0
            return 0
        rev = _num(mv, 'ESTIMATED_EARNINGS')
        imp = _num(mv, 'IMPRESSIONS')
        total_revenue += rev
        total_impressions += int(imp)
        dv = row.get('dimensionValues', {}) or {}
        date_cell = dv.get('DATE', {}) or {}
        d_str = date_cell.get('value', '') or ''
        daily.append({'date': _fmt_date(d_str), 'date_raw': d_str,
                      'revenue_usd': rev, 'impressions': int(imp)})

    ecpm = (total_revenue / total_impressions * 1000.0) if total_impressions else 0.0

    result = {
        'range': date_range,
        'revenue_usd': round(total_revenue, 4),
        'impressions': int(total_impressions),
        'ecpm_usd': round(ecpm, 4),
        'rows': daily,
    }
    _cache_set(cache_key, result)
    return result


def _strip_pub(p: str) -> str:
    """'pub-2444093901783574' → '2444093901783574' (AdMob account id)."""
    return p.replace('pub-', '') if p else ''


def _extract_app_id(a: Dict[str, Any]) -> str:
    """AdMob v1 API: appId direkt string ('ca-app-pub-...') veya
    nested object {'appId': {'value': '...'}} olabilir.
    Farklı field adları da desteklenir: appCode, applicationCode, app_id, id.
    Ayrıca nested objede farklı key'ler: 'id', 'appId', 'value' kontrol edilir.
    """
    if not isinstance(a, dict):
        return ''
    for key in ('appId', 'appCode', 'applicationCode', 'app_id', 'id'):
        app_id = a.get(key, '')
        if not app_id:
            continue
        if isinstance(app_id, dict):
            # Nested object — birkaç olası field ismi
            for nested_key in ('value', 'id', 'appId', 'app_id'):
                v = app_id.get(nested_key, '')
                if v:
                    return str(v)
        else:
            s = str(app_id).strip()
            if s:
                return s
    return ''


def get_apps(date_range: str = '30d') -> Optional[List[Dict[str, Any]]]:
    """AdMob hesabına bağlı uygulamalar."""
    if _is_in_cooldown():
        return None
    cfg = _get_config()
    if not cfg:
        return None
    cache_key = f'apps:{date_range}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    parent = cfg['publisher_id'] if cfg['publisher_id'].startswith('pub-') else f'pub-{_strip_pub(cfg["publisher_id"])}'
    apps_data = _api_get(f'/accounts/{parent}/apps', cfg)
    # Debug: response shape — bir sonraki deploy'da çıkarılabilir
    if apps_data is not None:
        try:
            sample = apps_data if isinstance(apps_data, list) else (
                list(apps_data.keys()) if isinstance(apps_data, dict) else type(apps_data).__name__
            )
            sample_count = len(apps_data) if hasattr(apps_data, '__len__') else 0
            logger.info(f'[AdMob] /apps response: type={type(apps_data).__name__}, len={sample_count}, sample={str(sample)[:500]}')
            if isinstance(apps_data, dict) and apps_data.get('apps'):
                first = apps_data['apps'][0] if isinstance(apps_data['apps'], list) and apps_data['apps'] else None
                if first is not None:
                    logger.info(f'[AdMob] first app keys: {list(first.keys()) if isinstance(first, dict) else type(first).__name__}')
            elif isinstance(apps_data, list) and apps_data:
                first = apps_data[0]
                logger.info(f'[AdMob] first app keys: {list(first.keys()) if isinstance(first, dict) else type(first).__name__}')
        except Exception:
            pass
    if not apps_data:
        return None
    # Birçok format: dict {apps: [...]}, dict {app: [...]}, direkt list [...]
    apps_list = []
    if isinstance(apps_data, list):
        apps_list = apps_data
    elif isinstance(apps_data, dict):
        for key in ('apps', 'app', 'items', 'results'):
            if isinstance(apps_data.get(key), list):
                apps_list = apps_data[key]
                break
        if not apps_list:
            apps_list = [apps_data]
    def _is_valid_app(a: Dict[str, Any]) -> bool:
        if not isinstance(a, dict):
            return False
        app_id = _extract_app_id(a)
        if not app_id or not app_id.startswith('ca-app-pub-'):
            return False
        # appId geçerliyse app valid — name filtresi gevşetildi (AdMob bazen
        # path-benzeri name döndürüyor olabilir; önemli olan appId).
        return True
    result = [
        {
            'appId': _extract_app_id(a),
            'name': (a.get('name', '') if isinstance(a, dict) else '') or '',
            'platform': (a.get('platform', '') if isinstance(a, dict) else '') or '',
        }
        for a in apps_list
        if _is_valid_app(a)
    ]
    logger.info(f'[AdMob] get_apps result count={len(result)}, raw apps_list count={len(apps_list)}')
    if result:
        logger.info(f'[AdMob] first app: {result[0]}')
    _cache_set(cache_key, result)
    return result
