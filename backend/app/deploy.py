"""Hosted API/worker entry points and non-destructive synthetic provisioning."""

import argparse
import os
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import psycopg
from fastapi.responses import JSONResponse

from app.api.auth import configured_verifier, cors_origins
from app.persistence.seed import DEMO_STUDY_ID, seed_demo
from app.persistence.storage import SupabasePrivateStorage, configured_storage


def validate_hosted_config():
    required = ('DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY',
                'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_STORAGE_BUCKET', 'CORS_ORIGINS')
    missing = [name for name in required if not os.environ.get(name, '').strip()]
    if missing:
        raise ValueError('Missing hosted configuration: ' + ', '.join(missing))
    if os.environ.get('TRIALSYNC_AUTH_MODE', 'required') != 'required':
        raise ValueError('Hosted API requires authentication')
    origins = cors_origins()
    if not origins or any(urlsplit(origin).scheme != 'https' for origin in origins):
        raise ValueError('Hosted CORS requires exact HTTPS frontend origins')
    database = urlsplit(os.environ['DATABASE_URL'])
    if database.scheme not in ('postgres', 'postgresql') or not database.hostname:
        raise ValueError('Hosted database requires a PostgreSQL connection URL')
    if parse_qs(database.query).get('sslmode', [''])[0] not in ('require', 'verify-ca', 'verify-full'):
        raise ValueError('Hosted database requires an explicit TLS sslmode')
    configured_verifier()
    storage = configured_storage()
    if not isinstance(storage, SupabasePrivateStorage):
        raise ValueError('Hosted processes require shared private Supabase storage')
    return storage


def database_ready():
    # Connection + bounded read verifies both baseline and worker migrations.
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=2,
                         prepare_threshold=None) as connection:
        connection.execute("SET LOCAL statement_timeout = '1000ms'")
        connection.execute('SELECT study_id, user_id FROM public.memberships LIMIT 0')
        connection.execute('SELECT claimed_by, lease_expires_at, attempts FROM public.jobs LIMIT 0')
        connection.execute('SELECT candidate_version_id FROM public.changes LIMIT 0')


def hosted_app():
    validate_hosted_config()
    from app.main import create_app
    application = create_app()

    @application.get('/ready', include_in_schema=False)
    def ready():
        try:
            database_ready()
        except psycopg.Error:
            return JSONResponse({'status': 'unavailable'}, status_code=503)
        return {'status': 'ready'}

    return application


def seed_member(database_url, user_id):
    user_id = UUID(str(user_id))  # Validate before any writes.
    study_id = seed_demo(database_url)
    with psycopg.connect(database_url, connect_timeout=5, prepare_threshold=None) as connection:
        connection.execute("INSERT INTO public.memberships (study_id, user_id, role) VALUES (%s, %s, 'owner') "
                           'ON CONFLICT DO NOTHING', (DEMO_STUDY_ID, user_id))
    return study_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['api', 'worker', 'seed'])
    args = parser.parse_args()
    try:
        storage = validate_hosted_config()
        if args.command == 'seed':
            user_id = os.environ.get('TRIALSYNC_DEMO_USER_ID')
            if not user_id:
                raise ValueError('TRIALSYNC_DEMO_USER_ID must be a real Supabase Auth user UUID')
            seed_member(os.environ['DATABASE_URL'], user_id)
            print(f'Synthetic study provisioned: {DEMO_STUDY_ID}')
            return
        database_ready()
        storage._private_bucket()  # Refuse public/missing buckets before serving or claiming.
    except Exception:
        # Connection/storage errors may contain secrets; startup output is deliberately bounded.
        raise SystemExit('Hosted startup failed; check private configuration, migrations, and bucket privacy') from None
    if args.command == 'api':
        import uvicorn
        uvicorn.run('app.deploy:hosted_app', factory=True, host='0.0.0.0',
                    port=int(os.environ.get('PORT', '10000')))
    else:
        from app.worker import main as worker_main
        import sys
        adapter = os.environ.get('TRIALSYNC_WORKER_ADAPTER')
        if not adapter:
            raise SystemExit('TRIALSYNC_WORKER_ADAPTER is required; use demo only for the synthetic study')
        sys.argv = ['trialsync-worker', '--adapter', adapter]
        worker_main()


if __name__ == '__main__':
    main()
