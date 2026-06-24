"""
ORBIS Google Analytics 4 — Data API wrapper.
Server-side metric çekme (admin dashboard için).
Fail-closed: credential yoksa / API hata verirse None.

API sürümü: google.analytics.data_v1beta (BetaAnalyticsDataClient)
Referans: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport

Metric/Dimension isimleri GA4 Data API v1beta ile uyumlu:
  activeUsers, sessions, screenPageViews, conversions, averageSessionDuration
  pageTitle, pagePath, sessionSourceMedium, date

Property ID format: 'properties/{numeric_id}' (env'de 'properties/' öneki varsa tekrarlanmaz).
"""
import os
import json
import logging
import time
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Cache (Redis varsa kullan, yoksa in-process dict)
_cache: Dict[str, tuple] = {}
CACHE_TTL = 3600  # 1 saat

# Terminal hata sonrası cooldown
_FATAL_COOLDOWN = 12 * 3600
_SHORT_COOLDOWN = 300
_fatal_until: float = 0.0
_fatal_reason: str = ''

# GA4 'date' dimension değeri "YYYYMMDD" → "23 Haz" gibi kısa Türkçe etiket
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


def _is_in_cooldown() -> bool:
    global _fatal_until
    return _fatal_until and time.time() < _fatal_until


def _mark_short_cooldown(seconds: int, reason: str):
    global _fatal_until, _fatal_reason
    _fatal_until = time.time() + seconds
    _fatal_reason = reason
    logger.warning('[GA4] entering %ss cooldown: %s', seconds, reason)


def _mark_fatal(reason: str):
    global _fatal_until, _fatal_reason
    _fatal_until = time.time() + _FATAL_COOLDOWN
    _fatal_reason = reason
    logger.warning('[GA4] entering %sh cooldown: %s', int(_FATAL_COOLDOWN/3600), reason)


def _normalize_property(prop_id: str) -> str:
    if not prop_id:
        return ''
    return prop_id if prop_id.startswith('properties/') else f'properties/{prop_id}'


def _get_property_id() -> Optional[str]:
    return os.environ.get('GA4_PROPERTY_ID')


def _get_service_account_path() -> Optional[str]:
    """Service account credentials: dosya veya env JSON. Öncelik: env JSON > dosya."""
    import tempfile
    json_env = os.environ.get('GA4_SERVICE_ACCOUNT_JSON')
    if json_env:
        try:
            fd, path = tempfile.mkstemp(suffix='.json', prefix='ga4-sa-')
            os.write(fd, json_env.encode('utf-8') if isinstance(json_env, str) else json_env)
            os.close(fd)
            return path
        except Exception:
            pass
    path = os.environ.get('GA4_SERVICE_ACCOUNT_PATH')
    if path and os.path.exists(path):
        return path
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


def _get_client():
    sa_path = _get_service_account_path()
    if not sa_path:
        return None
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=['https://www.googleapis.com/auth/analytics.readonly']
        )
        return BetaAnalyticsDataClient(credentials=creds)
    except Exception:
        logger.exception('[GA4] client init failed')
        return None


def _run_report(date_range: str = '7d', *,
               dimensions: List[str], metrics: List[str],
               order_by: Optional[Any] = None,
               limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if _is_in_cooldown():
        return None
    prop_id = _get_property_id()
    if not prop_id:
        return None
    property_path = _normalize_property(prop_id)

    cache_key = f'report:{date_range}:{",".join(dimensions)}:{",".join(metrics)}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return None

    days = {'1d': 1, '7d': 7, '30d': 30, '90d': 90}.get(date_range, 7)

    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension, OrderBy as OB
        )
        kwargs = {
            'property': property_path,
            'dimensions': [Dimension(name=d) for d in dimensions],
            'metrics': [Metric(name=m) for m in metrics],
            'date_ranges': [DateRange(start_date=f'{days}daysAgo', end_date='today')],
        }
        if order_by is not None:
            kwargs['order_bys'] = [order_by]
        if limit is not None:
            kwargs['limit'] = limit
        req = RunReportRequest(**kwargs)
        resp = client.run_report(req)
        rows = []
        for r in (resp.rows or []):
            rows.append({
                'dimension_values': [dv.value for dv in (r.dimension_values or [])],
                'metric_values': [mv.value for mv in (r.metric_values or [])],
            })
        result = {'range': date_range, 'rows': rows}
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        msg = str(e)
        if '401' in msg or '403' in msg or 'PERMISSION_DENIED' in msg:
            _mark_fatal(f'GA4 {msg[:200]}')
        elif '400' in msg or 'INVALID_ARGUMENT' in msg or 'NOT_FOUND' in msg:
            _mark_short_cooldown(300, f'GA4 {msg[:200]}')
        else:
            logger.exception('[GA4] run_report failed')
        return None


def _parse_num(s, default=0):
    try:
        if s is None:
            return default
        if '.' in str(s):
            return float(s)
        return int(s)
    except (ValueError, TypeError):
        try:
            return float(s)
        except Exception:
            return default


def get_overview(date_range: str = '7d') -> Optional[Dict[str, Any]]:
    data = _run_report(
        date_range,
        dimensions=['date'],
        metrics=['activeUsers', 'sessions', 'screenPageViews', 'conversions', 'averageSessionDuration'],
    )
    if not data or not data.get('rows'):
        return None
    rows_raw = data['rows']
    rows = [
        {
            'date': r['dimension_values'][0],
            'users': _parse_num(r['metric_values'][0]),
            'sessions': _parse_num(r['metric_values'][1]),
            'pageViews': _parse_num(r['metric_values'][2]),
            'conversions': _parse_num(r['metric_values'][3]),
            'avgDuration': _parse_num(r['metric_values'][4], default=0.0),
        }
        for r in rows_raw
        if len(r['dimension_values']) >= 1 and len(r['metric_values']) >= 4
    ]
    if not rows:
        return None
    total_users = sum(r['users'] for r in rows)
    total_sessions = sum(r['sessions'] for r in rows)
    total_pageviews = sum(r['pageViews'] for r in rows)
    total_conversions = sum(r['conversions'] for r in rows)
    if total_sessions > 0:
        avg_sec = sum(float(r.get('avgDuration') or 0) * r['sessions'] for r in rows) / total_sessions
        avg_str = f'{int(avg_sec // 60)}m {int(avg_sec % 60)}s'
    else:
        avg_str = '—'
    return {
        'range': date_range,
        'totalUsers': total_users,
        'totalSessions': total_sessions,
        'totalPageViews': total_pageviews,
        'totalConversions': total_conversions,
        'avgSessionDuration': avg_str,
        'usersSeries': [{'label': _fmt_date(r['date']), 'value': r['users']} for r in rows],
        'sessionsSeries': [{'label': _fmt_date(r['date']), 'value': r['sessions']} for r in rows],
    }


def get_top_pages(date_range: str = '7d', limit: int = 10) -> Optional[List[Dict[str, Any]]]:
    if _is_in_cooldown():
        return None
    from google.analytics.data_v1beta.types import OrderBy as OB
    data = _run_report(
        date_range,
        dimensions=['pageTitle', 'pagePath'],
        metrics=['screenPageViews'],
        order_by=OB(metric=OB.MetricOrderBy(metric_name='screenPageViews'), desc=True),
        limit=limit,
    )
    if not data or not data.get('rows'):
        return None
    return [
        {
            'title': r['dimension_values'][0] if len(r['dimension_values']) >= 1 else '',
            'path': r['dimension_values'][1] if len(r['dimension_values']) >= 2 else '',
            'views': _parse_num(r['metric_values'][0]) if r['metric_values'] else 0,
        }
        for r in data['rows']
    ]


def get_traffic_sources(date_range: str = '7d') -> Optional[List[Dict[str, Any]]]:
    if _is_in_cooldown():
        return None
    from google.analytics.data_v1beta.types import OrderBy as OB
    data = _run_report(
        date_range,
        dimensions=['sessionSourceMedium'],
        metrics=['sessions'],
        order_by=OB(metric=OB.MetricOrderBy(metric_name='sessions'), desc=True),
        limit=10,
    )
    if not data or not data.get('rows'):
        return None
    return [
        {
            'source': r['dimension_values'][0] if r['dimension_values'] else '',
            'sessions': _parse_num(r['metric_values'][0]) if r['metric_values'] else 0,
        }
        for r in data['rows']
    ]
