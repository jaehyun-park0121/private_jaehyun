from __future__ import annotations

import json
import logging
import re
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# Field state constants
OPTIONAL = 0
REQUIRED = 1
REQUIRED_NONEMPTY = 2


def validate_output_root(
    output_root: Path,
    field_states: dict[str, int],
    field_validation_enabled: bool,
    tag_count_check: bool,
) -> int:
    """output_root 아래 모든 문서를 검증한다. 반환값은 exit code."""
    doc_dirs = sorted(p for p in output_root.iterdir() if p.is_dir())
    if not doc_dirs:
        LOGGER.warning("[검증] 검증할 문서 폴더가 없습니다: %s", output_root)
        return 0

    has_error = False
    for doc_dir in doc_dirs:
        work_id = doc_dir.name
        json_path = doc_dir / f"{work_id}.json"
        if not json_path.exists():
            LOGGER.warning("[검증][%s] 결과 JSON 없음: %s", work_id, json_path)
            has_error = True
            continue

        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.error("[검증][%s] JSON 파싱 실패: %s", work_id, exc)
            has_error = True
            continue

        errors = _validate_document(
            work_id,
            doc,
            field_states,
            field_validation_enabled,
            tag_count_check,
        )
        if errors:
            has_error = True
            for msg in errors:
                LOGGER.warning("%s", msg)

    if has_error:
        LOGGER.info("[검증] 완료 — 오류가 있습니다.")
        return 1
    LOGGER.info("[검증] 완료 — 오류 없음.")
    return 0


def _validate_document(
    work_id: str,
    doc: dict,
    field_states: dict[str, int],
    field_validation_enabled: bool,
    tag_count_check: bool,
) -> list[str]:
    errors: list[str] = []
    prefix = f"[검증][{work_id}]"

    contents = doc.get("contents")

    if field_validation_enabled:
        # ── 문서 레벨 단순 필드 ──
        for field in (
            "work_id", "title", "source_format",
            "category_1", "category_2", "category_3",
            "author", "publisher", "published_date",
        ):
            errors.extend(_check_field(prefix, doc, field, field_states.get(field, OPTIONAL)))

        # identifiers.isbn
        id_state = field_states.get("identifiers.isbn", OPTIONAL)
        if id_state >= REQUIRED:
            identifiers = doc.get("identifiers")
            if not isinstance(identifiers, dict):
                errors.append(f"{prefix} identifiers 필드가 없거나 올바르지 않습니다.")
            else:
                errors.extend(_check_field(
                    f"{prefix}[identifiers]", identifiers, "isbn", id_state
                ))

        # contents 배열 자체
        contents_state = field_states.get("contents", OPTIONAL)
        if contents_state >= REQUIRED:
            if not isinstance(contents, list):
                errors.append(f"{prefix} contents 필드가 없거나 list가 아닙니다.")
            elif contents_state == REQUIRED_NONEMPTY and len(contents) == 0:
                errors.append(f"{prefix} contents가 비어 있습니다.")

    if not isinstance(contents, list):
        return errors

    # ── 페이지 레벨 ──
    for idx, page_item in enumerate(contents):
        if not isinstance(page_item, dict):
            errors.append(f"{prefix} contents[{idx}]가 객체가 아닙니다.")
            continue

        page_label = page_item.get("page", str(idx))
        pg_prefix = f"{prefix}[page={page_label}]"

        if field_validation_enabled:
            for field in ("page", "chapter", "page_contents"):
                errors.extend(_check_field(
                    pg_prefix, page_item, field,
                    field_states.get(f"contents[].{field}", OPTIONAL),
                ))

        # add_info 배열 자체
        add_info = page_item.get("add_info")
        if field_validation_enabled:
            ai_arr_state = field_states.get("contents[].add_info", OPTIONAL)
            if ai_arr_state >= REQUIRED:
                if not isinstance(add_info, list):
                    errors.append(f"{pg_prefix} add_info 필드가 없거나 list가 아닙니다.")
                elif ai_arr_state == REQUIRED_NONEMPTY and len(add_info) == 0:
                    errors.append(f"{pg_prefix} add_info가 비어 있습니다.")

        if not isinstance(add_info, list):
            if tag_count_check:
                errors.extend(_check_tag_counts(work_id, page_item, page_label))
            continue

        # ── 태그 레벨 ──
        if field_validation_enabled:
            for ai_idx, ai_item in enumerate(add_info):
                if not isinstance(ai_item, dict):
                    continue
                ai_tag = ai_item.get("tag", str(ai_idx))
                ai_prefix = f"{pg_prefix}[tag={ai_tag}]"

                for field in ("tag", "type", "caption", "file_path"):
                    errors.extend(_check_field(
                        ai_prefix, ai_item, field,
                        field_states.get(f"contents[].add_info[].{field}", OPTIONAL),
                    ))

                desc_state = field_states.get(
                    "contents[].add_info[].description.value", OPTIONAL
                )
                if desc_state >= REQUIRED:
                    description = ai_item.get("description")
                    if not isinstance(description, dict):
                        errors.append(f"{ai_prefix} description 필드가 없습니다.")
                    else:
                        errors.extend(_check_field(
                            f"{ai_prefix}[description]", description, "value", desc_state
                        ))

        if tag_count_check:
            errors.extend(_check_tag_counts(work_id, page_item, page_label))

    return errors


def _check_field(prefix: str, obj: dict, field: str, state: int) -> list[str]:
    if state == OPTIONAL:
        return []
    value = obj.get(field)
    if value is None:
        return [f"{prefix} 필수 필드 누락: {field}"]
    if state == REQUIRED_NONEMPTY and value in ("", [], {}):
        return [f"{prefix} 빈 값 비허용 필드가 비어 있음: {field}"]
    return []


def _check_tag_counts(
    work_id: str, page_item: dict, page_label: object
) -> list[str]:
    """page_contents + description.value 의 태그 참조와 add_info 태그 목록을 대조한다."""
    errors: list[str] = []
    page_contents = page_item.get("page_contents", "")
    add_info = page_item.get("add_info", [])

    if not isinstance(page_contents, str) or not isinstance(add_info, list):
        return errors

    # page_contents 에서 {tag} 수집
    ref_tags: set[str] = set(_normalize_tag(t) for t in re.findall(r"\{([^{}]+)\}", page_contents))

    # add_info[].description.value 에서 {tag} 수집
    for ai in add_info:
        if not isinstance(ai, dict):
            continue
        desc = ai.get("description", {})
        if isinstance(desc, dict):
            val = desc.get("value", "")
            if isinstance(val, str):
                ref_tags.update(
                    _normalize_tag(t) for t in re.findall(r"\{([^{}]+)\}", val)
                )

    # add_info 의 tag 값 수집
    ai_tags: set[str] = set()
    for ai in add_info:
        if isinstance(ai, dict):
            raw = ai.get("tag", "")
            normalized = _normalize_tag(str(raw))
            if normalized:
                ai_tags.add(normalized)

    missing_in_ai = ref_tags - ai_tags
    orphan_in_ai = ai_tags - ref_tags

    snippet = _text_snippet(page_contents)
    context = f"[검증] 도서={work_id}, 페이지={page_label}, 본문 일부='{snippet}'"
    if missing_in_ai:
        errors.append(
            f"{context} | 본문에 참조됐지만 add_info에 없는 태그: {sorted(missing_in_ai)}"
        )
    if orphan_in_ai:
        errors.append(
            f"{context} | add_info에 있지만 본문에 참조되지 않은 태그: {sorted(orphan_in_ai)}"
        )
    return errors


def _normalize_tag(tag: str) -> str:
    return tag.strip("{}").strip()


def _text_snippet(text: str, limit: int = 80) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"
