from __future__ import annotations

import concurrent.futures
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import boto3
import regex

from app.common.config.parallel_settings import resolve_parallel_workers

ProgressCallback = Optional[Callable[[str, int, int], None]]
StopRequestedCallback = Optional[Callable[[], bool]]

TEXT_LABEL_KEYWORDS_DEFAULT = ("TEXT", "CAPTION", "FOOTNOTE", "TITLE")
SPECIAL_CHAR_PATTERN = regex.compile(
    r"[^A-Za-z0-9가-힣~!@#$%^&*()_\+\-=\[\]{}\|;:'\",<\.>/\?`\n]"
)


@dataclass
class S3Config:
    access_key_id: str = ""
    secret_access_key: str = ""
    session_token: str = ""
    region_name: str = ""
    profile_name: str = ""


@dataclass
class AnalysisConfig:
    text_label_keywords: Sequence[str] = TEXT_LABEL_KEYWORDS_DEFAULT
    max_workers: Optional[int] = None


@dataclass
class Box:
    label: str
    x1: float
    y1: float
    x2: float
    y2: float
    text: str

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"잘못된 S3 URI: {s3_uri}")
    without_scheme = s3_uri[len("s3://") :]
    parts = without_scheme.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def _build_s3_client(s3_config: Optional[S3Config]) -> boto3.client:
    s3_config = s3_config or S3Config()
    if s3_config.profile_name:
        session = boto3.Session(
            profile_name=s3_config.profile_name,
            region_name=s3_config.region_name or None,
        )
        return session.client("s3")

    kwargs = {}
    if s3_config.access_key_id:
        kwargs["aws_access_key_id"] = s3_config.access_key_id
    if s3_config.secret_access_key:
        kwargs["aws_secret_access_key"] = s3_config.secret_access_key
    if s3_config.session_token:
        kwargs["aws_session_token"] = s3_config.session_token
    if s3_config.region_name:
        kwargs["region_name"] = s3_config.region_name
    return boto3.client("s3", **kwargs)


def collect_s3_json_keys(
    s3_uri: str,
    s3_config: Optional[S3Config] = None,
    progress_callback: ProgressCallback = None,
) -> Tuple[str, Any, List[str]]:
    bucket, prefix = parse_s3_uri(s3_uri)
    s3 = _build_s3_client(s3_config)
    keys: List[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".json"):
                keys.append(key)
        if progress_callback:
            progress_callback("S3 목록 수집", len(keys), 0)
    return bucket, s3, keys


def find_matching_s3_image_key(s3_client: Any, bucket: str, json_key: str) -> str:
    path = Path(json_key)
    prefix = "" if str(path.parent) in {"", "."} else f"{path.parent.as_posix().rstrip('/')}/"
    stem = path.stem
    candidate_key = f"{prefix}{stem}.png"
    try:
        s3_client.head_object(Bucket=bucket, Key=candidate_key)
        return candidate_key
    except Exception:
        return ""


def get_filename_from_key(key: str) -> str:
    return Path(key).name


def get_book_name_from_key(key: str) -> str:
    path = Path(key)
    return path.parent.name if path.parent.name else "unknown_book"


def to_box(shape: dict) -> Optional[Box]:
    points = shape.get("points", [])
    if not isinstance(points, list) or len(points) < 2:
        return None
    try:
        (x1, y1), (x2, y2) = points[:2]
        x_min, x_max = sorted((float(x1), float(x2)))
        y_min, y_max = sorted((float(y1), float(y2)))
    except (TypeError, ValueError):
        return None

    label = str(shape.get("label", "")).strip()
    flags = shape.get("flags") or {}
    text = str(flags.get("text", "") or "")
    return Box(label=label, x1=x_min, y1=y_min, x2=x_max, y2=y_max, text=text)


def is_text_related_label(label: str, text_label_keywords: Sequence[str]) -> bool:
    upper = (label or "").upper()
    return any(keyword.upper() in upper for keyword in text_label_keywords)


def y_overlap_ratio(a: Box, b: Box) -> float:
    overlap = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    min_h = max(1e-9, min(a.height, b.height))
    return overlap / min_h


def is_strictly_contained(inner: Box, outer: Box, eps: float = 1e-6) -> bool:
    if inner is outer:
        return False
    inside = (
        outer.x1 - eps <= inner.x1 <= outer.x2 + eps
        and outer.x1 - eps <= inner.x2 <= outer.x2 + eps
        and outer.y1 - eps <= inner.y1 <= outer.y2 + eps
        and outer.y1 - eps <= inner.y2 <= outer.y2 + eps
    )
    if not inside:
        return False
    return (
        inner.x1 > outer.x1 + eps
        or inner.y1 > outer.y1 + eps
        or inner.x2 < outer.x2 - eps
        or inner.y2 < outer.y2 - eps
    )


def filter_contained_boxes(boxes: Sequence[Box]) -> List[Box]:
    kept: List[Box] = []
    for i, candidate in enumerate(boxes):
        contained = False
        for j, other in enumerate(boxes):
            if i == j:
                continue
            if is_strictly_contained(candidate, other):
                contained = True
                break
        if not contained:
            kept.append(candidate)
    return kept


def is_multicolumn_suspected(boxes: Sequence[Box]) -> bool:
    candidates = [box for box in filter_contained_boxes(boxes) if box.area > 0]
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if y_overlap_ratio(candidates[i], candidates[j]) > 0:
                return True
    return False


def split_characters(text: str) -> Dict[str, int]:
    all_chars = len(text)
    spaces = sum(1 for ch in text if ch == " ")
    word_count = len([word for word in text.split(" ") if word])

    language_chars = len(regex.findall(r"\p{L}", text))
    hangul_chars = len(regex.findall(r"\p{Hangul}", text))
    english_chars = len(regex.findall(r"[A-Za-z]", text))
    special_chars = len(SPECIAL_CHAR_PATTERN.findall(text))

    return {
        "all_chars": all_chars,
        "spaces": spaces,
        "word_count": word_count,
        "language_chars": language_chars,
        "hangul_chars": hangul_chars,
        "english_chars": english_chars,
        "special_chars": special_chars,
    }


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def analyze_page(boxes: Sequence[Box], text_label_keywords: Sequence[str]) -> dict:
    label_counter = Counter([box.label for box in boxes if box.label])
    total_boxes = len(boxes)
    multicolumn = is_multicolumn_suspected(boxes)
    bbox_lt_2 = 1 if total_boxes < 2 else 0

    text_related_boxes = [box for box in boxes if is_text_related_label(box.label, text_label_keywords)]
    text_values = [box.text for box in text_related_boxes if box.text]
    full_text = "\n".join(text_values)
    char_stats = split_characters(full_text)
    empty_text_box_count = sum(1 for box in text_related_boxes if not box.text.strip())

    language_chars = char_stats["language_chars"]
    all_chars = char_stats["all_chars"]
    english_chars = char_stats["english_chars"]
    hangul_chars = char_stats["hangul_chars"]
    other_foreign_chars = max(0, language_chars - hangul_chars - english_chars)

    return {
        "total_boxes": total_boxes,
        "label_counts": dict(label_counter),
        "multicolumn_suspected": multicolumn,
        "bbox_lt_2": bbox_lt_2,
        "word_count": char_stats["word_count"],
        "all_chars": all_chars,
        "spaces": char_stats["spaces"],
        "language_chars": language_chars,
        "hangul_chars": hangul_chars,
        "english_chars": english_chars,
        "special_chars": char_stats["special_chars"],
        "other_foreign_chars": other_foreign_chars,
        "space_ratio": safe_div(char_stats["spaces"], all_chars),
        "english_ratio": safe_div(english_chars, language_chars),
        "other_foreign_ratio": safe_div(other_foreign_chars, language_chars),
        "special_char_ratio": safe_div(char_stats["special_chars"], all_chars),
        "empty_text_box_count": empty_text_box_count,
    }


def aggregate_book(page_rows: Sequence[dict]) -> dict:
    book: dict = {}
    if not page_rows:
        return book

    label_counter = Counter()
    for row in page_rows:
        for label, count in row["label_counts"].items():
            label_counter[label] += count

    pages = len(page_rows)
    all_chars_total = sum(int(row["all_chars"]) for row in page_rows)
    spaces_total = sum(int(row["spaces"]) for row in page_rows)
    language_chars_total = sum(int(row["language_chars"]) for row in page_rows)
    hangul_chars_total = sum(int(row["hangul_chars"]) for row in page_rows)
    english_chars_total = sum(int(row["english_chars"]) for row in page_rows)
    special_chars_total = sum(int(row["special_chars"]) for row in page_rows)
    other_foreign_chars_total = max(0, language_chars_total - hangul_chars_total - english_chars_total)

    book["pages"] = pages
    book["multicolumn_suspected_pages"] = sum(int(row["multicolumn_suspected"]) for row in page_rows)
    book["bbox_lt_2_pages"] = sum(int(row["bbox_lt_2"]) for row in page_rows)
    book["empty_text_box_total"] = sum(int(row["empty_text_box_count"]) for row in page_rows)
    book["word_count_total"] = sum(int(row["word_count"]) for row in page_rows)
    book["space_ratio"] = safe_div(spaces_total, all_chars_total)
    book["english_ratio"] = safe_div(english_chars_total, language_chars_total)
    book["other_foreign_ratio"] = safe_div(other_foreign_chars_total, language_chars_total)
    book["special_char_ratio"] = safe_div(special_chars_total, all_chars_total)
    book["label_counts"] = dict(label_counter)
    return book


def _resolve_analysis_worker_count(analysis_config: AnalysisConfig, total_tasks: int) -> int:
    if total_tasks <= 1:
        return 1
    configured_max_workers = analysis_config.max_workers
    if configured_max_workers is None:
        return resolve_parallel_workers(None, total_tasks=total_tasks)
    return resolve_parallel_workers(
        {"parallel": {"max_workers": configured_max_workers}},
        total_tasks=total_tasks,
    )


def _build_page_row_from_raw(
    *,
    bucket: str,
    key: str,
    raw: bytes,
    text_label_keywords: Sequence[str],
) -> Optional[Tuple[str, dict]]:
    filename = get_filename_from_key(key)
    book_name = get_book_name_from_key(key)
    source_uri = f"s3://{bucket}/{key}"

    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        payload = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError:
        return None

    shapes = payload.get("shapes", [])
    boxes: List[Box] = []
    for shape in shapes:
        box = to_box(shape)
        if box:
            boxes.append(box)

    metrics = analyze_page(boxes=boxes, text_label_keywords=text_label_keywords)
    row = {
        "book_name": book_name,
        "file_name": filename,
        "source_uri": source_uri,
        "bucket": bucket,
        "json_key": key,
        "preview_boxes": [
            {
                "label": box.label,
                "text": box.text,
                "bbox": [box.x1, box.y1, box.x2, box.y2],
            }
            for box in boxes
        ],
        **metrics,
    }
    return book_name, row


def _process_s3_key(
    *,
    s3_client: Any,
    bucket: str,
    key: str,
    text_label_keywords: Sequence[str],
) -> Optional[Tuple[str, dict]]:
    raw = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    return _build_page_row_from_raw(
        bucket=bucket,
        key=key,
        raw=raw,
        text_label_keywords=text_label_keywords,
    )


def _is_stop_requested(stop_requested: StopRequestedCallback) -> bool:
    if stop_requested is None:
        return False
    try:
        return bool(stop_requested())
    except Exception:
        return False


def _append_result_row(
    result: Optional[Tuple[str, dict]],
    *,
    page_rows: List[dict],
    per_book_rows: Dict[str, List[dict]],
) -> None:
    if result is None:
        return
    book_name, row = result
    page_rows.append(row)
    per_book_rows[book_name].append(row)


def _consume_parallel_futures(
    *,
    futures: Sequence[concurrent.futures.Future],
    progress_desc: str,
    total: int,
    page_rows: List[dict],
    per_book_rows: Dict[str, List[dict]],
    progress_callback: ProgressCallback,
    stop_requested: StopRequestedCallback,
) -> bool:
    pending = set(futures)
    completed = 0
    stopped = False

    while pending:
        if _is_stop_requested(stop_requested):
            stopped = True
            break

        done, pending = concurrent.futures.wait(
            pending,
            timeout=0.1,
            return_when=concurrent.futures.FIRST_COMPLETED,
        )
        if not done:
            continue

        for future in done:
            completed += 1
            if not future.cancelled():
                result = future.result()
                _append_result_row(result, page_rows=page_rows, per_book_rows=per_book_rows)
            if progress_callback:
                progress_callback(progress_desc, completed, max(total, 1))

    return stopped


def run_analysis(
    *,
    s3_uri: Optional[str] = None,
    s3_config: Optional[S3Config] = None,
    analysis_config: Optional[AnalysisConfig] = None,
    progress_callback: ProgressCallback = None,
    stop_requested: StopRequestedCallback = None,
) -> Tuple[List[dict], Optional[Path], List[dict], bool]:
    if not s3_uri:
        raise ValueError("s3_uri가 필요합니다.")

    analysis_config = analysis_config or AnalysisConfig()
    text_label_keywords = list(analysis_config.text_label_keywords or TEXT_LABEL_KEYWORDS_DEFAULT)

    page_rows: List[dict] = []
    per_book_rows: Dict[str, List[dict]] = defaultdict(list)
    stopped = False

    bucket, s3, keys = collect_s3_json_keys(
        s3_uri,
        s3_config=s3_config,
        progress_callback=progress_callback,
    )
    total = len(keys)
    if progress_callback:
        progress_callback("JSON 분석", 0, max(total, 1))
    worker_count = _resolve_analysis_worker_count(analysis_config, total)
    if worker_count == 1:
        for index, key in enumerate(keys, start=1):
            if _is_stop_requested(stop_requested):
                stopped = True
                break
            result = _process_s3_key(
                s3_client=s3,
                bucket=bucket,
                key=key,
                text_label_keywords=text_label_keywords,
            )
            _append_result_row(result, page_rows=page_rows, per_book_rows=per_book_rows)
            if progress_callback:
                progress_callback("JSON 분석", index, max(total, 1))
    else:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=worker_count)
        try:
            futures = [
                executor.submit(
                    _process_s3_key,
                    s3_client=s3,
                    bucket=bucket,
                    key=key,
                    text_label_keywords=text_label_keywords,
                )
                for key in keys
            ]
            stopped = _consume_parallel_futures(
                futures=futures,
                progress_desc="JSON 분석",
                total=total,
                page_rows=page_rows,
                per_book_rows=per_book_rows,
                progress_callback=progress_callback,
                stop_requested=stop_requested,
            ) or stopped
        finally:
            executor.shutdown(wait=True)
    book_rows: List[dict] = []
    for book_name, rows in sorted(per_book_rows.items()):
        aggregate = aggregate_book(rows)
        label_counts = aggregate.pop("label_counts", {})
        book_rows.append(
            {
                "book_name": book_name,
                **aggregate,
                **{f"label_count_{label}": count for label, count in label_counts.items()},
            }
        )


    cancelled = stopped or _is_stop_requested(stop_requested)
    if cancelled:
        return book_rows, None, page_rows, True

    if progress_callback:
        progress_callback("도서 단위 집계 완료", 1, 1)

    return book_rows, None, page_rows, False
