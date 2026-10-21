from types import SimpleNamespace

import pytest
from lookout.config import Settings
from lookout.secrets import InfisicalSecretProvider, SecretProviderError


class FakeInfisicalClient:
    def __init__(self, *, host, secret_value="fictional-smtp-password", error=None):
        self.host = host
        self.secret_value = secret_value
        self.error = error
        self.login_calls = []
        self.secret_calls = []
        self.closed = False
        self.auth = SimpleNamespace(universal_auth=SimpleNamespace(login=self._login))
        self.secrets = SimpleNamespace(get_secret_by_name=self._get_secret_by_name)

    def _login(self, **kwargs):
        self.login_calls.append(kwargs)

    def _get_secret_by_name(self, *args, **kwargs):
        self.secret_calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(secretValue=self.secret_value)

    def close(self):
        self.closed = True


def make_settings(**overrides) -> Settings:
    values = {
        "infisical_url": "http://infisical:8080",
        "infisical_client_id": "fictional-client-id",
        "infisical_client_secret": "fictional-client-secret",
        "infisical_project_id": "fictional-project-id",
        "infisical_environment": "dev",
        "infisical_secret_path": "/application",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_secret_provider_authenticates_and_fetches_secret_from_requested_path():
    clients = []

    def client_factory(*, host):
        client = FakeInfisicalClient(host=host)
        clients.append(client)
        return client

    provider = InfisicalSecretProvider(make_settings(), client_factory=client_factory)

    secret = provider.get_secret("SMTP_PASSWORD", path="/application")

    assert secret == "fictional-smtp-password"
    assert clients[0].host == "http://infisical:8080"
    assert clients[0].login_calls == [
        {"client_id": "fictional-client-id", "client_secret": "fictional-client-secret"}
    ]
    assert clients[0].secret_calls == [
        (
            ("SMTP_PASSWORD", "dev", "/application"),
            {"project_id": "fictional-project-id"},
        )
    ]
    assert clients[0].closed


def test_secret_provider_sanitizes_sdk_errors_without_exposing_secret_values():
    secret_value = "fictional-secret-value-must-not-appear"
    client = FakeInfisicalClient(
        host="http://infisical:8080",
        error=RuntimeError(f"request failed while handling {secret_value}"),
    )
    provider = InfisicalSecretProvider(make_settings(), client_factory=lambda **_: client)

    with pytest.raises(SecretProviderError) as error:
        provider.get_secret("SMTP_PASSWORD", path="/application")

    assert secret_value not in str(error.value)
    assert client.closed


def test_secret_provider_requires_machine_identity_configuration():
    settings = make_settings(infisical_client_secret="")
    provider = InfisicalSecretProvider(settings, client_factory=lambda **_: pytest.fail())

    with pytest.raises(SecretProviderError, match="configuration is incomplete"):
        provider.get_secret("SMTP_PASSWORD", path="/application")
