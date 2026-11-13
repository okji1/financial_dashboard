"""systemd preflight: report missing variable names, never secret values."""
import os
from urllib.parse import urlsplit

REQUIRED = ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'KIS_APP_KEY',
            'KIS_APP_SECRET', 'EXCHANGE_RATE_API_KEY', 'KRX_API_KEY')


def validate(values):
    missing = [key for key in REQUIRED if not values.get(key, '').strip()]
    if missing:
        raise ValueError('Missing environment variables: '+', '.join(missing))
    parsed = urlsplit(values['SUPABASE_URL'])
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('SUPABASE_URL must be an HTTPS project URL')


if __name__ == '__main__':
    try:
        validate(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
