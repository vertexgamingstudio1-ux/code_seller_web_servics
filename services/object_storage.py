"""Private/public S3-compatible object storage adapter (no local-disk fallback)."""
import os
import uuid


class StorageNotConfigured(RuntimeError):
    pass


def _client():
    required = ("OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY_ID", "OBJECT_STORAGE_SECRET_ACCESS_KEY")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise StorageNotConfigured("Persistent object storage is not configured: " + ", ".join(missing))
    try:
        import boto3
    except ImportError as exc:
        raise StorageNotConfigured("Install the boto3 dependency to enable persistent uploads") from exc
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": os.environ["OBJECT_STORAGE_ACCESS_KEY_ID"],
        "aws_secret_access_key": os.environ["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
        "region_name": os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
    }
    endpoint = os.getenv("OBJECT_STORAGE_ENDPOINT", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client(**kwargs)


def upload(file_storage, *, prefix, max_bytes=5 * 1024 * 1024, private=False):
    name = (file_storage.filename or "").lower()
    allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    ext = next((e for e in allowed if name.endswith(e)), None)
    if not ext:
        raise ValueError("Upload a PNG, JPEG or WebP image")
    payload = file_storage.stream.read(max_bytes + 1)
    if not payload or len(payload) > max_bytes:
        raise ValueError("Image must be between 1 byte and 5 MB")
    content_type = file_storage.mimetype or ""
    if content_type != allowed[ext]:
        raise ValueError("Image content type does not match its file extension")
    signatures = {".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
                  ".jpg": payload.startswith(b"\xff\xd8\xff"),
                  ".jpeg": payload.startswith(b"\xff\xd8\xff"),
                  ".webp": len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"}
    if not signatures.get(ext):
        raise ValueError("File contents are not a valid image of the selected type")
    key = f"{prefix.strip('/')}/{uuid.uuid4().hex}{ext}"
    s3 = _client()
    s3.put_object(Bucket=os.environ["OBJECT_STORAGE_BUCKET"], Key=key,
                  Body=payload, ContentType=content_type,
                  CacheControl="public, max-age=31536000" if not private else "private, no-store")
    return key


def public_url(key):
    base = os.getenv("OBJECT_STORAGE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise StorageNotConfigured("Set OBJECT_STORAGE_PUBLIC_BASE_URL to enable public campaign banners")
    return base + "/" + key.lstrip("/")


def private_url(key, expires=300):
    s3 = _client()
    return s3.generate_presigned_url("get_object", Params={"Bucket": os.environ["OBJECT_STORAGE_BUCKET"], "Key": key}, ExpiresIn=expires)
