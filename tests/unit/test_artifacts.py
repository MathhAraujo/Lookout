from pathlib import Path
from uuid import UUID

import pytest
from lookout.artifacts import (
    ArtifactNotFoundError,
    S3ArtifactStore,
    build_artifact_object_key,
    ensure_bucket,
)


class StubS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.upload_calls: list[tuple[str, str, str, dict]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.create_bucket_calls: list[str] = []
        self.create_bucket_error = None

    def create_bucket(self, *, Bucket):
        self.create_bucket_calls.append(Bucket)
        if self.create_bucket_error is not None:
            raise self.create_bucket_error

    def upload_file(self, filename, bucket, key, *, ExtraArgs):
        self.upload_calls.append((filename, bucket, key, ExtraArgs))
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def get_object(self, *, Bucket, Key):
        from botocore.exceptions import ClientError

        content = self.objects.get((Bucket, Key))
        if content is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "The object does not exist"}},
                "GetObject",
            )
        from io import BytesIO

        return {"Body": BytesIO(content)}

    def delete_object(self, *, Bucket, Key):
        self.delete_calls.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


def make_store(client: StubS3Client) -> S3ArtifactStore:
    return S3ArtifactStore(
        endpoint_url="http://minio:9000",
        bucket="lookout-artifacts",
        access_key="fictional-access-key",
        secret_key="fictional-secret-key",
        client=client,
    )


def test_upload_and_download_preserve_binary_content_and_content_type(tmp_path):
    client = StubS3Client()
    store = make_store(client)
    path = tmp_path / "resume.pdf"
    expected = b"%PDF\x00\x01\xfffictional"
    path.write_bytes(expected)
    key = "applications/00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/resume"

    stored_key = store.put_file(key=key, path=path, content_type="application/pdf")

    assert stored_key == key
    assert client.upload_calls == [
        (str(path), "lookout-artifacts", key, {"ContentType": "application/pdf"})
    ]
    assert store.get_bytes(key) == expected


def test_missing_object_raises_artifact_not_found():
    store = make_store(StubS3Client())

    with pytest.raises(ArtifactNotFoundError):
        store.get_bytes("applications/unknown/unknown/resume")


def test_delete_removes_the_requested_object(tmp_path):
    client = StubS3Client()
    store = make_store(client)
    path = tmp_path / "answers.json"
    path.write_bytes(b'{"answer":"fictional"}')
    key = "applications/00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/answers"
    store.put_file(key=key, path=path, content_type="application/json")

    store.delete(key)

    assert client.delete_calls == [("lookout-artifacts", key)]
    assert ("lookout-artifacts", key) not in client.objects


def test_client_uses_endpoint_credentials_and_path_style_addressing(monkeypatch):
    import boto3

    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return StubS3Client()

    monkeypatch.setattr(boto3, "client", fake_client)

    S3ArtifactStore(
        endpoint_url="http://minio:9000",
        bucket="lookout-artifacts",
        access_key="fictional-access-key",
        secret_key="fictional-secret-key",
    )

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://minio:9000"
    assert captured["aws_access_key_id"] == "fictional-access-key"
    assert captured["aws_secret_access_key"] == "fictional-secret-key"
    assert captured["config"].s3["addressing_style"] == "path"


def test_artifact_object_keys_use_only_opaque_ids_and_known_kind():
    application_id = UUID("00000000-0000-0000-0000-000000000001")
    artifact_id = UUID("00000000-0000-0000-0000-000000000002")

    key = build_artifact_object_key(application_id, artifact_id, "resume")

    assert key == (
        "applications/00000000-0000-0000-0000-000000000001/"
        "00000000-0000-0000-0000-000000000002/resume"
    )
    assert "Globex" not in key
    assert "fictional@example.com" not in key
    with pytest.raises(ValueError, match="unsupported artifact kind"):
        build_artifact_object_key(application_id, artifact_id, "fictional-company")


def test_bucket_initializer_creates_the_configured_bucket():
    client = StubS3Client()

    ensure_bucket(client, "lookout-artifacts")

    assert client.create_bucket_calls == ["lookout-artifacts"]


def test_bucket_initializer_treats_an_existing_bucket_as_success():
    from botocore.exceptions import ClientError

    client = StubS3Client()
    client.create_bucket_error = ClientError(
        {
            "Error": {
                "Code": "BucketAlreadyOwnedByYou",
                "Message": "The bucket already exists",
            }
        },
        "CreateBucket",
    )

    ensure_bucket(client, "lookout-artifacts")

    assert client.create_bucket_calls == ["lookout-artifacts"]
