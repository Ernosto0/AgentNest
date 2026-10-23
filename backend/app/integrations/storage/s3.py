"""Private S3-compatible objects with presigned GET URLs (ADR-015)."""

import io
from typing import BinaryIO, Protocol, TypedDict, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.integrations.storage.base import StorageObjectNotFound, validate_key


class _ObjectBody(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class _GetObjectResult(TypedDict):
    Body: _ObjectBody


class S3Client(Protocol):
    """Only the SDK surface this backend needs; injectable without network or credentials."""

    def put_object(self, *, Bucket: str, Key: str, Body: BinaryIO, ContentType: str) -> object: ...

    def get_object(self, *, Bucket: str, Key: str) -> _GetObjectResult: ...

    def delete_object(self, *, Bucket: str, Key: str) -> object: ...

    def generate_presigned_url(
        self, ClientMethod: str, *, Params: dict[str, str], ExpiresIn: int
    ) -> str: ...


class S3MediaStorage:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str = "",
        region: str = "auto",
        access_key_id: str = "",
        secret_access_key: str = "",
        client: S3Client | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = (
            client
            if client is not None
            else cast(
                S3Client,
                boto3.client(
                    "s3",
                    endpoint_url=endpoint_url or None,
                    region_name=region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    config=Config(signature_version="s3v4", retries={"max_attempts": 0}),
                ),
            )
        )

    def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        validate_key(key)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def open(self, key: str) -> BinaryIO:
        validate_key(key)
        try:
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        except ClientError as exc:
            error = exc.response.get("Error", {})
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error.get("Code") in {"NoSuchKey", "404", "NotFound"} or status == 404:
                raise StorageObjectNotFound(key) from None
            raise
        try:
            return io.BytesIO(body.read())
        finally:
            body.close()

    def delete(self, key: str) -> None:
        validate_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def public_fetch_url(self, key: str, ttl_s: int) -> str:
        validate_key(key)
        if not 1 <= ttl_s <= 604800:  # SigV4 presigned URLs have a seven-day maximum.
            raise ValueError("S3 presigned URL TTL must be between 1 and 604800 seconds.")
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=ttl_s
        )
