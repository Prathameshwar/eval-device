import asyncio
import importlib
import os
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from training_contracts.durability import durable_replace, sync_directory

from pms_api.core.common import now, require


class LocalStorage:
    async def close(self):
        return None

    def __init__(self, settings):
        self.root = settings.storage_root.resolve()
        self.limit_bytes = settings.vm_local_storage_limit_bytes if settings.vm_local_mode else None

    @contextmanager
    def quota_lock(self):
        if self.limit_bytes is None:
            yield
            return
        fcntl = cast(Any, importlib.import_module("fcntl"))

        with (self.root / ".quota.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def path(self, key):
        require(
            isinstance(key, str) and not any(p in {"..", "."} for p in key.split("/")),
            "invalid_object",
            "Invalid object key",
        )
        path = (self.root / key).resolve()
        require(path.is_relative_to(self.root) and path != self.root, "invalid_object", "Invalid object key")
        return path

    async def write(self, key, data, content_type="application/octet-stream"):
        path = self.path(key)

        def save():
            created = []
            directory = path.parent
            while not directory.exists():
                created.append(directory)
                directory = directory.parent
            path.parent.mkdir(parents=True, exist_ok=True)
            # Newly created nested directories must survive before their blobs are acknowledged.
            for directory in reversed(created):
                sync_directory(directory.parent)
            with self.quota_lock():
                if self.limit_bytes is not None:
                    used = sum(
                        candidate.stat().st_size
                        for candidate in self.root.rglob("*")
                        if candidate.is_file() and candidate.name != ".quota.lock"
                    )
                    previous = path.stat().st_size if path.exists() else 0
                    require(
                        used - previous + len(data) <= self.limit_bytes,
                        "storage_full",
                        "Private VM media storage is full",
                        507,
                    )
                temporary = path.with_name(path.name + "." + uuid4().hex + ".part")
                try:
                    with temporary.open("xb") as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
                    durable_replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)

        await asyncio.to_thread(save)

    async def read(self, key, max_bytes):
        path = self.path(key)
        require(path.exists(), "media_not_found", "Media object not found", 404)
        require(path.stat().st_size <= max_bytes, "media_too_large", "Media exceeds policy", 413)

        def bounded_read():
            with path.open("rb") as stream:
                return stream.read(max_bytes + 1)

        data = await asyncio.to_thread(bounded_read)
        require(len(data) <= max_bytes, "media_too_large", "Media exceeds policy", 413)
        return data

    async def stat(self, key):
        path = self.path(key)
        require(path.exists(), "media_not_found", "Media object not found", 404)
        return {"size": path.stat().st_size, "content_type": "application/octet-stream"}

    async def delete(self, key):
        path = self.path(key)

        def remove():
            with self.quota_lock():
                path.unlink(missing_ok=True)

        await asyncio.to_thread(remove)


class S3Storage:
    async def close(self):
        await asyncio.to_thread(self.client.close)

    def __init__(self, settings):
        import boto3
        from botocore.config import Config

        self.bucket = settings.storage_bucket
        require(bool(self.bucket), "storage_not_configured", "Configure the private storage bucket", 503)
        self.client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}),
        )

    async def write(self, key, data, content_type="application/octet-stream"):
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def read(self, key, max_bytes):
        meta = await self.stat(key)
        require(meta["size"] <= max_bytes, "media_too_large", "Media exceeds policy", 413)
        result = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        try:
            data = await asyncio.to_thread(result["Body"].read, max_bytes + 1)
            require(len(data) <= max_bytes, "media_too_large", "Media exceeds policy", 413)
            return data
        finally:
            result["Body"].close()

    async def stat(self, key):
        result = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
        return {"size": result["ContentLength"], "content_type": result.get("ContentType")}

    async def delete(self, key):
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def signed_url(self, key, method, seconds, content_type):
        params = {"Bucket": self.bucket, "Key": key}
        if method == "PUT":
            params["ContentType"] = content_type
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object" if method == "PUT" else "get_object",
            Params=params,
            ExpiresIn=seconds,
            HttpMethod=method,
        )


class AzureStorage:
    async def close(self):
        await asyncio.to_thread(self.client.close)
        await asyncio.to_thread(self.credential.close)

    def __init__(self, settings):
        import re

        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        require(
            bool(re.fullmatch(r"[a-z0-9]{3,24}", settings.azure_storage_account)),
            "storage_not_configured",
            "Configure the Azure storage account",
            503,
        )
        self.account = settings.azure_storage_account
        self.container = settings.storage_bucket
        self.credential = DefaultAzureCredential()
        self.client = BlobServiceClient(
            f"https://{self.account}.blob.core.windows.net", credential=self.credential
        )

    def blob(self, key):
        return self.client.get_blob_client(self.container, key)

    async def write(self, key, data, content_type="application/octet-stream"):
        from azure.storage.blob import ContentSettings

        await asyncio.to_thread(
            self.blob(key).upload_blob,
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    async def read(self, key, max_bytes):
        meta = await self.stat(key)
        require(meta["size"] <= max_bytes, "media_too_large", "Media exceeds policy", 413)
        stream = await asyncio.to_thread(self.blob(key).download_blob, length=max_bytes + 1)
        data = await asyncio.to_thread(stream.readall)
        require(len(data) <= max_bytes, "media_too_large", "Media exceeds policy", 413)
        return data

    async def stat(self, key):
        result = await asyncio.to_thread(self.blob(key).get_blob_properties)
        return {"size": result.size, "content_type": result.content_settings.content_type}

    async def delete(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            await asyncio.to_thread(self.blob(key).delete_blob, delete_snapshots="include")
        except ResourceNotFoundError:
            pass

    async def signed_url(self, key, method, seconds, content_type):
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        start = now() - timedelta(minutes=1)
        end = now() + timedelta(seconds=seconds)
        delegation = await asyncio.to_thread(self.client.get_user_delegation_key, start, end)
        sas = generate_blob_sas(
            self.account,
            self.container,
            key,
            user_delegation_key=delegation,
            permission=BlobSasPermissions(
                read=method == "GET", write=method == "PUT", create=method == "PUT"
            ),
            start=start,
            expiry=end,
        )
        return self.blob(key).url + "?" + sas


def storage_for(settings):
    return {"local": LocalStorage, "s3": S3Storage, "azure": AzureStorage}[settings.storage_backend](settings)
