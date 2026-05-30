import pytest

from scripts.utils.providers.deepseek_provider import get_proxy_url


def test_get_proxy_url_uses_first_valid_proxy():
    env = {
        'HTTPS_PROXY': 'http://127.0.0.1:7897',
        'HTTP_PROXY': 'http://127.0.0.1:8888',
        'NO_PROXY': 'localhost,127.0.0.1,::1',
    }

    assert get_proxy_url(env) == 'http://127.0.0.1:7897'


def test_get_proxy_url_ignores_no_proxy_without_parsing_it():
    env = {
        'NO_PROXY': 'localhost,127.0.0.1,::1',
        'no_proxy': 'localhost,127.0.0.1,::1',
    }

    assert get_proxy_url(env) is None


def test_get_proxy_url_rejects_invalid_proxy_url():
    with pytest.raises(ValueError, match='HTTPS_PROXY'):
        get_proxy_url({'HTTPS_PROXY': '127.0.0.1:7897'})
