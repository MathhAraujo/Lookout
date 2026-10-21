from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

ArtifactKind = Literal["resume", "answers", "opening_record"]
_ARTIFACT_KINDS = frozenset({"resume", "answers", "opening_record"})


class ArtifactStore(Protocol):
    def put_file(self, *, key: str, path: Path, content_type: str) -> str: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class ArtifactStoreError(Exception):
    """Base error for sanitized artifact storage failures."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when an artifact key does not exist."""


def build_artifact_object_key(application_id: UUID, artifact_id: UUID, kind: ArtifactKind) -> str:
    if kind not in _ARTIFACT_KINDS:
        raise ValueError("unsupported artifact kind")
    return f"applications/{application_id}/{artifact_id}/{kind}"


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code == "BucketAlreadyOwnedByYou":
            return
        raise ArtifactStoreError("could not initialize artifact bucket") from None
    except BotoCoreError:
        raise ArtifactStoreError("could not initialize artifact bucket") from None


class S3ArtifactStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        client=None,
    ) -> None:
        if not endpoint_url.strip():
            raise ValueError("MinIO endpoint URL is required")
        if not bucket.strip():
            raise ValueError("artifact bucket is required")
        if not access_key or not secret_key:
            raise ValueError("MinIO credentials are required")

        self.bucket = bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}),
        )

    def put_file(self, *, key: str, path: Path, content_type: str) -> str:
        try:
            self.client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        except (BotoCoreError, ClientError, OSError):
            raise ArtifactStoreError("could not upload artifact") from None
        return key

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise ArtifactNotFoundError("artifact not found") from None
            raise ArtifactStoreError("could not retrieve artifact") from None
        except BotoCoreError:
            raise ArtifactStoreError("could not retrieve artifact") from None

        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError):
            raise ArtifactStoreError("could not delete artifact") from None
