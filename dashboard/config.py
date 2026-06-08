"""대시보드 설정 모듈."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DashboardConfig:
    """대시보드 전역 설정."""

    # ── 데이터 소스 ──────────────────────────────────────────
    # "excel" 또는 "gsheet" (환경변수 DATA_SOURCE로 변경 가능)
    data_source: str = field(
        default_factory=lambda: os.getenv("DATA_SOURCE", "gsheet")
    )

    # ── 엑셀 파일 경로 (data_source="excel"일 때 사용) ────────
    excel_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "EXCEL_PATH",
                r"C:\Users\박재현\Downloads\26pj077-a.xlsx",
            )
        )
    )

    # ── 구글 스프레드시트 설정 (data_source="gsheet"일 때 사용) ─
    gsheet_url: str = field(
        default_factory=lambda: os.getenv(
            "GSHEET_URL",
            "https://docs.google.com/spreadsheets/d/14ZqesPkXUBiCXYkYctsQysh3_qgWstzNk11_gryOLWw/edit"
        )
    )
    # Service Account JSON 경로
    gsheet_credential_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "GSHEET_CREDENTIAL",
                r"C:\Users\박재현\Documents\[프로젝트]26pj077_엘지씨엔에스\4. code\dashboard\service_account.json",
            )
        )
    )

    # ── 읽어올 시트 이름 (엑셀 / 구글시트 공통) ───────────────
    sheet_work_status: str = "3. 문서 별 작업 현황"
    sheet_doc_info: str = "2. 문서 정보"
    sheet_worker_mgmt: str = "4. 작업자 관리"

    # ── 서버 설정 ────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = True

    # ── 자동 갱신 간격 (밀리초) ───────────────────────────────
    auto_refresh_ms: int = 60_000

    # ── 작업 상태 값 정의 ────────────────────────────────────
    status_done: str = "작업 완료"
    status_in_progress: str = "진행 중"
    status_not_started: str = "미시작"
