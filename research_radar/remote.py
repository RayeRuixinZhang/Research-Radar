from __future__ import annotations

import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any


class RawArchive:
    def __init__(self, root: Path, prefix: str, run_id: str):
        self.root = root
        self.prefix = prefix.strip("/")
        self.run_id = run_id
        self.client = None
        self.bucket = os.getenv("S3_BUCKET_NAME", "")
        if self.bucket and os.getenv("S3_ACCESS_KEY_ID") and os.getenv("S3_SECRET_ACCESS_KEY"):
            import boto3

            self.client = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                region_name=os.getenv("S3_REGION") or "auto",
            )

    def save(self, source_id: str, payload: Any) -> dict:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        compressed = gzip.compress(encoded, compresslevel=6)
        digest = sha256(compressed).hexdigest()
        key = f"{self.prefix}/raw/{self.run_id}/{source_id}-{digest[:12]}.json.gz"
        path = self.root / "output" / "raw" / self.run_id / f"{source_id}-{digest[:12]}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(compressed)
        uploaded = False
        if self.client:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=compressed,
                ContentType="application/json",
                ContentEncoding="gzip",
                Metadata={"sha256": digest},
            )
            uploaded = True
        return {"source_id": source_id, "r2_key": key, "sha256": digest, "bytes": len(compressed), "uploaded": uploaded}

    def restore_database(self, target: Path) -> bool:
        if not self.client:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket, f"{self.prefix}/state/research-radar.db", str(target))
            return True
        except Exception:
            return False

    def upload_database(self, source: Path) -> bool:
        if not self.client or not source.exists():
            return False
        self.client.upload_file(
            str(source),
            self.bucket,
            f"{self.prefix}/state/research-radar.db",
            ExtraArgs={"ContentType": "application/vnd.sqlite3"},
        )
        return True

