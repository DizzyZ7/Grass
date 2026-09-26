"""Prove HMAC verification rejects attacker-controlled identities and replays."""
import hashlib
import hmac
import json
from urllib.parse import urlencode
import pytest
from backend.app.security import verify_init_data, InvalidTelegramData

TOKEN = '123456:dev-fixture'


def signed(user=None, now=1_800_000_000, **params):
    data = {'auth_date': str(now), 'user': json.dumps(user or {'id': 42, 'first_name': 'DizZy'})}
    data.update(params)
    secret = hmac.new(b'WebAppData', TOKEN.encode(), hashlib.sha256).digest()
    check = '\n'.join(f'{key}={val}' for key, val in sorted(data.items()))
    data['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def test_signature_and_identity():
    identity = verify_init_data(signed(), TOKEN, now=1_800_000_020)
    assert identity['id'] == 42
    assert identity['first_name'] == 'DizZy'


@pytest.mark.parametrize('bad', [
    lambda payload: payload.replace('DizZy', 'Admin'),
    lambda payload: payload + '&hash=' + '0' * 64,
    lambda payload: payload.replace('id%22%3A+42', 'id%22%3A+43'),
])
def test_reject_tampering(bad):
    with pytest.raises(InvalidTelegramData):
        verify_init_data(bad(signed()), TOKEN, now=1_800_000_020)


def test_expiry_and_future():
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed(now=1_800_000_000), TOKEN, now=1_800_100_000)
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed(now=1_800_000_120), TOKEN, now=1_800_000_000)


def test_invalid_identity():
    with pytest.raises(InvalidTelegramData):
        verify_init_data(signed(user={'id': -1}), TOKEN, now=1_800_000_000)


def test_signature_field_is_included():
    assert verify_init_data(signed(signature='third_party_signature'), TOKEN, now=1_800_000_000)['id'] == 42
