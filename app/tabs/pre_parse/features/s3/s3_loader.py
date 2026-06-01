from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Tuple


class S3Loader:
    """S3 프로젝트 경로를 스캔해 도서/페이지 메타를 생성한다."""

    def __init__(self, aws_config: Dict[str, Any]) -> None:
        self.aws_config = aws_config
        self._client = self._build_client()

    def scan_project(self, bucket: str, prefix: str) -> List[Dict[str, Any]]:
        normalized_prefix = prefix.lstrip("/")
        if normalized_prefix and not normalized_prefix.endswith("/"):
            normalized_prefix += "/"

        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=normalized_prefix)

        results: List[Dict[str, Any]] = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if not key or key.endswith("/"):
                    continue
                if not self._is_supported_file(key):
                    continue
                results.append(self._to_page_meta(bucket, normalized_prefix, key, obj))
        return results

    def _build_client(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3가 설치되어 있지 않습니다. `pip install boto3` 후 다시 시도해주세요.") from exc

        access_key = str(self.aws_config.get("access_key", "")).strip()
        secret_key = str(self.aws_config.get("secret_key", "")).strip()
        session_token = str(self.aws_config.get("session_token", "")).strip()
        region = str(self.aws_config.get("region", "")).strip()

        if not access_key or not secret_key:
            raise ValueError("AWS Access Key와 Secret Key를 설정에서 입력해주세요.")

        session_kwargs: Dict[str, Any] = {}
        if region:
            session_kwargs["region_name"] = region

        session = boto3.Session(**session_kwargs)
        client_kwargs: Dict[str, Any] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
        if session_token:
            client_kwargs["aws_session_token"] = session_token
        if region:
            client_kwargs["region_name"] = region
        return session.client("s3", **client_kwargs)

    def _to_page_meta(self, bucket: str, prefix: str, key: str, obj: Dict[str, Any]) -> Dict[str, Any]:
        relative = key[len(prefix) :] if key.startswith(prefix) else key
        parts = [p for p in PurePosixPath(relative).parts if p]
        file_name = parts[-1] if parts else key
        book_id = "unknown"
        if len(parts) >= 2:
            book_id = parts[0]
        elif "_" in file_name:
            book_id = file_name.split("_", 1)[0]
        return {
            "bucket": bucket,
            "book_id": book_id,
            "page_no": file_name,
            "s3_key": key,
            "etag": str(obj.get("ETag", "")).strip("\""),
            "last_modified": str(obj.get("LastModified", "")),
            "size": int(obj.get("Size", 0) or 0),
            "status": "PENDING",
            "issue_count": 0,
        }

    def _is_supported_file(self, key: str) -> bool:
        lowered = key.lower()
        return lowered.endswith((".png", ".jpg", ".jpeg", ".json"))

    @staticmethod
    def parse_s3_path(s3_path: str) -> Tuple[str, str]:
        value = s3_path.strip()
        if not value.startswith("s3://"):
            raise ValueError("S3 경로는 s3:// 로 시작해야 합니다.")
        without_scheme = value[5:]
        if not without_scheme:
            raise ValueError("S3 경로에 버킷명이 없습니다.")
        if "/" in without_scheme:
            bucket, prefix = without_scheme.split("/", 1)
        else:
            bucket, prefix = without_scheme, ""
        if not bucket.strip():
            raise ValueError("S3 경로에 버킷명이 없습니다.")
        return bucket.strip(), prefix.strip()
