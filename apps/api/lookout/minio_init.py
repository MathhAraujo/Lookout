import logging

from lookout.artifacts import S3ArtifactStore, ensure_bucket
from lookout.config import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    store = S3ArtifactStore(
        endpoint_url=settings.minio_endpoint_url,
        bucket=settings.minio_bucket,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    ensure_bucket(store.client, store.bucket)
    logger.info("MinIO artifact bucket is ready")


if __name__ == "__main__":
    main()
