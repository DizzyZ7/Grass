"""Telegram Mini App HMAC validation and fail-closed local-only demo auth."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InvalidTelegramData(ValueError):
    pass


def verify_init_data(raw: str, token: str, *, now: int | None = None, ttl: int = 86400) -> dict:
    if not token or not raw or len(raw) > 8192:
        raise InvalidTelegramData('Missing credentials')
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=30)
        data = dict(pairs)
        if len(data) != len(pairs) or 'hash' not in data or len(data['hash']) != 64:
            raise InvalidTelegramData('Malformed Telegram data')
        # Telegram's bot-token HMAC excludes hash, but unlike third-party
        # Ed25519 verification includes all other fields in the check string.
        check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()) if k != 'hash')
        secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, data['hash']):
            raise InvalidTelegramData('Invalid Telegram signature')
        auth_date = int(data['auth_date'])
        current = now if now is not None else int(time.time())
        if auth_date > current + 60 or current - auth_date > ttl:
            raise InvalidTelegramData('Telegram authorization expired')
        user = json.loads(data['user'])
        user_id = user.get('id')
        if type(user_id) is not int or user_id <= 0 or user_id >= 2**53:
            raise InvalidTelegramData('Invalid Telegram user')
        name = user.get('first_name', '')
        if not isinstance(name, str):
            raise InvalidTelegramData('Invalid name')
        return {'id': user_id, 'first_name': name[:120] or 'Игрок',
                'username': (user.get('username') or '')[:64] if isinstance(user.get('username'), (str, type(None))) else None}
    except (TypeError, ValueError, KeyError, UnicodeError) as exc:
        raise InvalidTelegramData('Invalid or expired Telegram data') from exc
