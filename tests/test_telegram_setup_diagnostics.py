import httpx
import pytest

from backend.telegram import TelegramWorker
from tools.telegram_setup import inspect_bot, main, validate_token


@pytest.mark.parametrize('token', ['123456789', 'bot123:ABC_def', '`123:ABC_def`', '"123:ABC_def"', '123:ABC def', '123:ABC_def\\', '123:ABC_def\n'])
def test_bad_token_shape_is_rejected_without_echo(token):
    with pytest.raises(ValueError) as error:
        validate_token(token)
    assert token not in str(error.value)


def test_token_format_accepts_full_token():
    validate_token('123456789:ABcdef_0123-xyz')


@pytest.mark.parametrize('status', [401, 404, 409, 429, 500])
def test_http_failure_is_specific_and_redacted(cfg, status, caplog):
    cfg.telegram_token = '123456789:private_token_never_echo'
    worker = TelegramWorker(None, cfg, httpx.MockTransport(lambda request: httpx.Response(
        status, json={'ok': False, 'description': 'Do not echo ' + cfg.telegram_token})))
    try:
        with pytest.raises(ValueError) as error:
            inspect_bot(worker)
        assert f'HTTP {status}' in str(error.value)
        assert cfg.telegram_token not in str(error.value) + caplog.text
        assert worker.last_http_status == status
    finally:
        worker.close()


@pytest.mark.parametrize('failure,expected', [('timeout', 'quá thời gian'), ('connection', 'Không kết nối'), ('html', 'không đúng định dạng')])
def test_transport_failure_does_not_echo_exception_or_url(cfg, failure, expected):
    cfg.telegram_token = '123456789:private_token_never_echo'
    def transport(request):
        if failure == 'timeout': raise httpx.ReadTimeout(str(request.url))
        if failure == 'connection': raise httpx.ConnectError(str(request.url))
        return httpx.Response(200, text='<html>' + cfg.telegram_token + '</html>')
    worker = TelegramWorker(None, cfg, httpx.MockTransport(transport))
    try:
        with pytest.raises(ValueError) as error: inspect_bot(worker)
        assert expected in str(error.value)
        assert cfg.telegram_token not in str(error.value)
    finally:
        worker.close()


def test_request_clears_previous_error_on_success(cfg):
    calls = []
    def transport(request):
        calls.append(1)
        return httpx.Response(401, json={'ok': False}) if len(calls) == 1 else httpx.Response(200, json={'ok': True})
    worker = TelegramWorker(None, cfg, httpx.MockTransport(transport))
    try:
        assert not worker.request('getMe', {})[0] and worker.last_http_status == 401
        assert worker.request('getMe', {})[0] and worker.last_error is None
    finally:
        worker.close()


def test_cli_rejects_numeric_only_token_before_network(monkeypatch, capsys):
    monkeypatch.setenv('TELEGRAM_TOKEN', '123456789')
    def forbidden(*args, **kwargs): raise AssertionError('Must not contact Telegram')
    monkeypatch.setattr('tools.telegram_setup.TelegramWorker', forbidden)
    assert main() == 1
    output = capsys.readouterr().out
    assert '123456789' not in output and 'NGUYÊN' in output
