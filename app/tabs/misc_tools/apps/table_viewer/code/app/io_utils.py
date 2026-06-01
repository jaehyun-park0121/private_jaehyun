"""파일 시스템 / S3 / SSH-SFTP IO — 폴더 스캔, JSON 로드/저장, 이미지 바이트 로드.

Qt import 금지 (테스트 가능성 유지). QPixmap 변환은 호출 측 담당.
"""

from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable, Optional, Protocol

from .constants import IMAGE_EXTS

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    _S3_ERRORS: tuple = (BotoCoreError, ClientError, NoCredentialsError)
except ImportError:
    boto3 = None
    _S3_ERRORS = ()

try:
    import paramiko
    from paramiko.ssh_exception import (
        AuthenticationException,
        BadHostKeyException,
        SSHException,
    )
    _SSH_ERRORS: tuple = (
        AuthenticationException,
        BadHostKeyException,
        SSHException,
        OSError,
    )
except ImportError:
    paramiko = None
    _SSH_ERRORS = ()


@dataclass(frozen=True)
class ImageEntry:
    """로컬/S3/SSH 통합 엔트리.

    image_path/json_path : 표시·트리 구성용 상대 경로 (forward slash 형태)
    has_table            : 동반 JSON의 TABLE shape 포함 여부 (`None`이면 아직 미확인)
    image_key/json_key   : 백엔드 식별자
        - 로컬: 절대 경로 문자열
        - S3:  버킷 내 키
        - SSH: 서버의 절대 POSIX 경로
    json_key는 동반 JSON이 없으면 "".
    """
    image_path: Path
    json_path: Path
    has_json: bool
    has_table: bool | None
    image_key: str
    json_key: str = ""


TablePresenceProgress = Callable[[int, int, ImageEntry], None]


# ===== 백엔드 프로토콜 =====
class StorageBackend(Protocol):
    """파일 저장소 추상화. Local/S3/SSH 공통 인터페이스."""

    def scan(self) -> list[ImageEntry]: ...
    def load_image_bytes(self, entry: ImageEntry) -> bytes: ...
    def load_json(self, entry: ImageEntry) -> dict: ...
    def save_json(self, entry: ImageEntry, data: dict) -> None: ...
    def display_root(self) -> str: ...
    def target_kind(self) -> str: ...
    def json_target_display(self, entry: ImageEntry) -> str: ...
    def resolve_table_presence(
        self,
        entries: list[ImageEntry],
        progress_callback: TablePresenceProgress | None = None,
    ) -> list[ImageEntry]: ...


class StorageBackendError(RuntimeError):
    """저장소 작업 실패 시 발생. 호출 측에서 사용자 친화 메시지 표시 용도."""


# ===== 로컬 =====
@dataclass
class LocalBackend:
    folder: Path

    def scan(self) -> list[ImageEntry]:
        entries: list[ImageEntry] = []
        for p in sorted(self.folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                json_abs = p.with_suffix(".json")
                has_json = json_abs.exists()
                rel_image = p.relative_to(self.folder)
                rel_json = json_abs.relative_to(self.folder)
                entries.append(
                    ImageEntry(
                        image_path=rel_image,
                        json_path=rel_json,
                        has_json=has_json,
                        has_table=None if has_json else False,
                        image_key=str(p),
                        json_key=str(json_abs) if has_json else "",
                    )
                )
        return entries

    def load_image_bytes(self, entry: ImageEntry) -> bytes:
        return Path(entry.image_key).read_bytes()

    def load_json(self, entry: ImageEntry) -> dict:
        if not entry.json_key:
            raise FileNotFoundError("JSON 경로가 없습니다.")
        with Path(entry.json_key).open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, entry: ImageEntry, data: dict) -> None:
        # 새 JSON(없던 경우)은 image_key 옆에 동일 stem으로 생성
        target = Path(entry.json_key) if entry.json_key else Path(entry.image_key).with_suffix(".json")
        with target.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def display_root(self) -> str:
        return str(self.folder)

    def target_kind(self) -> str:
        return "로컬"

    def json_target_display(self, entry: ImageEntry) -> str:
        target = Path(entry.json_key) if entry.json_key else Path(entry.image_key).with_suffix(".json")
        return str(target)

    def resolve_table_presence(
        self,
        entries: list[ImageEntry],
        progress_callback: TablePresenceProgress | None = None,
    ) -> list[ImageEntry]:
        return _resolve_pending_entries(
            entries,
            lambda entry: _json_file_has_table(Path(entry.json_key)),
            progress_callback=progress_callback,
            max_workers=_local_scan_workers(len(entries)),
            thread_name_prefix="table-viewer-local",
        )


# ===== S3 =====
@dataclass
class S3Config:
    bucket: str
    prefix: str  # 정규화된 prefix (trailing slash 제거)
    region: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    session_token: Optional[str] = None


def parse_s3_path(raw_value: str) -> tuple[str, str]:
    """`s3://bucket/prefix` 또는 `bucket/prefix` 형태를 (bucket, prefix)로 파싱."""
    value = (raw_value or "").strip()
    if not value:
        raise ValueError("S3 경로를 입력해주세요.")
    if value.startswith("s3://"):
        value = value[5:]
    value = value.lstrip("/")
    bucket, _, prefix = value.partition("/")
    if not bucket:
        raise ValueError("S3 버킷명이 없습니다.")
    return bucket, prefix.strip("/")


class S3BackendError(StorageBackendError):
    """S3 작업 실패 시 발생."""


class S3Backend:
    """S3 백엔드. boto3 미설치 시 생성 자체가 실패함."""

    def __init__(self, config: S3Config):
        if boto3 is None:
            raise S3BackendError("boto3가 설치되어 있지 않습니다. requirements.txt 설치 후 재실행하세요.")

        self.config = config
        self.bucket = config.bucket
        self.prefix = config.prefix.rstrip("/")
        self.list_prefix = f"{self.prefix}/" if self.prefix else ""

        session_kwargs: dict = {"region_name": config.region}
        if config.access_key and config.secret_key:
            session_kwargs["aws_access_key_id"] = config.access_key
            session_kwargs["aws_secret_access_key"] = config.secret_key
            if config.session_token:
                session_kwargs["aws_session_token"] = config.session_token

        try:
            session = boto3.session.Session(**session_kwargs)
            self.client = session.client("s3")
            self.client.list_objects_v2(Bucket=self.bucket, Prefix=self.list_prefix, MaxKeys=1)
        except _S3_ERRORS as exc:
            raise S3BackendError(f"S3 연결에 실패했습니다.\n{exc}") from exc

    def _key_to_relative(self, key: str) -> str:
        if self.list_prefix and key.startswith(self.list_prefix):
            return key[len(self.list_prefix):]
        return key

    def scan(self) -> list[ImageEntry]:
        json_candidates: dict[str, tuple[str, str]] = {}
        image_candidates: dict[str, tuple[str, str]] = {}

        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.list_prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    lower = key.lower()
                    rel = self._key_to_relative(key)
                    suffix = Path(lower).suffix
                    if suffix == ".json":
                        json_candidates[rel[:-5]] = (key, rel)
                    elif suffix in IMAGE_EXTS:
                        image_candidates[rel[: -len(suffix)]] = (key, rel)
        except _S3_ERRORS as exc:
            raise S3BackendError(f"S3 목록 조회에 실패했습니다.\n{exc}") from exc

        entries: list[ImageEntry] = []
        all_bases = sorted(set(json_candidates) | set(image_candidates))
        for base in all_bases:
            if base not in image_candidates:
                continue
            image_key, image_rel = image_candidates[base]
            json_pair = json_candidates.get(base)
            if json_pair:
                json_key, json_rel = json_pair
                has_json = True
                has_table = None
            else:
                json_key = ""
                json_rel = base + ".json"
                has_json = False
                has_table = False
            entries.append(
                ImageEntry(
                    image_path=Path(image_rel),
                    json_path=Path(json_rel),
                    has_json=has_json,
                    has_table=has_table,
                    image_key=image_key,
                    json_key=json_key,
                )
            )
        return entries

    def load_image_bytes(self, entry: ImageEntry) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=entry.image_key)
            return response["Body"].read()
        except _S3_ERRORS as exc:
            raise S3BackendError(f"이미지를 불러오지 못했습니다.\ns3://{self.bucket}/{entry.image_key}\n{exc}") from exc

    def load_json(self, entry: ImageEntry) -> dict:
        if not entry.json_key:
            raise S3BackendError("JSON 키가 없습니다.")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=entry.json_key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except _S3_ERRORS as exc:
            raise S3BackendError(f"JSON을 불러오지 못했습니다.\ns3://{self.bucket}/{entry.json_key}\n{exc}") from exc

    def save_json(self, entry: ImageEntry, data: dict) -> None:
        # 새 JSON(없던 경우)도 image_key 기준으로 키를 도출해 저장
        target_key = entry.json_key or _derive_json_key(entry.image_key)
        payload = json.dumps(data, ensure_ascii=False, indent=4)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=target_key,
                Body=(payload + "\n").encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
        except _S3_ERRORS as exc:
            raise S3BackendError(
                f"JSON 저장에 실패했습니다.\ns3://{self.bucket}/{target_key}\n{exc}"
            ) from exc

    def display_root(self) -> str:
        if self.prefix:
            return f"s3://{self.bucket}/{self.prefix}"
        return f"s3://{self.bucket}"

    def target_kind(self) -> str:
        return "S3"

    def json_target_display(self, entry: ImageEntry) -> str:
        target_key = entry.json_key or _derive_json_key(entry.image_key)
        return f"s3://{self.bucket}/{target_key}"

    def resolve_table_presence(
        self,
        entries: list[ImageEntry],
        progress_callback: TablePresenceProgress | None = None,
    ) -> list[ImageEntry]:
        return _resolve_pending_entries(
            entries,
            lambda entry: self._json_key_has_table(entry.json_key),
            progress_callback=progress_callback,
            max_workers=_s3_scan_workers(len(entries)),
            thread_name_prefix="table-viewer-s3",
        )

    def _json_key_has_table(self, key: str) -> bool:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            payload = response["Body"].read()
        except _S3_ERRORS:
            return False
        return _json_bytes_has_table(payload)


# ===== SSH / SFTP =====
@dataclass
class SSHConfig:
    host: str
    port: int
    username: str
    pem_path: Path
    remote_root: str
    passphrase: Optional[str] = None
    timeout_seconds: int = 15


class SSHBackendError(StorageBackendError):
    """SSH/SFTP 작업 실패 시 발생."""


class SSHBackend:
    """PEM 기반 SSH/SFTP 백엔드. 로컬 캐시 없이 원격 파일을 bytes로 읽는다."""

    def __init__(self, config: SSHConfig):
        if paramiko is None:
            raise SSHBackendError("paramiko가 설치되어 있지 않습니다. requirements.txt 설치 후 재실행하세요.")

        self.config = config
        self.host = config.host.strip()
        self.port = config.port
        self.username = config.username.strip()
        self.pem_path = config.pem_path
        self.remote_root = _normalize_remote_root(config.remote_root)
        self._client = None
        self._sftp = None

        if not self.host:
            raise SSHBackendError("SSH Host를 입력해주세요.")
        if not self.username:
            raise SSHBackendError("SSH User를 입력해주세요.")
        if not self.pem_path.is_file():
            raise SSHBackendError(f"PEM 파일을 찾을 수 없습니다.\n{self.pem_path}")

        client = None
        sftp = None
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                key_filename=str(self.pem_path),
                passphrase=config.passphrase or None,
                look_for_keys=False,
                allow_agent=False,
                timeout=config.timeout_seconds,
                banner_timeout=config.timeout_seconds,
                auth_timeout=config.timeout_seconds,
            )
            sftp = client.open_sftp()
        except _SSH_ERRORS as exc:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()
            raise SSHBackendError(f"SSH/SFTP 연결에 실패했습니다.\n{exc}") from exc

        try:
            attrs = sftp.stat(self.remote_root)
            if not stat.S_ISDIR(attrs.st_mode or 0):
                raise SSHBackendError(f"원격 경로가 폴더가 아닙니다.\n{self.remote_root}")
        except FileNotFoundError as exc:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()
            raise SSHBackendError(
                "SSH/SFTP 연결은 성공했지만 원격 루트 경로를 찾을 수 없습니다.\n"
                f"{self.remote_root}"
            ) from exc
        except PermissionError as exc:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()
            raise SSHBackendError(
                "SSH/SFTP 연결은 성공했지만 원격 루트 경로에 접근할 권한이 없습니다.\n"
                f"{self.remote_root}"
            ) from exc
        except SSHBackendError:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()
            raise
        except _SSH_ERRORS as exc:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()
            raise SSHBackendError(
                "SSH/SFTP 연결은 성공했지만 원격 루트 경로를 확인하지 못했습니다.\n"
                f"{self.remote_root}\n{exc}"
            ) from exc

        self._client = client
        self._sftp = sftp

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except OSError:
                pass
            self._sftp = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def scan(self) -> list[ImageEntry]:
        json_candidates: dict[str, tuple[str, str]] = {}
        image_candidates: dict[str, tuple[str, str]] = {}

        try:
            for remote_path in self._walk_files(self.remote_root):
                rel = self._remote_to_relative(remote_path)
                lower = rel.lower()
                suffix = PurePosixPath(lower).suffix
                if suffix == ".json":
                    json_candidates[rel[:-5]] = (remote_path, rel)
                elif suffix in IMAGE_EXTS:
                    image_candidates[rel[: -len(suffix)]] = (remote_path, rel)
        except _SSH_ERRORS as exc:
            raise SSHBackendError(f"SSH/SFTP 목록 조회에 실패했습니다.\n{exc}") from exc

        entries: list[ImageEntry] = []
        all_bases = sorted(set(json_candidates) | set(image_candidates))
        for base in all_bases:
            if base not in image_candidates:
                continue
            image_key, image_rel = image_candidates[base]
            json_pair = json_candidates.get(base)
            if json_pair:
                json_key, json_rel = json_pair
                has_json = True
                has_table = None
            else:
                json_key = ""
                json_rel = base + ".json"
                has_json = False
                has_table = False
            entries.append(
                ImageEntry(
                    image_path=Path(image_rel),
                    json_path=Path(json_rel),
                    has_json=has_json,
                    has_table=has_table,
                    image_key=image_key,
                    json_key=json_key,
                )
            )
        return entries

    def load_image_bytes(self, entry: ImageEntry) -> bytes:
        try:
            with self._sftp.open(entry.image_key, "rb") as f:
                return f.read()
        except _SSH_ERRORS as exc:
            raise SSHBackendError(f"이미지를 불러오지 못했습니다.\n{entry.image_key}\n{exc}") from exc

    def load_json(self, entry: ImageEntry) -> dict:
        if not entry.json_key:
            raise SSHBackendError("JSON 경로가 없습니다.")
        try:
            with self._sftp.open(entry.json_key, "rb") as f:
                payload = f.read()
            return json.loads(payload.decode("utf-8"))
        except _SSH_ERRORS as exc:
            raise SSHBackendError(f"JSON을 불러오지 못했습니다.\n{entry.json_key}\n{exc}") from exc

    def save_json(self, entry: ImageEntry, data: dict) -> None:
        target_path = entry.json_key or _derive_remote_json_path(entry.image_key)
        payload = json.dumps(data, ensure_ascii=False, indent=4)
        try:
            with self._sftp.open(target_path, "wb") as f:
                f.write((payload + "\n").encode("utf-8"))
        except _SSH_ERRORS as exc:
            raise SSHBackendError(f"JSON 저장에 실패했습니다.\n{target_path}\n{exc}") from exc

    def display_root(self) -> str:
        return _format_ssh_target(self.username, self.host, self.port, self.remote_root)

    def target_kind(self) -> str:
        return "SSH/SFTP"

    def json_target_display(self, entry: ImageEntry) -> str:
        target_path = entry.json_key or _derive_remote_json_path(entry.image_key)
        return _format_ssh_target(self.username, self.host, self.port, target_path)

    def resolve_table_presence(
        self,
        entries: list[ImageEntry],
        progress_callback: TablePresenceProgress | None = None,
    ) -> list[ImageEntry]:
        return _resolve_pending_entries(
            entries,
            lambda entry: self._json_path_has_table(entry.json_key),
            progress_callback=progress_callback,
            max_workers=_ssh_scan_workers(len(entries)),
            thread_name_prefix="table-viewer-ssh",
        )

    def _json_path_has_table(self, path: str) -> bool:
        try:
            with self._sftp.open(path, "rb") as f:
                payload = f.read()
        except _SSH_ERRORS:
            return False
        return _json_bytes_has_table(payload)

    def _walk_files(self, folder: str):
        stack = [folder]
        while stack:
            current = stack.pop()
            for attr in self._sftp.listdir_attr(current):
                name = attr.filename
                if name in (".", ".."):
                    continue
                remote_path = _join_remote_path(current, name)
                mode = attr.st_mode or 0
                if stat.S_ISDIR(mode):
                    stack.append(remote_path)
                elif stat.S_ISREG(mode):
                    yield remote_path

    def _remote_to_relative(self, remote_path: str) -> str:
        if self.remote_root == "/":
            return remote_path.lstrip("/")
        prefix = f"{self.remote_root.rstrip('/')}/"
        if remote_path.startswith(prefix):
            return remote_path[len(prefix):]
        return remote_path.lstrip("/")


def _derive_json_key(image_key: str) -> str:
    """이미지 키 → 동반 JSON 키 (확장자 교체)."""
    p = Path(image_key)
    return str(p.with_suffix(".json")).replace("\\", "/")


def _derive_remote_json_path(image_key: str) -> str:
    """원격 POSIX 이미지 경로 → 동반 JSON 경로."""
    return PurePosixPath(image_key).with_suffix(".json").as_posix()


def _normalize_remote_root(raw_value: str) -> str:
    value = (raw_value or "").strip().replace("\\", "/")
    if not value:
        raise SSHBackendError("원격 루트 경로를 입력해주세요.")
    return value.rstrip("/") or "/"


def _join_remote_path(folder: str, name: str) -> str:
    if folder == "/":
        return f"/{name}"
    return f"{folder.rstrip('/')}/{name}"


def _format_ssh_target(username: str, host: str, port: int, path: str) -> str:
    if path.startswith("/"):
        return f"{username}@{host}:{port}:{path}"
    return f"{username}@{host}:{port}:{path} (상대 경로)"


def _json_file_has_table(path: Path) -> bool:
    try:
        payload = path.read_bytes()
    except OSError:
        return False
    return _json_bytes_has_table(payload)


def _json_bytes_has_table(payload: bytes) -> bool:
    if b'"shapes"' not in payload or b"TABLE" not in payload:
        return False
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    shapes = data.get("shapes")
    if not isinstance(shapes, list):
        return False
    return any(
        isinstance(shape, dict) and shape.get("label") == "TABLE"
        for shape in shapes
    )


def _resolve_pending_entries(
    entries: list[ImageEntry],
    checker: Callable[[ImageEntry], bool],
    progress_callback: TablePresenceProgress | None,
    max_workers: int,
    thread_name_prefix: str,
) -> list[ImageEntry]:
    pending = [
        (idx, entry)
        for idx, entry in enumerate(entries)
        if entry.has_json and entry.has_table is None
    ]
    total = len(pending)
    if total == 0:
        return list(entries)

    resolved_map: dict[int, ImageEntry] = {}
    workers = max(1, min(max_workers, total))
    if workers == 1:
        for step, (idx, entry) in enumerate(pending, start=1):
            checked = replace(entry, has_table=checker(entry))
            resolved_map[idx] = checked
            if progress_callback is not None:
                progress_callback(step, total, checked)
        return [
            resolved_map.get(idx, entry)
            for idx, entry in enumerate(entries)
        ]

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix=thread_name_prefix,
    ) as executor:
        future_map = {
            executor.submit(checker, entry): (idx, entry)
            for idx, entry in pending
        }
        for step, future in enumerate(as_completed(future_map), start=1):
            idx, entry = future_map[future]
            checked = replace(entry, has_table=future.result())
            resolved_map[idx] = checked
            if progress_callback is not None:
                progress_callback(step, total, checked)

    return [
        resolved_map.get(idx, entry)
        for idx, entry in enumerate(entries)
    ]


def _local_scan_workers(total_entries: int) -> int:
    cpu = os.cpu_count() or 4
    return min(8, max(2, cpu), max(1, total_entries))


def _s3_scan_workers(total_entries: int) -> int:
    return min(12, max(4, total_entries))


def _ssh_scan_workers(total_entries: int) -> int:
    # Paramiko SFTPClient는 스레드 안전하지 않으므로 보수적으로 순차 처리한다.
    return 1
