"""Read-only Render/Supabase inventory. Never prints credentials or token rows.

Use backend/venv/bin/python ops/preflight_production.py --backend-url <Render URL>
Credentials come ONLY from RENDER_API_KEY and SUPABASE_ACCESS_TOKEN; project
identity comes from SUPABASE_URL. This command performs no deployments or SQL DDL.
"""
import argparse
import base64
import json
import os
from urllib.parse import urlsplit

import requests

TABLES = ('kis_token', 'gold_prices', 'active_contracts', 'investment_strategies')
AUDIT_SQL = """
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS force_rls,
       (SELECT json_agg(json_build_object('role', CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE r.rolname END, 'privilege', a.privilege_type))
        FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        LEFT JOIN pg_roles r ON r.oid=a.grantee
        WHERE a.grantee=0 OR r.rolname IN ('anon','authenticated','service_role')) AS grants,
       (SELECT json_agg(json_build_object('name', p.policyname, 'roles', p.roles,
          'command', p.cmd, 'permissive', p.permissive,
          'unconditional_using', coalesce(p.qual='true', false),
          'unconditional_check', coalesce(p.with_check='true', false)))
        FROM pg_policies p WHERE p.schemaname='public' AND p.tablename=c.relname) AS policies
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND c.relname IN ('kis_token','gold_prices','active_contracts','investment_strategies')
ORDER BY c.relname;
"""


class ManagementError(RuntimeError):
    pass


def require_variable(name):
    value = os.environ.get(name)
    if not value:
        raise ManagementError(f'Missing required environment binding: {name}')
    return value


def api_call(session, method, url, token, **kwargs):
    try:
        response = session.request(method, url, headers={'Authorization': 'Bearer '+token},
                                   timeout=(3, 20), **kwargs)
        if not response.ok:
            raise ManagementError(f'{urlsplit(url).hostname}: HTTP {response.status_code}')
        return response.json()
    except (requests.RequestException, ValueError) as error:
        # Management responses may contain entire key inventories: never echo them.
        raise ManagementError(f'{urlsplit(url).hostname}: {type(error).__name__}') from None


def jwt_role(key):
    """Metadata only; an unverified JWT claim does not establish actual access."""
    try:
        encoded = key.split('.')[1]
        role = json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))).get('role')
        return role if role in ('anon', 'authenticated', 'service_role') else 'unconfirmed'
    except (IndexError, ValueError, TypeError):
        return 'unconfirmed'


def project_ref(url):
    host = urlsplit(url).hostname or ''
    if not host.endswith('.supabase.co') or host.count('.') != 2:
        raise ManagementError('SUPABASE_URL must identify the intended hosted Supabase project')
    return host.split('.')[0]


def find_service(session, token, backend_url):
    target = backend_url.rstrip('/')
    if urlsplit(target).scheme != 'https':
        raise ManagementError('Backend URL must use HTTPS')
    matches, cursor, seen = [], None, set()
    for _ in range(100):
        params = {'limit': 100}
        if cursor: params['cursor'] = cursor
        page = api_call(session, 'GET', 'https://api.render.com/v1/services', token, params=params)
        if not isinstance(page, list): raise ManagementError('Unexpected Render service list')
        for entry in page:
            service = entry.get('service', {})
            if service.get('serviceDetails', {}).get('url', '').rstrip('/') == target:
                matches.append(service)
        if len(page) < 100: break
        cursor = page[-1].get('cursor')
        if not cursor or cursor in seen: raise ManagementError('Incomplete Render pagination')
        seen.add(cursor)
    else:
        raise ManagementError('Render pagination limit exceeded')
    if len(matches) != 1:
        raise ManagementError('Backend URL must resolve to exactly one accessible Render service')
    return matches[0]


def preflight(session, backend_url):
    render_token = require_variable('RENDER_API_KEY')
    supabase_token = require_variable('SUPABASE_ACCESS_TOKEN')
    ref = project_ref(require_variable('SUPABASE_URL'))
    service = find_service(session, render_token, backend_url)
    env_rows, cursor, seen = [], None, set()
    for _ in range(100):
        params = {'limit': 100}
        if cursor: params['cursor'] = cursor
        page = api_call(session, 'GET', f"https://api.render.com/v1/services/{service['id']}/env-vars", render_token, params=params)
        if not isinstance(page, list): raise ManagementError('Unexpected Render environment list')
        env_rows.extend(page)
        if len(page) < 100: break
        cursor = page[-1].get('cursor')
        if not cursor or cursor in seen: raise ManagementError('Incomplete environment pagination')
        seen.add(cursor)
    else:
        raise ManagementError('Environment pagination limit exceeded')
    values = {item['envVar']['key']: item['envVar']['value'] for item in env_rows}
    # Fail if the target backend actually points at another project.
    if project_ref(values.get('SUPABASE_URL', '')) != ref:
        raise ManagementError('Render backend uses a different Supabase project; refusing to proceed')
    rows = api_call(session, 'POST', f'https://api.supabase.com/v1/projects/{ref}/database/query/read-only',
                    supabase_token, json={'query': AUDIT_SQL})
    if not isinstance(rows, list) or {row.get('table_name') for row in rows} != set(TABLES):
        raise ManagementError('Expected all four application tables; no migration is safe yet')
    # No environment values or token rows are included in the returned report.
    return {'service_id': service['id'], 'service_name': service['name'],
            'project_ref': ref, 'branch': service.get('branch'),
            'environment_binding_names': sorted(values),
            'backend_service_key_configured': bool(values.get('SUPABASE_SERVICE_ROLE_KEY')),
            'effective_key_role_claim': jwt_role(values.get('SUPABASE_SERVICE_ROLE_KEY') or values.get('SUPABASE_KEY', '')),
            'tables': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-url', required=True)
    args = parser.parse_args()
    try:
        with requests.Session() as session:
            print(json.dumps(preflight(session, args.backend_url), ensure_ascii=False, indent=2))
    except ManagementError as error:
        parser.exit(1, str(error)+'\n')
