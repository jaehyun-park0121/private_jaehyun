from __future__ import annotations

import copy
import unicodedata
from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import QApplication, QMessageBox

from app.common.config.parallel_settings import resolve_parallel_workers
from app.tabs.text_analysis.features.base_state import is_error_base_state
from app.tabs.text_analysis.tools.registry import get_scan_tool_spec, validate_scan_tool_config
from app.tabs.text_analysis.tools.replace import (
    build_replace_detail,
    compile_pattern,
    format_replace_row_label,
    normalize_compare_payload,
    replace_text,
)

from .workers.replace_worker import TextAnalysisReplaceWorker
from .workers.scan_worker import TextAnalysisScanWorker


class TextAnalysisRunFlowMixin:
    _SCAN_WORKER_CHUNK_SIZE = 200

    def _initialize_tool_run_state(self) -> None:
        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._text_analysis_scan_worker = None
        self._text_analysis_scan_request_id = 0
        self._text_analysis_replace_worker = None
        self._text_analysis_replace_request_id = 0
        self._active_tool_id = "special_char_analysis"
        self._last_search_context: Optional[Dict[str, Any]] = None

    def _on_run_tool_clicked(self) -> None:
        replace_preview_timer = getattr(self, "_replace_preview_timer", None)
        if replace_preview_timer is not None:
            replace_preview_timer.stop()

        if self._text_analysis_is_running:
            if self._request_tool_run_stop():
                return
            self._text_analysis_stop_requested = True
            self._set_recent_log("실행 중지 요청")
            return

        if not self._text_analysis_query_ready or not self.current_label_rows:
            QMessageBox.information(
                self,
                "조회 필요",
                "도서 선택이 바뀌었거나 OCR 라벨을 아직 불러오지 않았습니다.\n먼저 [조회]를 눌러 현재 대상을 불러와 주세요.",
            )
            return

        if self._is_placeholder_data():
            self._text_analysis_is_running = True
            self._text_analysis_stop_requested = False
            self._refresh_run_button_state()
            loaded = self._load_full_label_data()
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            if not loaded:
                self._text_analysis_stop_requested = False
                return
            self.center_panel.set_books(self.current_book_rows)
            self.center_panel.set_pages(self.current_label_rows, results_only=False)
            self._refresh_dashboard()

        tool_id = self.left_panel.selected_tool_id()
        self._active_tool_id = tool_id
        if tool_id in {"special_char_analysis", "search_tool"}:
            self._run_scan_tool(tool_id)
            return
        if tool_id == "replace_tool":
            self._run_replace_tool()
            return
        if tool_id == "nfkc_normalize_tool":
            self._run_nfkc_tool()
            return

        QMessageBox.information(self, "개발 예정", "선택한 텍스트 분석 도구는 아직 개발 예정입니다.")

    def _request_tool_run_stop(self) -> bool:
        scan_worker = getattr(self, "_text_analysis_scan_worker", None)
        if scan_worker is not None:
            try:
                scan_worker.request_stop()
                self._set_recent_log("검수 도구 중지 요청됨: 진행 중인 텍스트 분석 작업을 정리 후 멈춥니다.")
                return True
            except Exception as exc:
                self._set_recent_log(f"검수 도구 중지 요청 실패: {exc}")
                return False

        replace_worker = getattr(self, "_text_analysis_replace_worker", None)
        if replace_worker is not None:
            try:
                replace_worker.request_stop()
                self._text_analysis_stop_requested = True
                self._set_recent_log("치환 중지 요청됨: 진행 중인 페이지 저장을 정리 후 멈춥니다.")
                return True
            except Exception as exc:
                self._set_recent_log(f"치환 중지 요청 실패: {exc}")
                return False
        return False

    def _build_scan_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        if tool_id == "special_char_analysis":
            config = {
                "pattern_text": self.left_panel.allowed_pattern(),
                "target_labels": list(self.left_panel.target_labels()),
            }
            error = validate_scan_tool_config(tool_id, config)
            if error:
                QMessageBox.warning(self, "패턴 오류", f"허용 문자 패턴이 올바른 정규식이 아닙니다.\n{error}")
                return None
            return config

        if tool_id == "search_tool":
            config = {
                "keyword": self.left_panel.search_keyword(),
                "use_regex": self.left_panel.search_use_regex(),
                "case_sensitive": self.left_panel.search_case_sensitive(),
            }
            keyword = str(config.get("keyword", "")).strip()
            if not keyword:
                QMessageBox.information(self, "검색어 입력 필요", "검색할 텍스트를 입력한 뒤 실행해 주세요.")
                return None
            error = validate_scan_tool_config(tool_id, config)
            if error:
                QMessageBox.warning(self, "정규식 오류", f"검색 정규식이 올바르지 않습니다.\n{error}")
                return None
            return config

        return None

    def _scan_row_inputs(self) -> List[Dict[str, Any]]:
        return [
            {
                "row_key": str(row.get("row_key", "")).strip(),
                "label": str(row.get("label", "")).strip(),
                "flags_text": str(row.get("flags_text", "") or ""),
            }
            for row in self.current_label_rows
            if str(row.get("row_key", "")).strip()
        ]

    def _run_scan_tool(self, tool_id: str) -> None:
        spec = get_scan_tool_spec(tool_id)
        if spec is None:
            QMessageBox.information(self, "개발 예정", "선택한 텍스트 분석 도구는 아직 개발 예정입니다.")
            return

        tool_config = self._build_scan_tool_config(tool_id)
        if tool_config is None:
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        row_inputs = self._scan_row_inputs()
        if not row_inputs:
            QMessageBox.information(self, "안내", "실행할 라벨 데이터가 없습니다.")
            return

        self._text_analysis_is_running = True
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()
        self._clear_replace_visual_state(clear_preview=True, clear_applied=True)

        request_id = self._text_analysis_scan_request_id + 1
        self._text_analysis_scan_request_id = request_id
        worker = TextAnalysisScanWorker(
            tool_id=tool_id,
            tool_config=tool_config,
            row_inputs=row_inputs,
            progress_desc=spec.progress_desc,
            max_workers=resolve_parallel_workers(self.config, total_tasks=len(row_inputs)),
            chunk_size=self._SCAN_WORKER_CHUNK_SIZE,
        )
        self._text_analysis_scan_worker = worker
        worker.progress.connect(
            lambda desc, current, total, rid=request_id: self._on_scan_worker_progress(rid, desc, current, total)
        )
        worker.finished_ok.connect(
            lambda patches, failures, matched_count, rid=request_id, tid=tool_id, cfg=dict(tool_config): self._on_scan_worker_finished(
                rid,
                tid,
                cfg,
                patches,
                failures,
                matched_count,
            )
        )
        worker.cancelled.connect(
            lambda patches, failures, matched_count, rid=request_id, tid=tool_id, cfg=dict(tool_config): self._on_scan_worker_cancelled(
                rid,
                tid,
                cfg,
                patches,
                failures,
                matched_count,
            )
        )
        worker.failed.connect(lambda message, rid=request_id: self._on_scan_worker_failed(rid, message))
        worker.finished.connect(lambda rid=request_id: self._on_scan_worker_cleanup(rid))
        worker.start()

    def _on_scan_worker_progress(self, request_id: int, desc: str, current: int, total: int) -> None:
        if request_id != self._text_analysis_scan_request_id:
            return
        self._set_progress(desc, current, total)

    def _apply_scan_result_patches(self, patches: List[Dict[str, Any]]) -> None:
        row_by_key = {
            str(row.get("row_key", "")).strip(): row
            for row in self.current_label_rows
            if str(row.get("row_key", "")).strip()
        }
        for item in patches:
            row_key = str(item.get("row_key", "")).strip()
            row = row_by_key.get(row_key)
            if row is None:
                continue
            patch = dict(item.get("patch", {}) or {})
            row["tool_id"] = str(patch.get("tool_id", "") or "")
            row["tool_error_type"] = str(patch.get("tool_error_type", "") or "")
            row["tool_error_detail"] = str(patch.get("tool_error_detail", "") or "")
            row["tool_error_matches"] = list(patch.get("tool_error_matches", []) or [])
            row["match_spans"] = list(patch.get("match_spans", []) or [])
            row["highlight_text"] = str(patch.get("highlight_text", "") or "")
            row["highlight_matches"] = list(patch.get("highlight_matches", []) or [])
            self._set_detail_filter_state(
                row,
                tool_id=str(patch.get("detail_filter_tool_id", "") or ""),
                values=list(patch.get("detail_filter_values", []) or []),
            )
            self._refresh_row_result_state(row)

    def _finalize_scan_run(
        self,
        *,
        tool_id: str,
        tool_config: Dict[str, Any],
        patches: List[Dict[str, Any]],
        failures: List[str],
        matched_count: int,
        cancelled: bool,
    ) -> None:
        self._apply_scan_result_patches(list(patches or []))
        self.center_panel._clear_all_filters(emit_changed=False)
        self.center_panel.set_pages(self.current_label_rows, results_only=True)
        self._refresh_dashboard()
        self._select_first_row_after_refresh(prefer_result=True)

        if tool_id == "search_tool" and not cancelled:
            self._last_search_context = {
                "pattern": str(tool_config.get("keyword", "") or ""),
                "use_regex": bool(tool_config.get("use_regex", False)),
                "case_sensitive": bool(tool_config.get("case_sensitive", False)),
            }

        if failures:
            preview = ", ".join(str(item) for item in failures[:3] if str(item).strip())
            suffix = "" if len(failures) <= 3 else " ..."
            self._set_recent_log(f"검수 도구 일부 실패 {len(failures)}건: {preview}{suffix}")

        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()

        spec = get_scan_tool_spec(tool_id)
        if cancelled:
            self._set_recent_log(f"실행 중지: {spec.display_name if spec else '텍스트 분석'} 작업을 멈췄습니다.")
            return

        if spec is None:
            self._set_recent_log(f"실행 완료: 결과 {matched_count}건")
            return

        if tool_id == "search_tool":
            keyword = str(tool_config.get("keyword", "") or "")
            self._set_recent_log(spec.completion_message.format(matched_count=matched_count, keyword=keyword))
            return
        self._set_recent_log(spec.completion_message.format(matched_count=matched_count))

    def _on_scan_worker_finished(
        self,
        request_id: int,
        tool_id: str,
        tool_config: Dict[str, Any],
        patches: List[Dict[str, Any]],
        failures: List[str],
        matched_count: int,
    ) -> None:
        if request_id != self._text_analysis_scan_request_id:
            return
        self._finalize_scan_run(
            tool_id=tool_id,
            tool_config=tool_config,
            patches=list(patches or []),
            failures=list(failures or []),
            matched_count=int(matched_count or 0),
            cancelled=False,
        )

    def _on_scan_worker_cancelled(
        self,
        request_id: int,
        tool_id: str,
        tool_config: Dict[str, Any],
        patches: List[Dict[str, Any]],
        failures: List[str],
        matched_count: int,
    ) -> None:
        if request_id != self._text_analysis_scan_request_id:
            return
        self._finalize_scan_run(
            tool_id=tool_id,
            tool_config=tool_config,
            patches=list(patches or []),
            failures=list(failures or []),
            matched_count=int(matched_count or 0),
            cancelled=True,
        )

    def _on_scan_worker_failed(self, request_id: int, message: str) -> None:
        if request_id != self._text_analysis_scan_request_id:
            return
        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()
        QMessageBox.warning(self, "텍스트 분석 실행 실패", str(message).strip() or "알 수 없는 오류")

    def _on_scan_worker_cleanup(self, request_id: int) -> None:
        if request_id != self._text_analysis_scan_request_id:
            return
        worker = self._text_analysis_scan_worker
        if worker is not None:
            worker.deleteLater()
        self._text_analysis_scan_worker = None

    def _run_replace_tool(self) -> None:
        self._text_analysis_is_running = True
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()

        context = self._build_replace_context(show_errors=True)
        if context is None:
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        visible_rows = self._visible_replace_target_rows()
        if not visible_rows:
            QMessageBox.information(
                self,
                "치환 대상 없음",
                "검색 결과와 추가 필터가 적용된 현재 중앙 결과 테이블에 치환 대상이 없습니다.",
            )
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        matched_rows: List[Dict[str, Any]] = []
        precheck_failures: List[str] = []
        total_scan_rows = len(visible_rows)
        for index, row in enumerate(visible_rows, start=1):
            if self._text_analysis_stop_requested:
                break
            self._set_progress("치환 대상 확인", index, total_scan_rows)
            QApplication.processEvents()

            current_text = self._replace_source_text_from_row(row)
            if current_text == "":
                precheck_failures.append(f"{self._format_replace_row_label(row)}: 표시값은 있지만 flags.text가 비어 있습니다.")
                continue
            replaced_text, matches, preview_segments = replace_text(
                current_text,
                context["source_text"],
                context["target_text"],
                use_regex=context["use_regex"],
                case_sensitive=context["case_sensitive"],
                regex=context["regex"],
                replacement_uses_groups=context["replacement_uses_groups"],
            )
            if matches and replaced_text != current_text:
                matched_rows.append(row)
            else:
                precheck_failures.append(f"{self._format_replace_row_label(row)}: 현재 값에서 치환 패턴이 일치하지 않습니다.")

        if self._text_analysis_stop_requested:
            self._text_analysis_is_running = False
            self._text_analysis_stop_requested = False
            self._refresh_run_button_state()
            self._set_recent_log("실행 중지: 치환 작업을 멈췄습니다.")
            return

        if not matched_rows:
            detail = "\n".join(precheck_failures[:8])
            suffix = "\n..." if len(precheck_failures) > 8 else ""
            message = "현재 화면의 결과 중 실제로 치환 가능한 flags.text 대상이 없습니다."
            if detail:
                message += f"\n\n{detail}{suffix}"
            QMessageBox.information(self, "치환 대상 없음", message)
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        reply = QMessageBox.question(
            self,
            "치환 확인",
            (
                "정말 실행하시겠습니까?\n\n"
                f"찾을 값: {context['source_text']}\n"
                f"치환 값: {context['target_text']}\n"
                f"대상 라벨: {len(matched_rows)}개"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._set_recent_log("실행 취소: 치환 작업을 취소했습니다.")
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        page_tasks: List[Dict[str, Any]] = []
        missing_snapshot_pages: List[str] = []
        grouped_rows: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for row in matched_rows:
            key = (str(row.get("book_id", "")).strip(), str(row.get("page_name", "")).strip())
            grouped_rows.setdefault(key, []).append(row)

        for (book_id, page_name), rows in grouped_rows.items():
            json_row = self._find_json_row(book_id, page_name)
            page_label = f"{book_id}:{page_name}"
            if json_row is None:
                missing_snapshot_pages.append(page_label)
                continue
            snapshot_payload = self._load_page_json_payload(json_row)
            if not snapshot_payload:
                missing_snapshot_pages.append(page_label)
                continue
            page_tasks.append(
                {
                    "page_label": page_label,
                    "json_row": dict(json_row),
                    "snapshot_payload": snapshot_payload,
                    "rows": [
                        {
                            "row_key": str(row.get("row_key", "")).strip(),
                            "book_id": str(row.get("book_id", "")).strip(),
                            "page_name": str(row.get("page_name", "")).strip(),
                            "label_id": str(row.get("label_id", "")).strip(),
                            "label": str(row.get("label", "")).strip(),
                            "shape_index": int(row.get("shape_index", -1)),
                        }
                        for row in rows
                    ],
                }
            )

        if missing_snapshot_pages:
            preview = ", ".join(missing_snapshot_pages[:5])
            suffix = " ..." if len(missing_snapshot_pages) > 5 else ""
            QMessageBox.warning(
                self,
                "치환 중단",
                "치환에 필요한 스냅샷 JSON이 없어 치환을 진행하지 않았습니다.\n"
                f"대상 페이지: {preview}{suffix}",
            )
            self._set_recent_log(f"실행 중단: 스냅샷 JSON 없음 ({preview}{suffix})")
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        self._clear_replace_visual_state(clear_preview=True, clear_applied=True)
        self._begin_replace_worker(page_tasks=page_tasks, context=context)

    def _run_nfkc_tool(self) -> None:
        self._text_analysis_is_running = True
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()

        target_rows, precheck_failures, segment_count = self._collect_nfkc_target_rows()
        if not target_rows:
            detail = "\n".join(precheck_failures[:8])
            suffix = "\n..." if len(precheck_failures) > 8 else ""
            message = "현재 검색/필터 결과 중 NFKC 정규화로 변경되는 매칭 구간이 없습니다."
            if detail:
                message += f"\n\n{detail}{suffix}"
            QMessageBox.information(self, "NFKC 정규화 대상 없음", message)
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        reply = QMessageBox.question(
            self,
            "NFKC 정규화 확인",
            (
                "현재 필터 결과의 매칭 구간만 NFKC 정규화합니다.\n\n"
                f"대상 라벨: {len(target_rows)}개\n"
                f"변경 구간: {segment_count}개\n\n"
                "계속하시겠습니까?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._set_recent_log("실행 취소: NFKC 정규화 작업을 취소했습니다.")
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        page_tasks: List[Dict[str, Any]] = []
        missing_snapshot_pages: List[str] = []
        grouped_rows: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for row in target_rows:
            key = (str(row.get("book_id", "")).strip(), str(row.get("page_name", "")).strip())
            grouped_rows.setdefault(key, []).append(row)

        for (book_id, page_name), rows in grouped_rows.items():
            json_row = self._find_json_row(book_id, page_name)
            page_label = f"{book_id}:{page_name}"
            if json_row is None:
                missing_snapshot_pages.append(page_label)
                continue
            snapshot_payload = self._load_page_json_payload(json_row)
            if not snapshot_payload:
                missing_snapshot_pages.append(page_label)
                continue
            page_tasks.append(
                {
                    "page_label": page_label,
                    "json_row": dict(json_row),
                    "snapshot_payload": snapshot_payload,
                    "rows": [
                        {
                            "row_key": str(row.get("row_key", "")).strip(),
                            "book_id": str(row.get("book_id", "")).strip(),
                            "page_name": str(row.get("page_name", "")).strip(),
                            "label_id": str(row.get("label_id", "")).strip(),
                            "label": str(row.get("label", "")).strip(),
                            "shape_index": int(row.get("shape_index", -1)),
                            "nfkc_segments": list(row.get("nfkc_segments", []) or []),
                        }
                        for row in rows
                    ],
                }
            )

        if missing_snapshot_pages:
            preview = ", ".join(missing_snapshot_pages[:5])
            suffix = " ..." if len(missing_snapshot_pages) > 5 else ""
            QMessageBox.warning(
                self,
                "NFKC 정규화 중단",
                "NFKC 정규화에 필요한 스냅샷 JSON이 없어 진행하지 않았습니다.\n"
                f"대상 페이지: {preview}{suffix}",
            )
            self._set_recent_log(f"실행 중단: NFKC 정규화 스냅샷 JSON 없음 ({preview}{suffix})")
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        self._clear_replace_visual_state(clear_preview=True, clear_applied=False)
        self._begin_replace_worker(
            page_tasks=page_tasks,
            context={
                "operation": "nfkc",
                "source_text": "NFKC",
                "target_text": "정규화",
                "use_regex": False,
                "case_sensitive": True,
                "replacement_uses_groups": False,
            },
        )

    def _begin_replace_worker(self, *, page_tasks: List[Dict[str, Any]], context: Dict[str, Any]) -> None:
        request_id = self._text_analysis_replace_request_id + 1
        self._text_analysis_replace_request_id = request_id
        worker = TextAnalysisReplaceWorker(
            aws_config=self.config.get("aws", {}),
            cache_dir=str(self._json_cache_dir),
            page_tasks=page_tasks,
            context={
                "operation": str(context.get("operation", "replace") or "replace"),
                "source_text": str(context.get("source_text", "") or ""),
                "target_text": str(context.get("target_text", "") or ""),
                "use_regex": bool(context.get("use_regex", False)),
                "case_sensitive": bool(context.get("case_sensitive", False)),
                "replacement_uses_groups": bool(context.get("replacement_uses_groups", False)),
            },
        )
        self._text_analysis_replace_worker = worker
        worker.progress.connect(
            lambda desc, current, total, rid=request_id: self._on_replace_worker_progress(rid, desc, current, total)
        )
        worker.finished_ok.connect(
            lambda bundle, rid=request_id, ctx=copy.deepcopy(context): self._on_replace_worker_finished(rid, bundle, ctx)
        )
        worker.cancelled.connect(
            lambda bundle, rid=request_id, ctx=copy.deepcopy(context): self._on_replace_worker_cancelled(rid, bundle, ctx)
        )
        worker.failed.connect(
            lambda message, rid=request_id, ctx=copy.deepcopy(context): self._on_replace_worker_failed(rid, message, ctx)
        )
        worker.finished.connect(lambda rid=request_id: self._on_replace_worker_cleanup(rid))
        worker.start()

    def _on_replace_worker_progress(self, request_id: int, desc: str, current: int, total: int) -> None:
        if request_id != self._text_analysis_replace_request_id:
            return
        self._set_progress(desc, current, total)

    def _apply_replace_worker_bundle(self, bundle: Dict[str, Any], context: Dict[str, Any], *, cancelled: bool) -> None:
        bundle = dict(bundle or {})
        operation = str(context.get("operation", "replace") or "replace").strip()
        is_nfkc = operation == "nfkc"
        operation_label = "NFKC 정규화" if is_nfkc else "치환"
        mismatch_pages = list(bundle.get("snapshot_mismatch_pages", []) or [])
        if mismatch_pages:
            preview = ", ".join(mismatch_pages[:5])
            suffix = " ..." if len(mismatch_pages) > 5 else ""
            QMessageBox.warning(
                self,
                f"{operation_label} 중단",
                f"{operation_label} 시점에 S3 데이터가 스냅샷과 달라 진행하지 않았습니다.\n"
                f"대상 페이지: {preview}{suffix}",
            )
            self._set_recent_log(f"실행 중단: S3 스냅샷 차이 감지 ({preview}{suffix})")
            self._text_analysis_is_running = False
            self._text_analysis_stop_requested = False
            self._refresh_run_button_state()
            return

        updated_payloads = dict(bundle.get("updated_payloads", {}) or {})
        for page_label, payload in updated_payloads.items():
            if ":" not in str(page_label):
                continue
            book_id, page_name = str(page_label).split(":", 1)
            json_row = self._find_json_row(book_id, page_name)
            if json_row is None:
                continue
            cache_key = self._json_cache_key(json_row)
            if cache_key:
                self._json_payload_cache[cache_key] = copy.deepcopy(payload)

        successful_row_keys: set[str] = {
            str(item.get("row_key", "")).strip()
            for item in list(bundle.get("applied_updates", []) or [])
            if str(item.get("row_key", "")).strip()
        }
        applied_by_key = {
            str(item.get("row_key", "")).strip(): dict(item)
            for item in list(bundle.get("applied_updates", []) or [])
            if str(item.get("row_key", "")).strip()
        }
        replace_summary = "NFKC 정규화" if is_nfkc else f"{context['source_text']} → {context['target_text']}"

        for row in self.current_label_rows:
            row_key = str(row.get("row_key", "")).strip()
            if row_key in successful_row_keys:
                update = applied_by_key[row_key]
                matched_values = list(update.get("matched_values", []) or [])
                changed_segment_count = int(update.get("changed_segment_count", len(matched_values)) or 0)
                row["replace_original_value"] = str(update.get("current_text", "") or "")
                row["replace_preview_value"] = ""
                row["replace_preview_segments"] = []
                row["replace_applied"] = True
                row["flags_text"] = str(update.get("replaced_text", "") or "")
                row["value"] = str(update.get("replaced_text", "") or "")
                row["tool_id"] = "nfkc_normalize_tool" if is_nfkc else "replace_tool"
                if not is_nfkc:
                    if str(row.get("detail_filter_tool_id", "")).strip() != "search_tool" or not list(
                        row.get("detail_filter_values", []) or []
                    ):
                        self._set_detail_filter_state(row, tool_id="search_tool", values=matched_values)
                row["tool_error_type"] = replace_summary
                if is_nfkc:
                    row["tool_error_detail"] = f"NFKC 정규화 완료: {changed_segment_count}개 구간"
                else:
                    row["tool_error_detail"] = build_replace_detail(
                        pattern=context["source_text"],
                        replacement=context["target_text"],
                        matches=matched_values,
                        use_regex=context["use_regex"],
                    )
                row["tool_error_matches"] = matched_values
                row["match_spans"] = list(update.get("display_spans", []) or [])
                row["highlight_text"] = ""
                row["highlight_matches"] = []
                self._refresh_row_result_state(row)
                continue

            row["replace_preview_value"] = ""
            row["replace_preview_segments"] = []
            if is_nfkc:
                continue
            row["replace_applied"] = False
            row["replace_original_value"] = ""
            if str(row.get("tool_id", "")) == "replace_tool":
                row["tool_id"] = ""
                row["tool_error_type"] = ""
                row["tool_error_detail"] = ""
                row["tool_error_matches"] = []
                row["highlight_text"] = ""
                row["highlight_matches"] = []
                self._set_detail_filter_state(row, tool_id="", values=[])
                self._refresh_row_result_state(row)

        failed_rows = list(bundle.get("failed_rows", []) or [])
        updated_pages = int(bundle.get("updated_pages", 0) or 0)
        updated_labels = int(bundle.get("updated_labels", 0) or 0)
        fatal_error = str(bundle.get("fatal_error", "") or "").strip()
        if failed_rows:
            preview = "\n".join(failed_rows[:10])
            suffix = "\n..." if len(failed_rows) > 10 else ""
            QMessageBox.warning(
                self,
                f"{operation_label} 일부 실패",
                f"{operation_label} 성공 {updated_labels}건, 실패 {len(failed_rows)}건입니다.\n\n{preview}{suffix}",
            )
            self._set_recent_log(
                f"실행 완료: {operation_label} 페이지 {updated_pages}건 / 라벨 {updated_labels}건 / 실패 {len(failed_rows)}건"
            )
        if fatal_error:
            QMessageBox.warning(self, f"{operation_label} 실패", fatal_error)
            self._set_recent_log(
                f"실행 실패: {operation_label} 페이지 {updated_pages}건 / 라벨 {updated_labels}건 반영 후 중단 ({fatal_error})"
            )

        self.center_panel.set_pages(self.current_label_rows, results_only=True)
        self._refresh_dashboard()
        self._select_first_row_after_refresh(prefer_result=True)
        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()

        if cancelled:
            self._set_recent_log(
                f"실행 중지: {operation_label} 페이지 {updated_pages}건 / 라벨 {updated_labels}건 반영 후 멈췄습니다."
            )
            return
        if fatal_error:
            return
        self._set_recent_log(f"실행 완료: {operation_label} 페이지 {updated_pages}건 / 라벨 {updated_labels}건")

    def _on_replace_worker_finished(self, request_id: int, bundle: Dict[str, Any], context: Dict[str, Any]) -> None:
        if request_id != self._text_analysis_replace_request_id:
            return
        self._apply_replace_worker_bundle(bundle, context, cancelled=False)

    def _on_replace_worker_cancelled(self, request_id: int, bundle: Dict[str, Any], context: Dict[str, Any]) -> None:
        if request_id != self._text_analysis_replace_request_id:
            return
        self._apply_replace_worker_bundle(bundle, context, cancelled=True)

    def _on_replace_worker_failed(self, request_id: int, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        if request_id != self._text_analysis_replace_request_id:
            return
        operation = str((context or {}).get("operation", "replace") or "replace").strip()
        operation_label = "NFKC 정규화" if operation == "nfkc" else "치환"
        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._refresh_run_button_state()
        QMessageBox.warning(self, f"{operation_label} 실패", str(message).strip() or "알 수 없는 오류")
        self._set_recent_log(f"실행 실패: {operation_label} 저장 중 오류")

    def _on_replace_worker_cleanup(self, request_id: int) -> None:
        if request_id != self._text_analysis_replace_request_id:
            return
        worker = self._text_analysis_replace_worker
        if worker is not None:
            worker.deleteLater()
        self._text_analysis_replace_worker = None

    def _build_replace_context(self, *, show_errors: bool) -> Optional[Dict[str, Any]]:
        search_context = dict(self._last_search_context or {})
        source_text = str(search_context.get("pattern", "") or "").strip()
        if not source_text:
            if show_errors:
                QMessageBox.information(self, "검색 실행 필요", "치환 전 검색을 먼저 실행해 주세요.")
            return None

        target_text = self.left_panel.replace_target_text()
        if target_text == "":
            if show_errors:
                QMessageBox.information(self, "치환값 필요", "치환 값을 입력해 주세요.")
            return None

        source_use_regex = bool(search_context.get("use_regex", False))
        source_case_sensitive = bool(search_context.get("case_sensitive", False))
        try:
            regex = compile_pattern(
                source_text,
                use_regex=source_use_regex,
                case_sensitive=source_case_sensitive,
            )
        except Exception as exc:
            if show_errors:
                QMessageBox.warning(self, "정규식 오류", f"마지막 검색 정규식이 올바르지 않습니다.\n{exc}")
            return None

        return {
            "source_text": source_text,
            "target_text": target_text,
            "use_regex": source_use_regex,
            "case_sensitive": source_case_sensitive,
            "regex": regex,
            "replacement_uses_groups": self.left_panel.replace_use_regex(),
            "search_context": search_context,
        }

    def _visible_replace_target_rows(self) -> List[Dict[str, Any]]:
        visible_rows = getattr(self.center_panel, "visible_source_rows", lambda: [])()
        if not visible_rows:
            return []

        current_by_key = {
            str(row.get("row_key", "")): row
            for row in self.current_label_rows
            if str(row.get("row_key", ""))
        }
        targets: List[Dict[str, Any]] = []
        for visible_row in visible_rows:
            if bool(visible_row.get("replace_applied", False)):
                continue
            detail_tool_id = str(
                visible_row.get("detail_filter_tool_id", visible_row.get("tool_id", "")) or ""
            ).strip()
            if detail_tool_id != "search_tool":
                continue
            row_key = str(visible_row.get("row_key", "")).strip()
            if not row_key:
                continue
            current_row = current_by_key.get(row_key)
            if current_row is not None and not bool(current_row.get("replace_applied", False)):
                targets.append(current_row)
        return targets

    def _visible_nfkc_target_display_rows(self) -> List[Dict[str, Any]]:
        visible_rows = getattr(self.center_panel, "visible_display_rows", lambda: [])()
        if not visible_rows:
            return []

        targets: List[Dict[str, Any]] = []
        for visible_row in visible_rows:
            if bool(visible_row.get("replace_applied", False)):
                continue
            detail_tool_id = str(
                visible_row.get("detail_filter_tool_id", visible_row.get("tool_id", "")) or ""
            ).strip()
            if detail_tool_id not in {"search_tool", "special_char_analysis"}:
                continue
            row_key = str(visible_row.get("row_key", "")).strip()
            if not row_key:
                continue
            targets.append(dict(visible_row))
        return targets

    def _collect_nfkc_target_rows(self) -> tuple[List[Dict[str, Any]], List[str], int]:
        current_by_key = {
            str(row.get("row_key", "")).strip(): row
            for row in self.current_label_rows
            if str(row.get("row_key", "")).strip()
        }
        segments_by_key: Dict[str, List[Dict[str, Any]]] = {}
        seen_segments: set[tuple[str, int, int, str]] = set()
        failures: List[str] = []

        for visible_row in self._visible_nfkc_target_display_rows():
            row_key = str(visible_row.get("row_key", "")).strip()
            current_row = current_by_key.get(row_key)
            if current_row is None or bool(current_row.get("replace_applied", False)):
                continue

            try:
                start = int(visible_row.get("_match_start", -1))
                end = int(visible_row.get("_match_end", -1))
            except (TypeError, ValueError):
                failures.append(f"{self._format_replace_row_label(current_row)}: NFKC 정규화 구간을 읽을 수 없습니다.")
                continue

            text = str(current_row.get("flags_text", "") or "")
            if not text or start < 0 or end <= start or end > len(text):
                failures.append(f"{self._format_replace_row_label(current_row)}: NFKC 정규화 구간 범위가 올바르지 않습니다.")
                continue

            original = text[start:end]
            expected = str(visible_row.get("_match_value", "") or visible_row.get("_kwic_match", "") or "")
            if expected and original != expected:
                failures.append(f"{self._format_replace_row_label(current_row)}: 표시된 매칭값과 flags.text 구간이 일치하지 않습니다.")
                continue

            normalized = unicodedata.normalize("NFKC", original)
            if normalized == original:
                continue

            segment_key = (row_key, start, end, original)
            if segment_key in seen_segments:
                continue
            seen_segments.add(segment_key)
            segments_by_key.setdefault(row_key, []).append(
                {"start": start, "end": end, "original": original, "replacement": normalized}
            )

        target_rows: List[Dict[str, Any]] = []
        segment_count = 0
        for row_key, segments in segments_by_key.items():
            current_row = current_by_key.get(row_key)
            if current_row is None:
                continue
            ordered_segments = sorted(segments, key=lambda item: int(item.get("start", -1)))
            last_end = 0
            overlap = False
            for segment in ordered_segments:
                start = int(segment.get("start", -1))
                end = int(segment.get("end", -1))
                if start < last_end:
                    overlap = True
                    break
                last_end = end
            if overlap:
                failures.append(f"{self._format_replace_row_label(current_row)}: NFKC 정규화 구간이 서로 겹칩니다.")
                continue
            target_row = dict(current_row)
            target_row["nfkc_segments"] = ordered_segments
            target_rows.append(target_row)
            segment_count += len(ordered_segments)

        return target_rows, failures, segment_count

    def _clear_replace_visual_state(self, *, clear_preview: bool, clear_applied: bool) -> bool:
        changed = False
        for row in self.current_label_rows:
            if clear_preview:
                if str(row.get("replace_preview_value", "")):
                    row["replace_preview_value"] = ""
                    changed = True
                if list(row.get("replace_preview_segments", []) or []):
                    row["replace_preview_segments"] = []
                    changed = True
            if clear_applied and bool(row.get("replace_applied", False)):
                row["replace_applied"] = False
                row["replace_original_value"] = ""
                changed = True
        return changed

    def _refresh_replace_preview(self, *_args) -> None:
        if not self.current_label_rows:
            return

        changed = self._clear_replace_visual_state(clear_preview=True, clear_applied=False)
        selected_tool_id = self.left_panel.selected_tool_id()
        if selected_tool_id == "nfkc_normalize_tool":
            changed = self._refresh_nfkc_preview() or changed
            if changed:
                self.center_panel.set_pages(self.current_label_rows, results_only=True)
            return

        if selected_tool_id != "replace_tool":
            if changed:
                self.center_panel.set_pages(
                    self.current_label_rows,
                    results_only=any(is_error_base_state(row.get("base_state")) for row in self.current_label_rows),
                )
            return

        context = self._build_replace_context(show_errors=False)
        if context is None:
            if changed:
                self.center_panel.set_pages(self.current_label_rows, results_only=True)
            return

        preview_rows = self._visible_replace_target_rows()
        for row in preview_rows:
            current_text = self._replace_source_text_from_row(row)
            if current_text == "":
                continue
            replaced_text, matches, preview_segments = replace_text(
                current_text,
                context["source_text"],
                context["target_text"],
                use_regex=context["use_regex"],
                case_sensitive=context["case_sensitive"],
                regex=context["regex"],
                replacement_uses_groups=context["replacement_uses_groups"],
            )
            if not matches or replaced_text == current_text:
                continue
            row["replace_preview_value"] = replaced_text
            row["replace_preview_segments"] = preview_segments
            changed = True

        if changed:
            self.center_panel.set_pages(self.current_label_rows, results_only=True)

    def _refresh_nfkc_preview(self) -> bool:
        current_by_key = {
            str(row.get("row_key", "")).strip(): row
            for row in self.current_label_rows
            if str(row.get("row_key", "")).strip()
        }
        target_rows, _failures, _segment_count = self._collect_nfkc_target_rows()
        changed = False
        for target_row in target_rows:
            row_key = str(target_row.get("row_key", "")).strip()
            current_row = current_by_key.get(row_key)
            if current_row is None:
                continue
            segments = list(target_row.get("nfkc_segments", []) or [])
            text = str(current_row.get("flags_text", "") or "")
            preview_value = self._apply_preview_segments(text, segments)
            if not preview_value or preview_value == text:
                continue
            current_row["replace_preview_value"] = preview_value
            current_row["replace_preview_segments"] = sorted(
                segments,
                key=lambda item: int(item.get("start", -1)),
            )
            changed = True
        return changed

    def _apply_preview_segments(self, text: str, segments: List[Dict[str, Any]]) -> str:
        ordered: List[Dict[str, Any]] = []
        last_end = 0
        for segment in sorted(segments, key=lambda item: int(item.get("start", -1))):
            try:
                start = int(segment.get("start", -1))
                end = int(segment.get("end", -1))
            except (TypeError, ValueError):
                return ""
            if start < last_end or start < 0 or end <= start or end > len(text):
                return ""
            ordered.append(segment)
            last_end = end

        parts: List[str] = []
        cursor = 0
        for segment in ordered:
            start = int(segment.get("start", -1))
            end = int(segment.get("end", -1))
            parts.append(text[cursor:start])
            parts.append(str(segment.get("replacement", "") or ""))
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts)

    def _normalize_replace_compare_payload(self, payload: Any) -> Any:
        return normalize_compare_payload(payload)

    def _replace_source_text_from_row(self, row: Dict[str, Any]) -> str:
        return str(row.get("flags_text", "") or "")

    def _format_replace_row_label(self, row: Dict[str, Any]) -> str:
        return format_replace_row_label(row)
