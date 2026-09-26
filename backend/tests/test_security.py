import hashlib
import hmac
import json
from urllib.parse import urlencode
import pytest
from backend.app.security import InvalidTelegramData, verify_init_data

BOT_TOKEN = '12345:test-token-for-unit-tests'
NOW = 1_780_000_000


def signed(user: dict, auth_date: int = NOW, extra: dict | None = None):
    data = {'user': json.dumps(user, separators=(',', ':'), ensure_ascii=False),
            'auth_date': str(auth_date), 'query_id': 'AA123'}
    if extra: data.update(extra)
    check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
    data['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def test_valid_unicode_initdata():
    result = verify_init_data(signed({'id': 123456789, 'first_name': 'Димаш', 'username': 'DizzyZ7'}),
                              BOT_TOKEN, now=NOW)
    assert result['id'] == 123456789
    assert result['first_name'] == 'Димаш'


def test_tamper_rejected():
    raw = signed({'id': 2, 'first_name': 'x'})
    with pytest.raises(InvalidTelegramData):
        verify_init_data(raw.replace('id%22%3A2', 'id%22%3A3'), BOT_TOKEN, now=NOW)


def test_old_data_rejected():
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed({'id': 2}, NOW - 86401), BOT_TOKEN, now=NOW)


def test_future_data_rejected():
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed({'id': 2}, NOW + 61), BOT_TOKEN, now=NOW)


def test_duplicate_keys_rejected():
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed({'id': 2}) + '&user=bad', BOT_TOKEN, now=NOW)

@pytest.mark.parametrize('bad_id', [0, -3, '123', True, 2**55])
def test_invalid_id_rejected(bad_id):
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed({'id': bad_id}), BOT_TOKEN, now=NOW)


def test_hash_with_other_signed_fields():
    raw = signed({'id': 3, 'first_name': 'A'}, extra={'chat_type': 'sender'})
    assert verify_init_data(raw, BOT_TOKEN, now=NOW)['id'] == 3
