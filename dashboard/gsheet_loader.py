"""구글 스프레드시트 데이터 로더 모듈.

gspread를 사용하여 Google Sheets에서 직접
'3. 문서 별 작업 현황' 시트를 읽어온다.

기존 data-team2-base 프로젝트의 OAuth 인증 패턴을 재사용한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from config import DashboardConfig
from data_loader import (
    DocumentRow,
    StageStats,
    WorkerStats,
    _normalize_status,
    calc_stage_stats,
    calc_worker_stats,
)


# ── 시트 헤더 → 컬럼 인덱스 매핑 ────────────────────────────
_HEADER_MAP: dict[str, str] = {
    "ID": "id",
    "작업 페이지": "pages",
    "문서 종류": "doc_type",
    "BBOX 작업": "bbox_status",
    "BBOX 작업자": "bbox_worker",
    "BBOX 검수자": "bbox_reviewer",
    "특이사항": "note",
    "OCR 작업 상태": "ocr_status",
    "OCR 작업자": "ocr_worker",
    "OCR 검수자": "ocr_reviewer",
    "수식표 작업 상태": "formula_status",
    "WER 검수 상태": "wer_status",
    "납품 전 체크리스트": "delivery_check",
    "납품 차수": "delivery_phase",
}


def _build_gspread_client(
    credential_path: Path,
) -> Any:
    """gspread Service Account 클라이언트를 생성한다 (자동화에 최적)."""
    try:
        import gspread
    except ImportError as exc:
        raise ImportError(
            "gspread 패키지가 필요합니다. `pip install gspread` 로 설치해주세요."
        ) from exc

    # Service Account 방식: 브라우저 인증 불필요, 토큰 관리 불필요
    client = gspread.service_account(filename=str(credential_path))
    return client


def _parse_header_indices(
    header_row: list[str],
) -> dict[str, int]:
    """헤더 행에서 필요한 컬럼의 인덱스를 찾는다."""
    indices: dict[str, int] = {}
    for col_idx, cell in enumerate(header_row):
        key = str(cell or "").strip()
        if key in _HEADER_MAP:
            indices[_HEADER_MAP[key]] = col_idx
    return indices


def _safe_get(row: list[str], idx: int | None) -> str | None:
    """행에서 안전하게 값을 가져온다."""
    if idx is None or idx >= len(row):
        return None
    val = str(row[idx] or "").strip()
    return val if val else None


def _safe_int(value: str | None) -> int:
    """문자열을 정수로 변환한다."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def load_documents_from_gsheet(
    config: DashboardConfig,
) -> list[DocumentRow]:
    """구글 스프레드시트에서 문서 목록을 읽어온다."""
    client = _build_gspread_client(
        credential_path=config.gsheet_credential_path,
    )

    spreadsheet = client.open_by_url(config.gsheet_url)
    worksheet = spreadsheet.worksheet(config.sheet_work_status)

    # 전체 데이터 가져오기
    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        return []

    # 헤더 파싱
    header_row = all_values[0]
    col = _parse_header_indices(header_row)

    # 데이터 행 파싱
    documents: list[DocumentRow] = []
    for row in all_values[1:]:
        doc_id = _safe_get(row, col.get("id"))
        if doc_id is None:
            continue

        documents.append(
            DocumentRow(
                doc_id=doc_id,
                pages=_safe_int(_safe_get(row, col.get("pages"))),
                doc_type=_safe_get(row, col.get("doc_type")),
                bbox_status=_normalize_status(
                    _safe_get(row, col.get("bbox_status")), config
                ),
                bbox_worker=_safe_get(row, col.get("bbox_worker")),
                bbox_reviewer=_safe_get(row, col.get("bbox_reviewer")),
                note=_safe_get(row, col.get("note")),
                ocr_status=_normalize_status(
                    _safe_get(row, col.get("ocr_status")), config
                ),
                ocr_worker=_safe_get(row, col.get("ocr_worker")),
                ocr_reviewer=_safe_get(row, col.get("ocr_reviewer")),
                formula_status=_normalize_status(
                    _safe_get(row, col.get("formula_status")), config
                ),
                wer_status=_safe_get(row, col.get("wer_status")),
                delivery_phase=_safe_get(row, col.get("delivery_phase")),
                delivery_check=_safe_get(row, col.get("delivery_check")),
            )
        )

    return documents


def build_dashboard_data_from_gsheet(
    config: DashboardConfig,
) -> dict[str, Any]:
    """구글 스프레드시트에서 대시보드 전체 데이터를 빌드한다."""
    documents = load_documents_from_gsheet(config)

    # 단계별 통계
    bbox_stats = calc_stage_stats(documents, "bbox_status", config)
    ocr_stats = calc_stage_stats(documents, "ocr_status", config)
    formula_stats = calc_stage_stats(documents, "formula_status", config)

    # 작업자별 통계
    bbox_workers = calc_worker_stats(documents, "bbox_worker", "bbox_status", config)
    ocr_workers = calc_worker_stats(documents, "ocr_worker", "ocr_status", config)

    # 납품 차수별 통계
    from data_loader import calc_delivery_phase_stats
    delivery_stats = calc_delivery_phase_stats(documents, config)

    # 전체 진척도 (3단계 평균, 페이지 기준)
    overall_rate = round(
        (
            bbox_stats.done_rate_pages
            + ocr_stats.done_rate_pages
            + formula_stats.done_rate_pages
        )
        / 3,
        1,
    )

    # 문서별 상세 데이터
    doc_details = []
    for doc in documents:
        doc_details.append(
            {
                "id": doc.doc_id,
                "pages": doc.pages,
                "doc_type": doc.doc_type or "-",
                "bbox_status": doc.bbox_status,
                "bbox_worker": doc.bbox_worker or "-",
                "ocr_status": doc.ocr_status,
                "ocr_worker": doc.ocr_worker or "-",
                "formula_status": doc.formula_status,
                "delivery_phase": doc.delivery_phase or "-",
                "note": doc.note or "",
            }
        )

    from datetime import datetime

    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "google_sheets",
        "summary": {
            "total_docs": len(documents),
            "total_pages": sum(d.pages for d in documents),
            "overall_rate": overall_rate,
        },
        "bbox": bbox_stats.to_dict(),
        "ocr": ocr_stats.to_dict(),
        "formula": formula_stats.to_dict(),
        "bbox_workers": [w.to_dict() for w in bbox_workers],
        "ocr_workers": [w.to_dict() for w in ocr_workers],
        "delivery_phases": delivery_stats,
        "documents": doc_details,
        "auto_refresh_ms": config.auto_refresh_ms,
    }
