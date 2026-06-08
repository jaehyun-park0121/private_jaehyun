"""엑셀 데이터 로더 모듈.

26pj077-a.xlsx의 '3. 문서 별 작업 현황' 시트를 읽어
대시보드에 필요한 데이터를 가공한다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from config import DashboardConfig


# ── 컬럼 인덱스 매핑 (0-based) ──────────────────────────────
class Col:
    """시트 컬럼 인덱스 상수."""
    ID = 0           # A: 문서 ID
    PAGES = 1        # B: 작업 페이지
    DOC_TYPE = 2     # C: 문서 종류
    EXTRACT = 3      # D: 추출 방식
    BBOX_STATUS = 4  # E: BBOX 작업 상태
    BBOX_WORKER = 5  # F: BBOX 작업자
    BBOX_REVIEWER = 6  # G: BBOX 검수자
    NOTE = 7         # H: 특이사항
    OCR_DIST = 8     # I: OCR 분배
    OCR_DONE = 9     # J: OCR 완료
    OCR_WORKER = 10  # K: OCR 작업자
    OCR_STATUS = 11  # L: OCR 작업 상태
    OCR_REVIEWER = 12  # M: OCR 검수자
    FORMULA_DIST = 13  # N: 수식표 분배
    FORMULA_DONE = 14  # O: 수식표 완료
    FORMULA_STATUS = 15  # P: 수식표 작업 상태
    FINAL_FOLDER = 16   # Q: 최종 폴더
    SORT_CHECK = 17     # R: 정렬 검사
    FINAL_REVIEWER = 18  # S: 최종 검수자
    WER_STATUS = 19      # T: WER 검수 상태
    WER_REVIEWER = 20    # U: WER 검수자
    WER_RESULT = 21      # V: WER 검수 결과
    DELIVERY_CHECK = 22  # W: 납품 전 체크리스트
    DELIVERY_PHASE = 23  # X: 납품 차수
    REMARK = 24          # Y: 비고


@dataclass
class DocumentRow:
    """문서 한 행의 데이터."""
    doc_id: str
    pages: int
    doc_type: str | None
    bbox_status: str
    bbox_worker: str | None
    bbox_reviewer: str | None
    note: str | None
    ocr_status: str
    ocr_worker: str | None
    ocr_reviewer: str | None
    formula_status: str
    wer_status: str | None
    delivery_phase: str | None
    delivery_check: str | None = None


@dataclass
class StageStats:
    """작업 단계별 통계."""
    total_docs: int = 0
    done_docs: int = 0
    in_progress_docs: int = 0
    not_started_docs: int = 0
    total_pages: int = 0
    done_pages: int = 0
    in_progress_pages: int = 0
    not_started_pages: int = 0

    @property
    def done_rate_docs(self) -> float:
        """문서 기준 완료율 (%)."""
        return (self.done_docs / self.total_docs * 100) if self.total_docs else 0.0

    @property
    def done_rate_pages(self) -> float:
        """페이지 기준 완료율 (%)."""
        return (self.done_pages / self.total_pages * 100) if self.total_pages else 0.0

    @property
    def in_progress_rate_docs(self) -> float:
        return (self.in_progress_docs / self.total_docs * 100) if self.total_docs else 0.0

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화용 딕셔너리 변환."""
        return {
            "total_docs": self.total_docs,
            "done_docs": self.done_docs,
            "in_progress_docs": self.in_progress_docs,
            "not_started_docs": self.not_started_docs,
            "total_pages": self.total_pages,
            "done_pages": self.done_pages,
            "in_progress_pages": self.in_progress_pages,
            "not_started_pages": self.not_started_pages,
            "done_rate_docs": round(self.done_rate_docs, 1),
            "done_rate_pages": round(self.done_rate_pages, 1),
            "in_progress_rate_docs": round(self.in_progress_rate_docs, 1),
        }


@dataclass
class WorkerStats:
    """작업자별 통계."""
    name: str
    assigned_docs: int = 0
    done_docs: int = 0
    assigned_pages: int = 0
    done_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "assigned_docs": self.assigned_docs,
            "done_docs": self.done_docs,
            "assigned_pages": self.assigned_pages,
            "done_pages": self.done_pages,
        }


def _normalize_status(raw_value: Any, config: DashboardConfig) -> str:
    """원시 상태 값을 표준 상태 문자열로 변환한다."""
    if raw_value is None or str(raw_value).strip() == "":
        return config.status_not_started
    val = str(raw_value).strip()
    if val == config.status_done:
        return config.status_done
    if val == config.status_in_progress:
        return config.status_in_progress
    # 알 수 없는 값은 '진행 중'으로 분류
    return config.status_in_progress


def load_documents(config: DashboardConfig | None = None) -> list[DocumentRow]:
    """엑셀에서 문서 목록을 읽어온다."""
    if config is None:
        config = DashboardConfig()

    wb = openpyxl.load_workbook(str(config.excel_path), data_only=True, read_only=True)
    ws = wb[config.sheet_work_status]

    documents: list[DocumentRow] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        doc_id = row[Col.ID]
        if doc_id is None:
            continue

        pages = int(row[Col.PAGES] or 0)
        doc = DocumentRow(
            doc_id=str(doc_id).strip(),
            pages=pages,
            doc_type=row[Col.DOC_TYPE],
            bbox_status=_normalize_status(row[Col.BBOX_STATUS], config),
            bbox_worker=row[Col.BBOX_WORKER],
            bbox_reviewer=row[Col.BBOX_REVIEWER],
            note=row[Col.NOTE],
            ocr_status=_normalize_status(row[Col.OCR_STATUS], config),
            ocr_worker=row[Col.OCR_WORKER],
            ocr_reviewer=row[Col.OCR_REVIEWER],
            formula_status=_normalize_status(row[Col.FORMULA_STATUS], config),
            wer_status=row[Col.WER_STATUS],
            delivery_phase=row[Col.DELIVERY_PHASE],
            delivery_check=str(row[Col.DELIVERY_CHECK]).strip() if row[Col.DELIVERY_CHECK] else None,
        )
        documents.append(doc)

    wb.close()
    return documents


def calc_stage_stats(
    documents: list[DocumentRow],
    status_getter: str,
    config: DashboardConfig | None = None,
) -> StageStats:
    """특정 단계의 통계를 계산한다.

    Args:
        documents: 문서 목록
        status_getter: DocumentRow의 상태 필드명 (bbox_status, ocr_status, formula_status)
        config: 설정 객체
    """
    if config is None:
        config = DashboardConfig()

    stats = StageStats()
    for doc in documents:
        status = getattr(doc, status_getter)
        stats.total_docs += 1
        stats.total_pages += doc.pages

        if status == config.status_done:
            stats.done_docs += 1
            stats.done_pages += doc.pages
        elif status == config.status_in_progress:
            stats.in_progress_docs += 1
            stats.in_progress_pages += doc.pages
        else:
            stats.not_started_docs += 1
            stats.not_started_pages += doc.pages

    return stats


def calc_worker_stats(
    documents: list[DocumentRow],
    worker_field: str,
    status_field: str,
    config: DashboardConfig | None = None,
) -> list[WorkerStats]:
    """작업자별 통계를 계산한다."""
    if config is None:
        config = DashboardConfig()

    workers: dict[str, WorkerStats] = {}
    for doc in documents:
        worker = getattr(doc, worker_field)
        if worker is None:
            continue
        worker = str(worker).strip()
        if worker not in workers:
            workers[worker] = WorkerStats(name=worker)

        w = workers[worker]
        w.assigned_docs += 1
        w.assigned_pages += doc.pages

        status = getattr(doc, status_field)
        if status == config.status_done:
            w.done_docs += 1
            w.done_pages += doc.pages

    return sorted(workers.values(), key=lambda w: w.assigned_pages, reverse=True)


def calc_delivery_phase_stats(
    documents: list[DocumentRow],
    config: DashboardConfig | None = None,
) -> dict[str, Any]:
    """납품 차수별 진행도 통계를 계산한다.

    Returns:
        {
            "phases": [
                {
                    "phase": "1 Cycle",
                    "total_docs": 10,
                    "total_pages": 500,
                    "bbox_rate": 80.0,  # 페이지 기준
                    "ocr_rate": 60.0,
                    "formula_rate": 40.0,
                    "overall_rate": 60.0,
                    "delivery_checked": 3,
                    "delivery_total": 10,
                },
                ...
            ]
        }
    """
    if config is None:
        config = DashboardConfig()

    # 납품 차수별로 문서를 그룹핑
    phase_groups: dict[str, list[DocumentRow]] = defaultdict(list)
    for doc in documents:
        phase = str(doc.delivery_phase or "").strip()
        if not phase or phase == "-" or phase == "None":
            phase = "미지정"
        phase_groups[phase].append(doc)

    phases = []
    for phase_name, docs in sorted(phase_groups.items()):
        total_docs = len(docs)
        total_pages = sum(d.pages for d in docs)

        # 각 단계별 완료 문서 수 / 페이지 수
        bbox_done = sum(1 for d in docs if d.bbox_status == config.status_done)
        ocr_done = sum(1 for d in docs if d.ocr_status == config.status_done)
        formula_done = sum(1 for d in docs if d.formula_status == config.status_done)
        bbox_done_pages = sum(d.pages for d in docs if d.bbox_status == config.status_done)
        ocr_done_pages = sum(d.pages for d in docs if d.ocr_status == config.status_done)
        formula_done_pages = sum(d.pages for d in docs if d.formula_status == config.status_done)

        # 완료율 계산 (페이지 기준)
        bbox_rate = round(bbox_done_pages / total_pages * 100, 1) if total_pages else 0.0
        ocr_rate = round(ocr_done_pages / total_pages * 100, 1) if total_pages else 0.0
        formula_rate = round(formula_done_pages / total_pages * 100, 1) if total_pages else 0.0
        overall_rate = round((bbox_rate + ocr_rate + formula_rate) / 3, 1)

        # 납품 전 체크 완료 건수
        delivery_checked = sum(
            1 for d in docs
            if d.delivery_check and d.delivery_check not in ("", "-", "None")
        )

        phases.append({
            "phase": phase_name,
            "total_docs": total_docs,
            "total_pages": total_pages,
            "bbox_done": bbox_done,
            "ocr_done": ocr_done,
            "formula_done": formula_done,
            "bbox_done_pages": bbox_done_pages,
            "ocr_done_pages": ocr_done_pages,
            "formula_done_pages": formula_done_pages,
            "bbox_rate": bbox_rate,
            "ocr_rate": ocr_rate,
            "formula_rate": formula_rate,
            "overall_rate": overall_rate,
            "delivery_checked": delivery_checked,
            "delivery_total": total_docs,
        })

    return {"phases": phases}


def build_dashboard_data(config: DashboardConfig | None = None) -> dict[str, Any]:
    """대시보드 전체 데이터를 빌드한다."""
    if config is None:
        config = DashboardConfig()

    documents = load_documents(config)

    # 단계별 통계
    bbox_stats = calc_stage_stats(documents, "bbox_status", config)
    ocr_stats = calc_stage_stats(documents, "ocr_status", config)
    formula_stats = calc_stage_stats(documents, "formula_status", config)

    # 작업자별 통계
    bbox_workers = calc_worker_stats(documents, "bbox_worker", "bbox_status", config)
    ocr_workers = calc_worker_stats(documents, "ocr_worker", "ocr_status", config)

    # 납품 차수별 통계
    delivery_stats = calc_delivery_phase_stats(documents, config)

    # 전체 진척도 (3단계 평균, 페이지 기준)
    overall_rate = round(
        (bbox_stats.done_rate_pages + ocr_stats.done_rate_pages + formula_stats.done_rate_pages) / 3, 1
    )

    # 문서별 상세 데이터
    doc_details = []
    for doc in documents:
        doc_details.append({
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
        })

    from datetime import datetime
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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


if __name__ == "__main__":
    import json
    data = build_dashboard_data()
    print(json.dumps(data, ensure_ascii=False, indent=2))
