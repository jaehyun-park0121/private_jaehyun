from __future__ import annotations

import concurrent.futures
import copy
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtWidgets import QApplication, QInputDialog, QMenu, QMessageBox

from app.common.config.parallel_settings import resolve_parallel_workers
from app.tabs.text_analysis.features.base_state import is_error_base_state
from app.tabs.text_analysis.features.s3_loader import S3Loader


class TextAnalysisProblemSyncStrictMixin:
    def _problem_sync_is_busy(self, action_name: str) -> bool:
        if bool(getattr(self, "_text_analysis_snapshot_loading", False)):
            QMessageBox.information(self, "조회 중", f"JSON 스냅샷 조회가 끝난 뒤 {action_name}을 진행해 주세요.")
            self._set_recent_log(f"{action_name} 보류: JSON 스냅샷 조회 중")
            return True
        if bool(getattr(self, "_text_analysis_is_running", False)):
            QMessageBox.information(self, "실행 중", f"검수 도구 실행이 끝난 뒤 {action_name}을 진행해 주세요.")
            self._set_recent_log(f"{action_name} 보류: 검수 도구 실행 중")
            return True
        return False

    def _problem_sync_shape_index(self, row: Dict[str, Any]) -> int:
        value = row.get("shape_index", -1)
        if value is None:
            return -1
        text = str(value).strip()
        if not text:
            return -1
        try:
            return int(text)
        except Exception:
            return -1

    def _problem_sync_terminal_log(self, message: str) -> None:
        try:
            print(f"[SKIP][text_analysis problem_sync_strict] {str(message).strip()}", flush=True)
        except Exception:
            pass

    def _problem_sync_row_label(self, row: Dict[str, Any]) -> str:
        book_id = str(row.get("book_id", "")).strip() or "-"
        page_name = str(row.get("page_name", "")).strip() or "-"
        label = str(row.get("label", "")).strip() or "-"
        label_id = str(row.get("label_id", "")).strip() or "-"
        row_key = str(row.get("row_key", "")).strip() or "-"
        shape_index = self._problem_sync_shape_index(row)
        shape_text = str(shape_index + 1) if shape_index >= 0 else "-"
        return (
            f"{book_id}:{page_name} / shape {shape_text} / label {label_id}:{label} / row_key={row_key}"
        )

    def _visible_current_rows(self) -> List[Dict[str, Any]]:
        visible_rows = list(getattr(self.center_panel, "visible_source_rows", lambda: [])() or [])
        if not visible_rows:
            return []

        current_by_key = {
            str(row.get("row_key", "")): row
            for row in self.current_label_rows
            if str(row.get("row_key", "")).strip()
        }
        resolved: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        for visible_row in visible_rows:
            row_key = str(visible_row.get("row_key", "")).strip()
            if not row_key:
                continue
            current_row = current_by_key.get(row_key)
            if current_row is not None:
                if row_key not in seen_keys:
                    seen_keys.add(row_key)
                    resolved.append(current_row)
                continue

            if ":placeholder:" in row_key:
                book_id = str(visible_row.get("book_id", "")).strip()
                page_name = str(visible_row.get("page_name", "")).strip()
                for lr in self.current_label_rows:
                    if str(lr.get("book_id", "")).strip() != book_id:
                        continue
                    if str(lr.get("page_name", "")).strip() != page_name:
                        continue
                    lk = str(lr.get("row_key", "")).strip()
                    if not lk or lk in seen_keys:
                        continue
                    seen_keys.add(lk)
                    resolved.append(lr)
        return resolved

    def _remove_reason_entry_line(self, reason_text: str, target_entry: str) -> Tuple[str, bool]:
        target = str(target_entry or "").strip()
        source = str(reason_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not target:
            return source, False

        lines = source.split("\n")
        had_problem_anchor = source.startswith("\n")
        kept_visible: List[str] = []
        removed = False
        for line in lines:
            if line.strip() == target:
                removed = True
                continue
            if line.strip():
                kept_visible.append(line.strip())

        merged = "\n".join(kept_visible)
        if had_problem_anchor:
            return (f"\n{merged}" if merged else "\n"), removed
        return merged, removed

    def _payload_without_problem_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(payload)
        shapes = normalized.get("shapes", [])
        if not isinstance(shapes, list):
            return normalized
        for shape in shapes:
            if not isinstance(shape, dict):
                continue
            shape.pop("is_problem", None)
            shape.pop("problem_reason", None)
        return normalized

    def _problem_sync_json_row_for_page(self, book_id: str, page_name: str) -> Optional[Dict[str, Any]]:
        return self._find_json_row(book_id, page_name)

    def _problem_sync_load_snapshot_payload(
        self,
        book_id: str,
        page_name: str,
        json_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        del book_id, page_name
        return self._load_page_json_payload(json_row)

    def _problem_sync_load_latest_payload(
        self,
        json_row: Dict[str, Any],
        *,
        loader: S3Loader,
    ) -> Dict[str, Any]:
        return self._load_page_json_payload_fresh(json_row, loader=loader)

    def _problem_sync_write_payload_remote(
        self,
        json_row: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        loader: S3Loader,
    ) -> None:
        self._write_page_json_payload_remote(json_row, payload, loader=loader)

    def _problem_sync_cache_saved_payload(
        self,
        json_row: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> None:
        self._cache_page_json_payload(json_row, payload)

    def _problem_sync_worker_count(self, total_tasks: int) -> int:
        if total_tasks <= 1:
            return 1
        return resolve_parallel_workers(self.config, total_tasks=total_tasks)

    def _problem_sync_prefetch_page_context(
        self,
        book_id: str,
        page_name: str,
        *,
        loader: S3Loader,
    ) -> Dict[str, Any]:
        page_label = f"{book_id}:{page_name}"
        page_key = (book_id, page_name)
        json_row = self._problem_sync_json_row_for_page(book_id, page_name)
        if json_row is None:
            return {
                "status": "missing_json",
                "page_key": page_key,
                "page_label": page_label,
            }
        try:
            latest_payload = self._problem_sync_load_latest_payload(json_row, loader=loader)
        except Exception as exc:
            return {
                "status": "load_failed",
                "page_key": page_key,
                "page_label": page_label,
                "error": str(exc),
            }
        if not latest_payload:
            return {
                "status": "missing_payload",
                "page_key": page_key,
                "page_label": page_label,
            }
        return {
            "status": "ok",
            "page_key": page_key,
            "page_label": page_label,
            "json_row": json_row,
            "latest_payload": latest_payload,
        }

    def _problem_sync_shapes(self, payload: Dict[str, Any]) -> List[Any]:
        shapes = payload.get("shapes", [])
        return shapes if isinstance(shapes, list) else []

    def _append_problem_reason_entry(
        self,
        current_reason: str,
        entry: str,
        *,
        keep_problem_without_reason: bool,
    ) -> str:
        normalized = str(current_reason or "").replace("\r\n", "\n").replace("\r", "\n")
        clean_entry = str(entry or "").strip()
        if not clean_entry:
            return normalized

        visible_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        visible_lines.append(clean_entry)
        merged = "\n".join(visible_lines)

        if keep_problem_without_reason and not normalized.strip():
            return f"\n{merged}" if merged else "\n"
        if normalized.startswith("\n"):
            return f"\n{merged}" if merged else "\n"
        return merged

    def _reason_text_keeps_problem_flag(self, reason_text: str) -> bool:
        normalized = str(reason_text or "").replace("\r\n", "\n").replace("\r", "\n")
        return bool(normalized.strip()) or normalized.startswith("\n")

    def _problem_reasons_with_count(self) -> List[Tuple[str, int]]:
        counts: Dict[str, int] = {}
        reason_pattern = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s+.+$")
        for row in self._visible_current_rows():
            if not bool(row.get("is_problem", False)):
                continue
            reason = str(row.get("problem_reason", "")).strip()
            if not reason:
                continue
            entries = [line.strip() for line in reason.replace("\r\n", "\n").split("\n") if line.strip()]
            for entry in entries:
                if not reason_pattern.match(entry):
                    continue
                counts[entry] = counts.get(entry, 0) + 1
        return sorted(counts.items(), key=lambda item: item[0])

    def _rebuild_reset_reason_menu(self, menu: QMenu) -> None:
        menu.clear()
        reason_items = self._problem_reasons_with_count()
        if not reason_items:
            empty = menu.addAction("초기화할 problem_reason 항목이 없습니다")
            empty.setEnabled(False)
            return
        for reason, count in reason_items:
            action = menu.addAction(f"{reason} ({count})")
            action.triggered.connect(lambda _=False, r=reason: self._reset_problem_by_reason_value(r))

    def _problem_latest_payloads_for_pages(
        self,
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]],
        s3_loader: S3Loader,
        *,
        require_snapshot_match: bool,
        progress_desc: Optional[str] = None,
    ) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], List[str], List[str]]:
        page_contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}
        skipped_pages: List[str] = []
        mismatch_pages: List[str] = []
        page_keys = list(grouped.keys())
        total_pages = len(page_keys)
        prefetch_desc = f"{progress_desc} / 최신 JSON 확인" if progress_desc else None
        worker_count = self._problem_sync_worker_count(total_pages)

        if worker_count <= 1:
            for index, (book_id, page_name) in enumerate(page_keys, start=1):
                if prefetch_desc:
                    self._set_progress(prefetch_desc, index, total_pages)
                QApplication.processEvents()
                result = self._problem_sync_prefetch_page_context(book_id, page_name, loader=s3_loader)
                page_label = str(result.get("page_label", "")).strip() or f"{book_id}:{page_name}"
                status = str(result.get("status", "")).strip()
                if status == "ok":
                    page_contexts[(book_id, page_name)] = {
                        "json_row": result.get("json_row", {}),
                        "latest_payload": result.get("latest_payload", {}),
                    }
                    continue

                skipped_pages.append(page_label)
                if status == "load_failed":
                    error = str(result.get("error", "")).strip()
                    self._set_recent_log(f"확인 필요 저장 제외: 최신 S3 JSON 로드 실패 ({page_label}) {error}")
                elif status == "missing_json":
                    self._set_recent_log(f"확인 필요 저장 제외: JSON 정보 없음 ({page_label})")
                else:
                    self._set_recent_log(f"확인 필요 저장 제외: 최신 S3 JSON 로드 실패 ({page_label})")
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        self._problem_sync_prefetch_page_context,
                        book_id,
                        page_name,
                        loader=s3_loader,
                    ): (book_id, page_name)
                    for book_id, page_name in page_keys
                }
                completed = 0
                for future in concurrent.futures.as_completed(future_map):
                    completed += 1
                    if prefetch_desc:
                        self._set_progress(prefetch_desc, completed, total_pages)
                    QApplication.processEvents()

                    book_id, page_name = future_map[future]
                    page_label = f"{book_id}:{page_name}"
                    try:
                        result = future.result()
                    except Exception as exc:
                        skipped_pages.append(page_label)
                        self._set_recent_log(f"확인 필요 저장 제외: 최신 S3 JSON 로드 실패 ({page_label}) {exc}")
                        continue

                    page_label = str(result.get("page_label", "")).strip() or page_label
                    status = str(result.get("status", "")).strip()
                    if status == "ok":
                        page_contexts[(book_id, page_name)] = {
                            "json_row": result.get("json_row", {}),
                            "latest_payload": result.get("latest_payload", {}),
                        }
                        continue

                    skipped_pages.append(page_label)
                    if status == "load_failed":
                        error = str(result.get("error", "")).strip()
                        self._set_recent_log(f"확인 필요 저장 제외: 최신 S3 JSON 로드 실패 ({page_label}) {error}")
                    elif status == "missing_json":
                        self._set_recent_log(f"확인 필요 저장 제외: JSON 정보 없음 ({page_label})")
                    else:
                        self._set_recent_log(f"확인 필요 저장 제외: 최신 S3 JSON 로드 실패 ({page_label})")

        if not require_snapshot_match:
            return page_contexts, skipped_pages, mismatch_pages

        for book_id, page_name in page_keys:
            page_context = page_contexts.get((book_id, page_name))
            if not page_context:
                continue

            page_label = f"{book_id}:{page_name}"
            json_row = page_context.get("json_row")
            latest_payload = page_context.get("latest_payload")
            if not isinstance(json_row, dict) or not isinstance(latest_payload, dict):
                skipped_pages.append(page_label)
                self._set_recent_log(f"확인 필요 저장 제외: 최신 JSON 정보 이상 ({page_label})")
                page_contexts.pop((book_id, page_name), None)
                continue

            snapshot_payload = self._problem_sync_load_snapshot_payload(book_id, page_name, json_row)
            if not snapshot_payload:
                skipped_pages.append(page_label)
                self._set_recent_log(f"확인 필요 저장 제외: 스냅샷 JSON 없음 ({page_label})")
                page_contexts.pop((book_id, page_name), None)
                continue
            if self._payload_without_problem_fields(latest_payload) != self._payload_without_problem_fields(
                snapshot_payload
            ):
                mismatch_pages.append(page_label)
                page_contexts.pop((book_id, page_name), None)

        return page_contexts, skipped_pages, mismatch_pages

    def _show_problem_snapshot_mismatch_warning(self, title: str, mismatch_pages: List[str]) -> None:
        preview = ", ".join(mismatch_pages[:5])
        suffix = "" if len(mismatch_pages) <= 5 else " ..."
        QMessageBox.warning(
            self,
            title,
            (
                f"스냅샷과 다른 JSON이 {len(mismatch_pages)}건 감지되어 작업을 진행하지 않았습니다.\n"
                "스냅샷을 다시 조회한 뒤 다시 시도해 주세요.\n\n"
                f"대상 페이지: {preview}{suffix}"
            ),
        )

    def _sync_problem_fields_to_json(
        self,
        rows: List[Dict[str, Any]],
        *,
        append_reason_entry: Optional[str] = None,
        remove_reason_entry: Optional[str] = None,
        progress_desc: Optional[str] = None,
        require_snapshot_match: bool = False,
        abort_on_snapshot_mismatch: bool = False,
    ) -> Tuple[int, List[str], List[str]]:
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for row in rows:
            shape_index = self._problem_sync_shape_index(row)
            if shape_index < 0:
                continue
            book_id = str(row.get("book_id", "")).strip()
            page_name = str(row.get("page_name", "")).strip()
            if not book_id or not page_name:
                continue
            grouped.setdefault((book_id, page_name), []).append(row)

        if not grouped:
            return 0, [], []

        try:
            s3_loader = S3Loader(self.config.get("aws", {}))
        except Exception as exc:
            self._set_recent_log(f"S3 저장 준비 실패로 작업을 중단했습니다: {exc}")
            return 0, [f"{book_id}:{page_name}" for book_id, page_name in grouped.keys()], []

        page_contexts, preloaded_failed_pages, mismatch_pages = self._problem_latest_payloads_for_pages(
            grouped,
            s3_loader,
            require_snapshot_match=require_snapshot_match,
            progress_desc=progress_desc,
        )
        if require_snapshot_match and abort_on_snapshot_mismatch and mismatch_pages:
            return 0, [], mismatch_pages

        updated_pages = 0
        failed_pages: List[str] = list(preloaded_failed_pages)
        save_jobs: List[Dict[str, Any]] = []

        for (book_id, page_name), target_rows in grouped.items():
            page_context = page_contexts.get((book_id, page_name))
            if not page_context:
                continue

            page_label = f"{book_id}:{page_name}"
            json_row = page_context.get("json_row")
            latest_payload = page_context.get("latest_payload")
            if not isinstance(json_row, dict) or not isinstance(latest_payload, dict):
                failed_pages.append(page_label)
                self._set_recent_log(f"확인 필요 저장 실패: 최신 JSON 정보 이상 ({page_label})")
                continue

            payload = copy.deepcopy(latest_payload)
            shapes = self._problem_sync_shapes(payload)
            if not isinstance(shapes, list):
                failed_pages.append(page_label)
                self._set_recent_log(f"확인 필요 저장 제외: JSON shapes 구조 이상 ({page_label})")
                continue

            pending_updates: List[Tuple[Dict[str, Any], bool, str]] = []
            local_sync_updates: List[Tuple[Dict[str, Any], bool, str]] = []
            page_changed = False
            for row in target_rows:
                source_row = row.get("_source_row", row)
                if not isinstance(source_row, dict):
                    source_row = row

                shape_index = self._problem_sync_shape_index(row)
                if shape_index < 0 or shape_index >= len(shapes):
                    self._problem_sync_terminal_log(
                        "라벨 skip: shape_index 범위 벗어남 / "
                        f"{self._problem_sync_row_label(row)} / shapes={len(shapes)}"
                    )
                    continue

                shape = shapes[shape_index]
                if not isinstance(shape, dict):
                    self._problem_sync_terminal_log(
                        "라벨 skip: shape dict 아님 / "
                        f"{self._problem_sync_row_label(row)} / shape_type={type(shape).__name__}"
                    )
                    continue

                next_is_problem = bool(row.get("is_problem", False))
                next_reason = str(row.get("problem_reason", "") or "")
                if append_reason_entry is not None:
                    next_reason = self._append_problem_reason_entry(
                        str(shape.get("problem_reason", "") or ""),
                        append_reason_entry,
                        keep_problem_without_reason=bool(shape.get("is_problem", False)),
                    )
                    next_is_problem = self._reason_text_keeps_problem_flag(next_reason)
                elif remove_reason_entry is not None:
                    previous_reason = str(shape.get("problem_reason", "") or "")
                    next_reason, _removed = self._remove_reason_entry_line(previous_reason, remove_reason_entry)
                    next_is_problem = self._reason_text_keeps_problem_flag(next_reason)

                if not next_is_problem:
                    next_reason = ""

                current_is_problem = bool(shape.get("is_problem", False))
                current_reason = str(shape.get("problem_reason", "") or "")
                if current_is_problem == next_is_problem and current_reason == next_reason:
                    source_is_problem = bool(source_row.get("is_problem", False))
                    source_reason = str(source_row.get("problem_reason", "") or "")
                    if source_is_problem != current_is_problem or source_reason != current_reason:
                        local_sync_updates.append((source_row, current_is_problem, current_reason))
                        self._problem_sync_terminal_log(
                            "라벨 skip: 변경 없음, 로컬 동기화 적용 / "
                            f"{self._problem_sync_row_label(row)} / "
                            f"is_problem={current_is_problem} / reason={current_reason or '-'}"
                        )
                        continue
                    self._problem_sync_terminal_log(
                        "라벨 skip: 변경 없음 / "
                        f"{self._problem_sync_row_label(row)} / "
                        f"is_problem={current_is_problem} / reason={current_reason or '-'}"
                    )
                    continue

                shape["is_problem"] = next_is_problem
                shape["problem_reason"] = next_reason
                pending_updates.append((source_row, next_is_problem, next_reason))
                page_changed = True

            for source_row, next_is_problem, next_reason in local_sync_updates:
                source_row["is_problem"] = next_is_problem
                source_row["problem_reason"] = next_reason

            if not page_changed:
                self._problem_sync_terminal_log(f"페이지 skip: 변경된 라벨 없음 ({page_label})")
                continue

            save_jobs.append(
                {
                    "page_label": page_label,
                    "json_row": json_row,
                    "payload": payload,
                    "pending_updates": pending_updates,
                }
            )

        if not save_jobs:
            return updated_pages, failed_pages, []

        total_saves = len(save_jobs)
        worker_count = self._problem_sync_worker_count(total_saves)

        if worker_count <= 1:
            for index, job in enumerate(save_jobs, start=1):
                if progress_desc:
                    self._set_progress(progress_desc, index, total_saves)
                QApplication.processEvents()
                try:
                    self._problem_sync_write_payload_remote(
                        job["json_row"],
                        job["payload"],
                        loader=s3_loader,
                    )
                except Exception as exc:
                    page_label = str(job.get("page_label", "")).strip()
                    failed_pages.append(page_label)
                    self._set_recent_log(f"확인 필요 저장 실패 ({page_label}): {exc}")
                    continue

                self._problem_sync_cache_saved_payload(job["json_row"], job["payload"])
                for source_row, next_is_problem, next_reason in job["pending_updates"]:
                    source_row["is_problem"] = next_is_problem
                    source_row["problem_reason"] = next_reason
                updated_pages += 1
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        self._problem_sync_write_payload_remote,
                        job["json_row"],
                        job["payload"],
                        loader=s3_loader,
                    ): job
                    for job in save_jobs
                }
                completed = 0
                for future in concurrent.futures.as_completed(future_map):
                    completed += 1
                    if progress_desc:
                        self._set_progress(progress_desc, completed, total_saves)
                    QApplication.processEvents()

                    job = future_map[future]
                    page_label = str(job.get("page_label", "")).strip()
                    try:
                        future.result()
                    except Exception as exc:
                        failed_pages.append(page_label)
                        self._set_recent_log(f"확인 필요 저장 실패 ({page_label}): {exc}")
                        continue

                    self._problem_sync_cache_saved_payload(job["json_row"], job["payload"])
                    for source_row, next_is_problem, next_reason in job["pending_updates"]:
                        source_row["is_problem"] = next_is_problem
                        source_row["problem_reason"] = next_reason
                    updated_pages += 1

        return updated_pages, failed_pages, []

    def _reset_problem_by_reason_value(self, target_reason: str) -> None:
        if self._problem_sync_is_busy("확인 필요 초기화"):
            return
        reason_pattern = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s+.+$")
        visible_rows = self._visible_current_rows()
        reasons = sorted(
            {
                entry
                for row in visible_rows
                for entry in [
                    line.strip()
                    for line in str(row.get("problem_reason", "")).replace("\r\n", "\n").split("\n")
                ]
                if bool(row.get("is_problem", False)) and entry and reason_pattern.match(entry)
            }
        )
        if not reasons or target_reason not in reasons:
            QMessageBox.information(self, "안내", "선택한 problem_reason 항목이 없습니다.")
            self._set_recent_log("확인 필요 초기화 실패: 선택한 reason 항목이 없습니다")
            return

        changed_rows: List[Dict[str, Any]] = []
        for row in visible_rows:
            if not bool(row.get("is_problem", False)):
                continue
            current_reason = str(row.get("problem_reason", "") or "")
            _merged_reason, removed = self._remove_reason_entry_line(current_reason, target_reason)
            if removed:
                changed_rows.append(row)

        if not changed_rows:
            QMessageBox.information(self, "안내", "선택한 problem_reason으로 초기화할 항목이 없습니다.")
            self._set_recent_log("확인 필요 초기화 실패: reason 대상 항목이 없습니다")
            return

        updated_pages, failed_pages, mismatch_pages = self._sync_problem_fields_to_json(
            changed_rows,
            remove_reason_entry=target_reason,
            progress_desc="확인 필요 reason 초기화 중",
            require_snapshot_match=True,
            abort_on_snapshot_mismatch=True,
        )
        if mismatch_pages:
            self._show_problem_snapshot_mismatch_warning("확인 필요 초기화 중단", mismatch_pages)
            self._set_recent_log(f"확인 필요 reason 초기화 중단: 스냅샷 불일치 {len(mismatch_pages)}건")
            return

        self.center_panel.set_pages(self.current_label_rows)
        self._refresh_dashboard()
        self._set_recent_log(f"확인 필요 reason 초기화 완료: 수정 페이지 {updated_pages}건")
        if failed_pages:
            preview = ", ".join(failed_pages[:3])
            suffix = "" if len(failed_pages) <= 3 else " ..."
            self._set_recent_log(f"저장 실패 페이지 {len(failed_pages)}건 {preview}{suffix}")

    def _mark_problem_for_visible_rows(self) -> None:
        if self._problem_sync_is_busy("확인 필요 체크"):
            return
        visible_rows = self._visible_current_rows()
        if not visible_rows:
            QMessageBox.information(self, "안내", "확인 필요로 표시할 결과가 없습니다.")
            self._set_recent_log("확인 필요 체크 실패: 대상이 없습니다.")
            return

        target_rows = [
            {**row, "_source_row": row}
            for row in visible_rows
            if self._problem_sync_shape_index(row) >= 0
            and is_error_base_state(row.get("base_state"))
        ]
        if not target_rows:
            QMessageBox.information(self, "안내", "확인 필요로 저장할 라벨이 없습니다.")
            self._set_recent_log("확인 필요 체크 실패: 저장 가능한 라벨이 없습니다.")
            return

        reason, ok = QInputDialog.getText(self, "확인 필요 사유", "확인 필요 사유를 입력하세요")
        if not ok:
            self._set_recent_log("확인 필요 체크 취소")
            return

        reason = str(reason).strip()
        if not reason:
            QMessageBox.warning(self, "입력 필요", "확인 필요 사유는 비워둘 수 없습니다.")
            self._set_recent_log("확인 필요 체크 실패: 사유를 입력해 주세요.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {reason}"
        updated_pages, failed_pages, mismatch_pages = self._sync_problem_fields_to_json(
            target_rows,
            append_reason_entry=entry,
            progress_desc="확인 필요 체크 적용 중",
            require_snapshot_match=True,
            abort_on_snapshot_mismatch=True,
        )
        if mismatch_pages:
            self._show_problem_snapshot_mismatch_warning("확인 필요 체크 중단", mismatch_pages)
            self._set_recent_log(f"확인 필요 체크 중단: 스냅샷 불일치 {len(mismatch_pages)}건")
            return

        self.center_panel.set_pages(self.current_label_rows)
        self._refresh_dashboard()
        scope_name = "현재 필터 결과"
        self._set_recent_log(
            f"확인 필요 체크 완료: 범위={scope_name} / 수정 페이지 {updated_pages}건 / 대상 행 {len(target_rows)}건"
        )
        if failed_pages:
            preview = ", ".join(failed_pages[:3])
            suffix = "" if len(failed_pages) <= 3 else " ..."
            self._set_recent_log(f"충돌로 제외된 페이지 {len(failed_pages)}건 {preview}{suffix}")
            QMessageBox.warning(
                self,
                "확인 필요 일부 실패",
                f"일부 페이지는 저장하지 못해 화면에 반영되지 않았습니다.\n{preview}{suffix}",
            )

    def _reset_problem_for_visible_rows(self) -> None:
        if self._problem_sync_is_busy("확인 필요 초기화"):
            return
        visible_rows = self._visible_current_rows()
        if not visible_rows:
            QMessageBox.information(self, "안내", "현재 필터 결과가 없습니다.")
            self._set_recent_log("확인 필요 필터 초기화 실패: 현재 필터 결과가 없습니다.")
            return

        target_rows = [
            {**row, "is_problem": False, "problem_reason": "", "_source_row": row}
            for row in visible_rows
            if bool(row.get("is_problem", False))
        ]
        if not target_rows:
            QMessageBox.information(self, "안내", "현재 필터 결과에서 초기화할 항목이 없습니다.")
            self._set_recent_log("확인 필요 필터 초기화 실패: 대상 항목이 없습니다.")
            return

        updated_pages, failed_pages, mismatch_pages = self._sync_problem_fields_to_json(
            target_rows,
            progress_desc="확인 필요 필터 초기화 중",
            require_snapshot_match=True,
            abort_on_snapshot_mismatch=True,
        )
        if mismatch_pages:
            self._show_problem_snapshot_mismatch_warning("확인 필요 초기화 중단", mismatch_pages)
            self._set_recent_log(f"확인 필요 필터 초기화 중단: 스냅샷 불일치 {len(mismatch_pages)}건")
            return
        self.center_panel.set_pages(self.current_label_rows)
        self._refresh_dashboard()
        self._set_recent_log(f"확인 필요 필터 초기화 완료: 수정 페이지 {updated_pages}건")
        if failed_pages:
            preview = ", ".join(failed_pages[:3])
            suffix = "" if len(failed_pages) <= 3 else " ..."
            self._set_recent_log(f"저장 제외 페이지 {len(failed_pages)}건 {preview}{suffix}")
            QMessageBox.warning(
                self,
                "확인 필요 초기화 일부 실패",
                f"일부 페이지는 초기화하지 못했습니다.\n{preview}{suffix}",
            )

    def _reset_problem_for_all_rows(self) -> None:
        if self._problem_sync_is_busy("확인 필요 초기화"):
            return
        target_rows = [
            {**row, "is_problem": False, "problem_reason": "", "_source_row": row}
            for row in self.current_label_rows
            if bool(row.get("is_problem", False))
        ]
        if not target_rows:
            QMessageBox.information(self, "안내", "초기화할 확인 필요 항목이 없습니다.")
            self._set_recent_log("확인 필요 전체 초기화 실패: 대상이 없습니다.")
            return

        updated_pages, failed_pages, _mismatch_pages = self._sync_problem_fields_to_json(
            target_rows,
            progress_desc="확인 필요 전체 초기화 중",
        )
        self.center_panel.set_pages(self.current_label_rows)
        self._refresh_dashboard()
        self._set_recent_log(f"확인 필요 전체 초기화 완료: 수정 페이지 {updated_pages}건")
        if failed_pages:
            preview = ", ".join(failed_pages[:3])
            suffix = "" if len(failed_pages) <= 3 else " ..."
            self._set_recent_log(f"저장 제외 페이지 {len(failed_pages)}건 {preview}{suffix}")
            QMessageBox.warning(
                self,
                "확인 필요 전체 초기화 일부 실패",
                f"일부 페이지는 초기화하지 못했습니다.\n{preview}{suffix}",
            )
