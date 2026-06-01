from __future__ import annotations

import hashlib
from pathlib import Path
import traceback
from typing import List, Optional

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QSplitter, QVBoxLayout, QWidget

from app.common.config.parallel_settings import resolve_parallel_workers
from app.common.panel_layout import DEFAULT_THREE_PANEL_SPLITTER_SIZES
from app.common.shared_status_bar import format_progress_status
from app.common.labels.label_reference import load_label_color_map, load_label_entries
from .analysis_core import (
    AnalysisConfig,
    S3Config,
    _build_s3_client,
    find_matching_s3_image_key,
)
from .panels.center_panel import RawDataAnalysisCenterPanel
from .panels.left_panel import RawDataAnalysisLeftPanel
from .panels.right_panel import RawDataAnalysisRightPanel
from .ui_shared import (
    RESULT_HEADERS,
    book_row_to_display_cells,
    init_dynamic_headers,
    normalize_highlight_rules,
)
from .worker import AnalysisWorker

RAW_DATA_GSHEET_CREDENTIAL_FILENAME = (
    "client_secret_473195316741-t8k58asvtobhqs9a1c3ghobvd3otiml3.apps.googleusercontent.com.json"
)
RAW_DATA_GSHEET_TOKEN_RELATIVE_PATH = Path(".auth") / "gspread_oauth_user.json"

class RawDataAnalysisTabPage(QWidget):
    status_message_requested = pyqtSignal(str)
    status_progress_requested = pyqtSignal(str, int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.project_root = Path(__file__).resolve().parents[3]

        # 패널 생성 전에 xlsx 라벨을 읽어 헤더를 동적으로 초기화
        _entries = load_label_entries(self.project_root)
        if _entries:
            init_dynamic_headers(_entries)

        self._initial_splitter_sizes_applied = False
        self._initial_left_panel_minimum_width = 0
        self._shared_config: dict = {}
        self.rows: List[dict] = []
        self.page_rows: List[dict] = []
        self.worker: Optional[AnalysisWorker] = None
        self._analysis_stop_requested = False
        self.last_output_path = ""
        self.last_text_label_keywords: List[str] = ["TEXT", "CAPTION", "FOOTNOTE", "TITLE"]
        self.preview_items: List[dict] = []
        self._label_color_map = load_label_color_map(self.project_root)
        self._preview_image_cache: dict[str, str] = {}
        self._preview_cache_dir = self.project_root / ".cache" / "raw_data_preview"
        self._preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self._preview_s3_client = None
        self.highlight_rules = normalize_highlight_rules()

        self.left_panel = RawDataAnalysisLeftPanel(self.project_root)
        self.center_panel = RawDataAnalysisCenterPanel()
        self.right_panel = RawDataAnalysisRightPanel()
        self.center_panel.set_highlight_rules(self.highlight_rules)
        self.right_panel.set_highlight_rules(self.highlight_rules)

        self.left_panel.run_requested.connect(self._on_run_requested)
        self.left_panel.export_excel_requested.connect(self._on_export_excel_requested)
        self.left_panel.export_gsheet_requested.connect(self._on_export_gsheet_requested)
        self.left_panel.highlight_rules_applied.connect(self._on_highlight_rules_applied)
        self.left_panel.status_message.connect(self.set_recent_log)
        self.center_panel.cell_selected.connect(self._on_result_cell_selected)
        self.right_panel.preview_index_changed.connect(self._on_preview_index_changed)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.center_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        self._splitter = splitter

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(splitter, 1)
        QTimer.singleShot(0, self._ensure_initial_splitter_sizes)
        self._set_run_button_state(running=False)

    def apply_shared_settings(self, config: Optional[dict] = None) -> None:
        self._shared_config = dict(config or {})
        self.left_panel.apply_shared_settings(config)

    def _apply_initial_splitter_sizes(self) -> None:
        self._initial_left_panel_minimum_width = self.left_panel.minimumWidth()
        self.left_panel.setMinimumWidth(DEFAULT_THREE_PANEL_SPLITTER_SIZES[0])
        self.left_panel.setMaximumWidth(DEFAULT_THREE_PANEL_SPLITTER_SIZES[0])
        self._splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        QTimer.singleShot(0, self._release_initial_left_panel_width)

    def _release_initial_left_panel_width(self) -> None:
        self.left_panel.setMaximumWidth(16777215)
        self.left_panel.setMinimumWidth(self._initial_left_panel_minimum_width)

    def _ensure_initial_splitter_sizes(self) -> None:
        if self._initial_splitter_sizes_applied:
            return
        self._apply_initial_splitter_sizes()
        self._initial_splitter_sizes_applied = True

    def set_recent_log(self, text: str) -> None:
        message = str(text or "").strip()
        if not message:
            message = format_progress_status("대기 중", 0, 1)
        elif message.startswith("최근 작업 로그:"):
            message = message[len("최근 작업 로그:") :].strip()
        self.status_message_requested.emit(message)

    def _resolve_path(self, value: str) -> Path:
        path = Path(value.strip())
        if not path.is_absolute():
            path = (self.project_root / path).resolve()
        return path

    def _fixed_gsheet_credential_path(self) -> Path:
        return (self.project_root / "app" / "tabs" / "raw_data_analysis" / RAW_DATA_GSHEET_CREDENTIAL_FILENAME).resolve()

    def _fixed_gsheet_token_path(self) -> Path:
        return (self.project_root.parent / RAW_DATA_GSHEET_TOKEN_RELATIVE_PATH).resolve()

    def _selected_text_labels(self) -> List[str]:
        selected = self.left_panel.text_label_selector.selected_values()
        normalized: List[str] = []
        seen: set[str] = set()
        for raw_value in selected:
            value = str(raw_value or "").strip()
            if not value:
                continue
            label_id = value
            if value.endswith(")") and "(" in value:
                candidate = value.rsplit("(", 1)[-1].rstrip(")").strip()
                if candidate:
                    label_id = candidate
            label_id = label_id.upper()
            if label_id and label_id not in seen:
                seen.add(label_id)
                normalized.append(label_id)
        return normalized or ["TEXT", "CAPTION", "FOOTNOTE", "TITLE"]

    def _validate_inputs(self) -> bool:
        if not self.left_panel.s3_uri_input.text().strip():
            QMessageBox.warning(self, "입력 확인", "상단 설정에서 S3 URL을 먼저 입력해주세요.")
            return False

        if not self.left_panel.output_dir_input.text().strip():
            QMessageBox.warning(self, "입력 확인", "결과를 저장할 출력 폴더를 입력해주세요.")
            return False
        return True

    def _format_progress_text(self, desc: str, current: int, total: int) -> str:
        safe_total = max(int(total or 0), 1)
        safe_current = max(0, min(int(current or 0), safe_total))
        return f"최근 작업 로그: {format_progress_status(desc, safe_current, safe_total)}"

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self.left_panel.export_excel_btn.setEnabled(enabled)
        self.left_panel.export_gsheet_btn.setEnabled(enabled)

    def _set_run_button_state(self, *, running: bool, stop_requested: bool = False) -> None:
        if running:
            if stop_requested:
                self.left_panel.run_btn.setText("중지 요청중...")
                self.left_panel.run_btn.setEnabled(False)
            else:
                self.left_panel.run_btn.setText("중지")
                self.left_panel.run_btn.setEnabled(True)
            return

        self.left_panel.run_btn.setText("분석 실행")
        self.left_panel.run_btn.setEnabled(True)

    def _release_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self._analysis_stop_requested = False
        self._set_run_button_state(running=False)

    def _label_aliases_for_header(self, header: str) -> List[str]:
        # 동적: xlsx에서 로드된 라벨 엔트리 사용
        from .ui_shared import _label_entries as _entries
        for entry in _entries:
            if entry["title"] == header:
                return [entry["id"]]

        # 폴백: 기존 하드코딩 (xlsx 없을 때)
        mapping = {
            "텍스트": ["TEXT"],
            "타이틀": ["TITLE"],
            "캡션": ["CAPTION"],
            "이미지": ["IMAGE"],
            "수식": ["LATEX", "EQUATION", "FORMULA", "MATH"],
            "표": ["TABLE"],
            "차트": ["CHART"],
            "각주": ["FOOTNOTE"],
            "아이템": ["ITEM"],
        }
        return mapping.get(header, [])

    def _make_viewer_boxes(self, all_boxes: List[dict], emphasized_boxes: Optional[List[dict]] = None) -> List[dict]:
        viewer_boxes: List[dict] = []
        emphasized_ids = {
            (
                tuple(box.get("bbox", []) or []),
                str(box.get("label", "")).strip().upper(),
                str(box.get("text", "") or ""),
            )
            for box in (emphasized_boxes or [])
        }
        for box in all_boxes:
            bbox = box.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            label = str(box.get("label", "")).strip().upper()
            box_key = (tuple(bbox), label, str(box.get("text", "") or ""))
            viewer_boxes.append(
                {
                    "bbox": bbox,
                    "severity": "WARN",
                    "color": self._label_color_map.get(label, "#2563eb"),
                    "label": label,
                    "tone_down": bool(emphasized_ids) and box_key not in emphasized_ids,
                }
            )
        return viewer_boxes

    def _metric_value_for_page(self, header: str, page_row: dict) -> float:
        if header == "띄어쓰기":
            return float(page_row.get("space_ratio", 0.0) or 0.0)
        if header == "영어":
            return float(page_row.get("english_ratio", 0.0) or 0.0)
        if header == "기타 외국어":
            return float(page_row.get("other_foreign_ratio", 0.0) or 0.0)
        if header == "특수문자":
            return float(page_row.get("special_char_ratio", 0.0) or 0.0)
        if header == "어절":
            return float(page_row.get("word_count", 0.0) or 0.0)
        if header == "빈 텍스트 박스":
            return float(page_row.get("empty_text_box_count", 0.0) or 0.0)
        if header == "박스(<2)":
            return float(page_row.get("bbox_lt_2", 0.0) or 0.0)
        if header == "다단 의심":
            return float(1 if page_row.get("multicolumn_suspected") else 0)

        aliases = self._label_aliases_for_header(header)
        if aliases:
            label_counts = page_row.get("label_counts", {}) or {}
            return float(sum(int(label_counts.get(alias, 0) or 0) for alias in aliases))
        return 0.0

    def _metric_text_for_page(self, header: str, page_row: dict) -> str:
        value = self._metric_value_for_page(header, page_row)
        if header in {"띄어쓰기", "영어", "기타 외국어", "특수문자"}:
            return f"{header}: {value:.4f}"
        return f"{header}: {int(value) if float(value).is_integer() else value}"

    def _relevant_boxes_for_page(self, header: str, page_row: dict) -> List[dict]:
        preview_boxes = list(page_row.get("preview_boxes", []) or [])
        aliases = set(self._label_aliases_for_header(header))
        if aliases:
            return [box for box in preview_boxes if str(box.get("label", "")).upper() in aliases]
        if header in {"띄어쓰기", "영어", "기타 외국어", "특수문자", "어절"}:
            target_labels = {label.upper() for label in self.last_text_label_keywords}
            return [box for box in preview_boxes if str(box.get("label", "")).upper() in target_labels]
        if header == "빈 텍스트 박스":
            target_labels = {label.upper() for label in self.last_text_label_keywords}
            return [
                box
                for box in preview_boxes
                if str(box.get("label", "")).upper() in target_labels and not str(box.get("text", "")).strip()
            ]
        if header in {"박스(<2)", "다단 의심"}:
            return preview_boxes
        return []

    def _candidate_pages_for_header(self, header: str, book_name: str) -> List[dict]:
        pages = [row for row in self.page_rows if str(row.get("book_name", "")) == book_name]
        if not pages:
            return []

        if header == "ID":
            return sorted(pages, key=lambda row: str(row.get("file_name", "")))

        candidates = [row for row in pages if self._metric_value_for_page(header, row) > 0]
        if header in {"띄어쓰기", "영어", "기타 외국어", "특수문자", "어절"}:
            candidates = pages

        return sorted(
            candidates,
            key=lambda row: (self._metric_value_for_page(header, row), str(row.get("file_name", ""))),
            reverse=True,
        )

    def _build_preview_items_for_cell(self, row_index: int, col_index: int) -> tuple[str, str, List[dict]]:
        if not (0 <= row_index < len(self.rows)) or not (0 <= col_index < len(RESULT_HEADERS)):
            return "", "", []

        row = self.rows[row_index]
        book_name = str(row.get("book_name", "") or "")
        header = RESULT_HEADERS[col_index]
        preview_items: List[dict] = []
        for page_row in self._candidate_pages_for_header(header, book_name):
            all_boxes = list(page_row.get("preview_boxes", []) or [])
            relevant_boxes = self._relevant_boxes_for_page(header, page_row)
            preview_items.append(
                {
                    "book_name": book_name,
                    "header": header,
                    "file_name": str(page_row.get("file_name", "") or ""),
                    "metric_text": self._metric_text_for_page(header, page_row),
                    "bucket": str(page_row.get("bucket", "") or ""),
                    "json_key": str(page_row.get("json_key", "") or ""),
                    "viewer_boxes": self._make_viewer_boxes(all_boxes, relevant_boxes),
                    "label_summary": ", ".join(sorted({str(box.get("label", "")).upper() for box in relevant_boxes})) or header,
                }
            )
        return book_name, header, preview_items

    def _get_preview_s3_client(self):
        if self._preview_s3_client is None:
            self._preview_s3_client = _build_s3_client(
                S3Config(
                    access_key_id=self.left_panel.aws_access_key_input.text().strip(),
                    secret_access_key=self.left_panel.aws_secret_key_input.text().strip(),
                    region_name=self.left_panel.aws_region_input.text().strip(),
                )
            )
        return self._preview_s3_client

    def _resolve_preview_image_path(self, preview_item: dict) -> str:
        bucket = str(preview_item.get("bucket", "") or "").strip()
        json_key = str(preview_item.get("json_key", "") or "").strip()
        if not bucket or not json_key:
            return ""

        cache_key = f"{bucket}|{json_key}"
        cached = self._preview_image_cache.get(cache_key, "")
        if cached and Path(cached).exists():
            return cached

        try:
            client = self._get_preview_s3_client()
            image_key = str(preview_item.get("image_key", "") or "").strip()
            if not image_key:
                image_key = find_matching_s3_image_key(client, bucket, json_key)
                preview_item["image_key"] = image_key
            if not image_key:
                return ""

            suffix = Path(image_key).suffix.lower() or ".png"
            local_path = self._preview_cache_dir / f"{hashlib.md5(image_key.encode('utf-8')).hexdigest()}{suffix}"
            if not local_path.exists():
                client.download_file(bucket, image_key, str(local_path))
            self._preview_image_cache[cache_key] = str(local_path)
            return str(local_path)
        except Exception as exc:
            self.set_recent_log(f"미리보기 이미지 로드 실패: {exc}")
            return ""

    def _show_preview_item(self, preview_item: dict) -> None:
        image_path = self._resolve_preview_image_path(preview_item)
        title = f"{preview_item.get('book_name', '')} · {preview_item.get('file_name', '')}"
        meta_text = (
            f"{preview_item.get('header', '')} | {preview_item.get('metric_text', '')} | "
            f"라벨: {preview_item.get('label_summary', '')}"
        )
        empty_message = "매칭되는 이미지가 없습니다." if not image_path else "이미지 없음"
        self.right_panel.show_preview_page(
            image_path=image_path,
            bboxes=list(preview_item.get("viewer_boxes", []) or []),
            title=title,
            meta_text=meta_text,
            empty_message=empty_message,
        )
        current_index = self.right_panel.preview_index + 1 if self.right_panel.preview_index >= 0 else 0
        total = len(self.preview_items)
        self.set_recent_log(
            f"최근 작업 로그: {format_progress_status('미리보기', current_index, max(total, 1))} | {title}"
        )

    def _on_result_cell_selected(self, row_index: int, col_index: int) -> None:
        book_name, header, preview_items = self._build_preview_items_for_cell(row_index, col_index)
        self.preview_items = preview_items
        if not preview_items:
            title = f"{book_name} · {header}" if book_name else header
            meta_text = "선택한 셀에 해당하는 페이지가 없습니다."
            empty_message = "이미지 없음"
            self.right_panel.set_preview_placeholder(
                title=title or "페이지 미리보기",
                meta_text=meta_text,
                empty_message=empty_message,
            )
            return
        self.right_panel.set_preview_items(preview_items, book_name=book_name, header=header)

    def _on_preview_index_changed(self, index: int) -> None:
        if not (0 <= index < len(self.preview_items)):
            return
        self._show_preview_item(self.preview_items[index])

    def _on_highlight_rules_applied(self, rules: dict) -> None:
        self.highlight_rules = normalize_highlight_rules(rules)
        self.center_panel.set_highlight_rules(self.highlight_rules)
        self.right_panel.set_highlight_rules(self.highlight_rules)
        self.center_panel.set_rows([book_row_to_display_cells(row) for row in self.rows])
        self.right_panel.set_stats_rows(self.rows)

    def _on_run_requested(self) -> None:
        self.setFocus(Qt.OtherFocusReason)
        if self.worker is not None and self.worker.isRunning():
            if self._analysis_stop_requested:
                return
            try:
                self.worker.request_stop()
                self._analysis_stop_requested = True
                self._set_run_button_state(running=True, stop_requested=True)
                self.set_recent_log("최근 작업 로그: 분석 중지 요청됨 - 진행 중인 작업 정리 후 멈춥니다.")
            except Exception as exc:
                self.set_recent_log(f"최근 작업 로그: 분석 중지 요청 실패 - {exc}")
            return

        if not self._validate_inputs():
            return
        self.highlight_rules = self.left_panel.current_highlight_rules()
        self.center_panel.set_highlight_rules(self.highlight_rules)
        self.right_panel.set_highlight_rules(self.highlight_rules)

        output_dir = self._resolve_path(self.left_panel.output_dir_input.text().strip())
        output_dir.mkdir(parents=True, exist_ok=True)

        self.rows = []
        self.page_rows = []
        self.last_output_path = ""
        self.preview_items = []
        self.last_text_label_keywords = self._selected_text_labels()
        self._analysis_stop_requested = False
        self._preview_s3_client = None
        self.center_panel.set_rows([])
        self.right_panel.set_preview_placeholder(
            title="페이지 미리보기",
            meta_text="셀을 선택하면 관련 페이지를 확인할 수 있습니다.",
            empty_message="이미지 없음",
        )
        self.right_panel.set_stats_rows([])
        self._set_run_button_state(running=True)
        self._set_export_buttons_enabled(False)

        worker = AnalysisWorker(
            s3_uri=self.left_panel.s3_uri_input.text().strip(),
            s3_config=S3Config(
                access_key_id=self.left_panel.aws_access_key_input.text().strip(),
                secret_access_key=self.left_panel.aws_secret_key_input.text().strip(),
                region_name=self.left_panel.aws_region_input.text().strip(),
            ),
            analysis_config=AnalysisConfig(
                text_label_keywords=self.last_text_label_keywords,
                max_workers=resolve_parallel_workers(self._shared_config),
            ),
        )
        worker.progress.connect(self._on_analysis_progress)
        worker.finished_ok.connect(self._on_analysis_finished)
        worker.failed.connect(self._on_analysis_failed)
        self.worker = worker

        self.set_recent_log(self._format_progress_text("원시 데이터 분석 준비", 0, 1))
        self.worker.start()

    def _on_analysis_progress(self, desc: str, current: int, total: int) -> None:
        self.status_progress_requested.emit(desc, current, total)

    def _on_analysis_finished(self, rows: list, output_path: str, page_rows: list, cancelled: bool) -> None:
        del output_path
        self._analysis_stop_requested = False
        self.rows = list(rows)
        self.page_rows = list(page_rows)
        self.last_output_path = ""
        self.center_panel.set_rows([book_row_to_display_cells(row) for row in self.rows])
        self.preview_items = []
        self.right_panel.set_preview_placeholder(
            title="페이지 미리보기",
            meta_text="셀을 선택하면 관련 페이지를 확인할 수 있습니다.",
            empty_message="이미지 없음",
        )
        self.right_panel.set_stats_rows(self.rows)
        if cancelled:
            if self.rows:
                self.set_recent_log(
                    f"최근 작업 로그: {format_progress_status('분석 중지', len(self.rows), max(len(self.rows), 1))} | 중지된 실행은 파일을 저장하지 않습니다."
                )
            else:
                self.set_recent_log(
                    f"최근 작업 로그: {format_progress_status('분석 중지', 1, 1)} | 반영된 결과 없음"
                )
            self._release_worker()
            return
        self._set_export_buttons_enabled(bool(self.rows))
        if self.rows:
            self.set_recent_log(
                f"최근 작업 로그: {format_progress_status('분석 완료', len(self.rows), len(self.rows))} | 저장 대기 (엑셀로 저장하기 버튼)"
            )
        else:
            self.set_recent_log(f"최근 작업 로그: {format_progress_status('분석 완료', 1, 1)} | 결과 없음")
        self._release_worker()

    def _on_analysis_failed(self, detail: str) -> None:
        self._analysis_stop_requested = False
        self._set_export_buttons_enabled(False)
        self.page_rows = []
        self.preview_items = []
        self.right_panel.set_preview_placeholder(
            title="페이지 미리보기",
            meta_text="셀을 선택하면 관련 페이지를 확인할 수 있습니다.",
            empty_message="이미지 없음",
        )
        self.right_panel.set_stats_rows([])
        self._release_worker()
        self.set_recent_log(f"최근 작업 로그: {format_progress_status('분석 실패', 0, 1)}")
        QMessageBox.critical(
            self,
            "원시 데이터 분석 실패",
            "분석 중 오류가 발생했습니다.\n\n" + detail,
        )

    def _on_export_excel_requested(self) -> None:
        if not self.rows:
            QMessageBox.information(self, "엑셀 저장", "저장할 분석 결과가 없습니다.")
            return

        try:
            from openpyxl import Workbook
        except Exception:
            QMessageBox.warning(
                self,
                "엑셀 저장",
                "엑셀 저장을 위해 `openpyxl` 패키지가 필요합니다.",
            )
            return

        default_dir = self._resolve_path(self.left_panel.output_dir_input.text().strip())
        default_dir.mkdir(parents=True, exist_ok=True)
        save_path = str((default_dir / "book_metrics.xlsx").resolve())

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "book_metrics"
        worksheet.append(RESULT_HEADERS)
        for row in self.rows:
            worksheet.append(book_row_to_display_cells(row))
        workbook.save(save_path)
        self.last_output_path = save_path
        self.set_recent_log(
            f"최근 작업 로그: {format_progress_status('엑셀 저장 완료', 1, 1)} | 저장 위치: {save_path}"
        )

    def _normalize_sheet_key(self, value: object) -> str:
        return str(value or "").strip().casefold()

    def _find_sheet_header_row(
        self,
        all_values: Sequence[Sequence[object]],
        *,
        max_scan_rows: int = 5,
    ) -> tuple[int, Sequence[object]]:
        scan_limit = min(len(all_values), max_scan_rows)
        for row_offset in range(scan_limit):
            header_row = all_values[row_offset]
            normalized_headers = {
                self._normalize_sheet_key(cell)
                for cell in header_row
                if self._normalize_sheet_key(cell)
            }
            if self._normalize_sheet_key("ID") in normalized_headers:
                return row_offset + 1, header_row
        raise ValueError("시트 상단 5행 안에서 'ID' 헤더를 찾지 못했습니다.")

    def _update_google_sheet_rows(
        self,
        worksheet,
        rows: Sequence[Sequence[object]],
    ) -> tuple[int, int, int]:
        from gspread.utils import rowcol_to_a1

        all_values = worksheet.get_all_values()
        if not all_values:
            raise ValueError("대상 시트가 비어 있습니다.")

        header_row_idx, header_row = self._find_sheet_header_row(all_values)
        header_index_by_key = {
            self._normalize_sheet_key(header): index + 1
            for index, header in enumerate(header_row)
            if self._normalize_sheet_key(header)
        }
        id_col = header_index_by_key.get(self._normalize_sheet_key("ID"))
        if id_col is None:
            raise ValueError("대상 시트에서 'ID' 열을 찾지 못했습니다.")

        row_index_by_id: dict[str, int] = {}
        for row_index, sheet_row in enumerate(all_values[header_row_idx:], start=header_row_idx + 1):
            cell_value = sheet_row[id_col - 1] if id_col - 1 < len(sheet_row) else ""
            row_id = str(cell_value).strip()
            if row_id and row_id not in row_index_by_id:
                row_index_by_id[row_id] = row_index

        normalized_headers = [self._normalize_sheet_key(header) for header in RESULT_HEADERS]
        updates: list[dict[str, object]] = []
        updated_row_count = 0
        skipped_missing_id_count = 0
        skipped_missing_column_count = 0

        for row in rows:
            if not row:
                continue
            row_id = str(row[0] or "").strip()
            sheet_row_index = row_index_by_id.get(row_id)
            if not row_id or sheet_row_index is None:
                skipped_missing_id_count += 1
                continue

            row_had_update = False
            for header_key, cell_value in zip(normalized_headers[1:], row[1:]):
                column_index = header_index_by_key.get(header_key)
                if column_index is None:
                    continue
                updates.append(
                    {
                        "range": rowcol_to_a1(sheet_row_index, column_index),
                        "values": [[str(cell_value or "")]],
                    }
                )
                row_had_update = True

            if row_had_update:
                updated_row_count += 1
            else:
                skipped_missing_column_count += 1

        if updates:
            worksheet.batch_update(updates, value_input_option="RAW")
        return updated_row_count, skipped_missing_id_count, skipped_missing_column_count

    def _on_export_gsheet_requested(self) -> None:
        if not self.rows:
            QMessageBox.information(self, "구글 스프레드시트 입력", "업로드할 분석 결과가 없습니다.")
            return

        try:
            import gspread
        except Exception:
            QMessageBox.warning(
                self,
                "구글 스프레드시트 입력",
                "`gspread` 패키지가 설치되어 있어야 합니다.",
            )
            return

        credential_path = self._fixed_gsheet_credential_path()
        token_path = self._fixed_gsheet_token_path()
        sheet_url = self.left_panel.gsheet_url_input.text().strip()
        tab_name = self.left_panel.gsheet_tab_input.text().strip() or "2. 검수 요약"

        if not sheet_url:
            QMessageBox.warning(self, "입력 확인", "구글 스프레드시트 URL을 입력해주세요.")
            return

        if not credential_path.exists():
            QMessageBox.warning(self, "입력 확인", f"고정 OAuth JSON 파일을 찾을 수 없습니다.\n{credential_path}")
            return

        result_rows = [book_row_to_display_cells(row) for row in self.rows]

        try:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            client = gspread.oauth(
                credentials_filename=str(credential_path),
                authorized_user_filename=str(token_path),
            )
            spreadsheet = client.open_by_url(sheet_url)
            worksheet = spreadsheet.worksheet(tab_name)
            updated_count, missing_id_count, missing_column_count = self._update_google_sheet_rows(
                worksheet,
                result_rows,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "구글 스프레드시트 입력 실패",
                "".join(traceback.format_exception(exc)),
            )
            return

        self.set_recent_log(
            f"최근 작업 로그: {format_progress_status('구글 스프레드시트 입력 완료', 1, 1)} | "
            f"업데이트 {updated_count}건, ID 없음 {missing_id_count}건, 열 없음 {missing_column_count}건"
        )
