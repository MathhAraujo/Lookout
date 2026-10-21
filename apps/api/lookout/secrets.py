from typing import Protocol

from infisical_sdk import InfisicalSDKClient

from lookout.config import Settings


class SecretProvider(Protocol):
    def get_secret(self, name: str, *, path: str) -> str: ...


class SecretProviderError(Exception):
    """Raised when a requested secret is missing or the vault is unavailable."""


class InfisicalSecretProvider:
    def __init__(self, settings: Settings, *, client_factory=InfisicalSDKClient):
        self.settings = settings
        self._client_factory = client_factory

    def get_secret(self, name: str, *, path: str) -> str:
        settings = self.settings
        if not name.strip() or not path.strip():
            raise SecretProviderError("secret name and path are required")
        if (
            not settings.infisical_client_id.strip()
            or not settings.infisical_client_secret.strip()
            or not settings.infisical_project_id.strip()
            or not settings.infisical_environment.strip()
        ):
            raise SecretProviderError("Infisical machine identity configuration is incomplete")

        try:
            client = self._client_factory(host=settings.infisical_url)
        except Exception:
            raise SecretProviderError("Infisical service is unavailable") from None

        value: str | None = None
        failure: str | None = None
        try:
            client.auth.universal_auth.login(
                client_id=settings.infisical_client_id,
                client_secret=settings.infisical_client_secret,
            )
            secret = client.secrets.get_secret_by_name(
                name,
                settings.infisical_environment,
                path,
                project_id=settings.infisical_project_id,
            )
            value = getattr(secret, "secretValue", None)
            if not isinstance(value, str) or not value:
                failure = "requested Infisical secret is missing"
        except Exception:
            failure = "Infisical secret retrieval failed"

        try:
            client.close()
        except Exception:
            if failure is None:
                failure = "Infisical client cleanup failed"

        if failure is not None:
            raise SecretProviderError(failure) from None
        if value is None:
            raise SecretProviderError("requested Infisical secret is missing") from None
        return value
