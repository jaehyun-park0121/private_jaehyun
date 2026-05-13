"""
PP-DocLayout 레이아웃 도구 (탭 GUI).

탭1 — DLA 추출
- 스킵 폴더: table_extract, table_qa
- PNG 옆 동일 파일명 JSON 저장 (배열 [{label, score, box}])

탭2 — JSON 변환
- 출력 경로: 출력 상위 폴더 아래에 입력 폴더 이름과 같은 하위 폴더를 만든다.
  예) 출력 상위 `validation`, 입력 `…\\split\\test` → `validation\\test\\…`.
- 동일 루트의 PNG + DLA 배열 JSON을 읽어 Labelme 형식으로 변환
- shapes[].label 은 업로드 호환을 위해 대문자화(str.upper)
- imageWidth/Height는 PIL 로 실제 PNG 크기 사용

모델 디렉터리는 한글 경로 시 PaddleInference 오류가 나므로 영문 경로 권장.
"""

from __future__ import annotations

import os

import PyQt5

# Qt 플랫폼 플러그인 경로 명시 (qwindows.dll 탐색 실패 방지)
os.environ.setdefault(
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforms"),
)

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# PaddleOCR inference.yml label_list 와 동일한 문자열이 label 필드로 출력됨 (25종).
SKIP_FOLDER_NAMES: frozenset[str] = frozenset({"table_extract", "table_qa"})
DEFAULT_MODEL_NAME: str = "PP-DocLayoutV3"
# PaddleInference 한글 경로 이슈 회피용 기본값 (robocopy 등으로 복사한 영문 경로)
DEFAULT_MODEL_DIR: str = r"C:\paddle_test\PP-DocLayoutV3"
DEFAULT_LAYOUT_THRESHOLD: float = 0.5
DEFAULT_LAYOUT_UNCLIP_RATIO: float = 1.0
LAYOUT_MERGE_BBOX_MODES: tuple[str, ...] = ("union", "large", "small")


@dataclass(frozen=True)
class RunSummary:
    """배치 실행 요약."""

    written: int
    skipped_existing_json: int
    failed: int


@dataclass(frozen=True)
class ConvertSummary:
    """JSON 변환 배치 요약."""

    written_pairs: int
    skipped_existing: int
    skipped_no_json: int
    skipped_invalid: int
    failed: int


def validate_box_coords(item: dict[str, Any], index: int) -> tuple[float, float, float, float]:
    """DLA 배열 항목에서 사각형 좌표를 검증·추출한다."""
    box = item.get("box")
    if not isinstance(box, dict):
        raise ValueError(f"항목 #{index}: 유효한 'box' 객체가 없습니다.")

    required = ("xmin", "ymin", "xmax", "ymax")
    missing = [key for key in required if key not in box]
    if missing:
        raise ValueError(f"항목 #{index}: box 에 키 누락: {', '.join(missing)}")

    return (
        float(box["xmin"]),
        float(box["ymin"]),
        float(box["xmax"]),
        float(box["ymax"]),
    )


def convert_layout_array_to_labelme(
    data: list[dict[str, Any]],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    """
    DLA 배열 JSON 을 Labelme 호환 단일 문서 JSON 으로 변환한다.
    shapes[].label 은 업로드 규격에 맞추어 ASCII 범위는 대문자로 통일한다.
    """
    shapes: list[dict[str, Any]] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"항목 #{i}: 객체가 아닙니다.")
        if "label" not in item:
            raise ValueError(f"항목 #{i}: 'label' 이 없습니다.")

        xmin, ymin, xmax, ymax = validate_box_coords(item, i)
        label_val = item["label"]
        shapes.append(
            {
                "label": str(label_val).upper(),
                "points": [[xmin, ymin], [xmax, ymax]],
                "group_id": "",
                "is_problem": None,
                "problem_reason": None,
                "shape_type": "rectangle",
                "latex": "",
                "result": None,
                "failedReason": None,
                "flags": {"text": ""},
                "attributes": None,
            }
        )

    return {
        "version": "",
        "flags": {},
        "shapes": shapes,
        "imagePath": "",
        "imageData": None,
        "imageWidth": image_width,
        "imageHeight": image_height,
    }


def read_png_size(path: Path) -> tuple[int, int]:
    """PNG 실제 픽셀 크기 (width, height)."""
    from PIL import Image

    with Image.open(path) as im:
        w, h = im.size
    return int(w), int(h)


def _is_under_skipped_folder(relative_path: Path, skip_names: frozenset[str]) -> bool:
    """PNG 경로(파일명 제외)에 스킵 폴더명이 포함되는지 확인한다."""
    parts = relative_path.parts
    if len(parts) <= 1:
        return False
    return any(p in skip_names for p in parts[:-1])


def collect_png_paths(root: Path) -> list[Path]:
    """루트 이하 PNG 목록을 수집한다. 스킵 폴더 하위는 제외한다."""
    root = root.resolve()
    pngs: list[Path] = []
    for path in root.rglob("*.png"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if _is_under_skipped_folder(rel, SKIP_FOLDER_NAMES):
            continue
        pngs.append(path)
    return sorted(pngs)


def _prediction_to_layout_items(result_obj: Any) -> list[dict[str, Any]]:
    """PaddleOCR LayoutDetection 단일 결과 객체에서 레이아웃 항목 리스트를 만든다."""
    raw_json = getattr(result_obj, "json", None)
    if raw_json is None:
        return []
    if callable(raw_json):
        raw_json = raw_json()
    if not isinstance(raw_json, dict):
        return []

    block = raw_json.get("res", raw_json)
    if not isinstance(block, dict):
        return []

    boxes = block.get("boxes", [])
    if not isinstance(boxes, list):
        return []

    items: list[dict[str, Any]] = []
    for box in boxes:
        if not isinstance(box, dict):
            continue
        coord = box.get("coordinate")
        if coord is None:
            coord = box.get("bbox")
        if not isinstance(coord, (list, tuple)) or len(coord) < 4:
            continue
        x1, y1, x2, y2 = coord[0], coord[1], coord[2], coord[3]
        label = box.get("label", "")
        score = box.get("score", 0.0)
        items.append(
            {
                "label": label,
                "score": float(score),
                "box": {
                    "xmin": int(round(float(x1))),
                    "ymin": int(round(float(y1))),
                    "xmax": int(round(float(x2))),
                    "ymax": int(round(float(y2))),
                },
            }
        )
    return items


class LayoutExtractWorker(QObject):
    """백그라운드에서 레이아웃 검출 및 JSON 저장."""

    log_line = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        root_dir: Path,
        model_name: str = DEFAULT_MODEL_NAME,
        model_dir: str | None = None,
        threshold: float = DEFAULT_LAYOUT_THRESHOLD,
        layout_nms: bool = False,
        layout_unclip_ratio: float = DEFAULT_LAYOUT_UNCLIP_RATIO,
        layout_merge_bboxes_mode: str = "union",
        enable_hpi: bool = False,
    ) -> None:
        super().__init__()
        self._root_dir = root_dir.resolve()
        self._model_name = model_name
        self._model_dir = model_dir.strip() if model_dir else None
        self._threshold = threshold
        self._layout_nms = layout_nms
        self._layout_unclip_ratio = layout_unclip_ratio
        self._layout_merge_bboxes_mode = layout_merge_bboxes_mode
        self._enable_hpi = enable_hpi
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            summary = self._run_inner()
            self.finished_ok.emit(summary)
        except Exception as exc:  # noqa: BLE001 — GUI에서 사용자에게 전달
            self.failed.emit(str(exc))

    def _run_inner(self) -> RunSummary:
        # 무거운 import는 워커 시작 시점에만 수행
        from paddleocr import LayoutDetection

        png_paths = collect_png_paths(self._root_dir)
        total_png = len(png_paths)
        self.log_line.emit(f"처리 대상 PNG(스킵 폴더 제외): {total_png}개")

        to_predict: list[Path] = []
        skipped_existing = 0
        for png in png_paths:
            json_path = png.with_suffix(".json")
            if json_path.is_file():
                skipped_existing += 1
                self.log_line.emit(f"건너뜀(JSON 존재): {png.name}")
                continue
            to_predict.append(png)

        self.log_line.emit(f"신규 추출 대상: {len(to_predict)}개 / 기존 JSON 스킵: {skipped_existing}개")

        layout_kw: dict[str, Any] = {
            "model_name": self._model_name,
            "threshold": self._threshold,
            "layout_nms": self._layout_nms,
            "layout_unclip_ratio": self._layout_unclip_ratio,
            "layout_merge_bboxes_mode": self._layout_merge_bboxes_mode,
            "enable_hpi": self._enable_hpi,
        }
        if self._model_dir:
            layout_kw["model_dir"] = self._model_dir
            self.log_line.emit(f"모델 디렉터리: {self._model_dir}")
        self.log_line.emit(
            "파라미터: "
            f"threshold={self._threshold}, layout_nms={self._layout_nms}, "
            f"unclip={self._layout_unclip_ratio}, merge={self._layout_merge_bboxes_mode}, "
            f"enable_hpi={self._enable_hpi}"
        )
        model = LayoutDetection(**layout_kw)
        written = 0
        failed = 0
        total_run = len(to_predict)

        for idx, png_path in enumerate(to_predict, start=1):
            if self._cancel_requested:
                self.log_line.emit("사용자 요청으로 중단되었습니다.")
                break
            self.progress.emit(idx, total_run)
            json_path = png_path.with_suffix(".json")
            try:
                output = model.predict(
                    str(png_path),
                    batch_size=1,
                    threshold=self._threshold,
                    layout_nms=self._layout_nms,
                    layout_unclip_ratio=self._layout_unclip_ratio,
                    layout_merge_bboxes_mode=self._layout_merge_bboxes_mode,
                )
                items: list[dict[str, Any]] = []
                for res in output:
                    items.extend(_prediction_to_layout_items(res))

                json_path.parent.mkdir(parents=True, exist_ok=True)
                with json_path.open("w", encoding="utf-8") as fp:
                    json.dump(items, fp, ensure_ascii=False, indent=2)

                written += 1
                self.log_line.emit(f"저장: {json_path.name} ({len(items)}개 박스)")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.log_line.emit(f"실패: {png_path} — {exc}")

        return RunSummary(
            written=written,
            skipped_existing_json=skipped_existing,
            failed=failed,
        )


class LayoutJsonConvertWorker(QObject):
    """
    DLA 배열 JSON → Labelme 형식 변환 및 PNG 복사.

    output_root 는 (출력 상위 폴더 / 입력 루트 폴더명) 형태의 최종 저장 디렉터리이다.
    """

    log_line = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        skip_existing_output: bool,
    ) -> None:
        super().__init__()
        self._input_root = input_root.resolve()
        self._output_root = output_root.resolve()
        self._skip_existing_output = skip_existing_output
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            summary = self._run_inner()
            self.finished_ok.emit(summary)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _run_inner(self) -> ConvertSummary:
        png_paths = collect_png_paths(self._input_root)
        total = len(png_paths)
        self.log_line.emit(f"변환 대상 PNG(스킵 폴더 제외): {total}개")
        self.log_line.emit(f"실제 출력 폴더: {self._output_root}")

        written_pairs = 0
        skipped_existing = 0
        skipped_no_json = 0
        skipped_invalid = 0
        failed = 0

        for idx, png_path in enumerate(png_paths, start=1):
            if self._cancel_requested:
                self.log_line.emit("사용자 요청으로 중단되었습니다.")
                break

            self.progress.emit(idx, total)
            rel = png_path.relative_to(self._input_root)
            out_png = self._output_root / rel
            out_json = out_png.with_suffix(".json")
            src_json = png_path.with_suffix(".json")

            if self._skip_existing_output and out_png.is_file() and out_json.is_file():
                skipped_existing += 1
                self.log_line.emit(f"건너뜀(출력 존재): {rel}")
                continue

            if not src_json.is_file():
                skipped_no_json += 1
                self.log_line.emit(f"건너뜀(DLA JSON 없음): {png_path.name}")
                continue

            try:
                raw_text = src_json.read_text(encoding="utf-8")
                raw_data = json.loads(raw_text)
            except Exception as exc:  # noqa: BLE001
                skipped_invalid += 1
                self.log_line.emit(f"건너뜀(JSON 파싱 실패): {src_json.name} — {exc}")
                continue

            if not isinstance(raw_data, list):
                skipped_invalid += 1
                self.log_line.emit(f"건너뜀(배열 아님): {src_json.name}")
                continue

            try:
                img_w, img_h = read_png_size(png_path)
                labelme_doc = convert_layout_array_to_labelme(raw_data, img_w, img_h)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.log_line.emit(f"실패: {rel} — {exc}")
                continue

            try:
                out_png.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(png_path, out_png)
                out_json.write_text(
                    json.dumps(labelme_doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                written_pairs += 1
                self.log_line.emit(
                    f"저장: {rel} (shapes {len(labelme_doc['shapes'])}, {img_w}x{img_h})"
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.log_line.emit(f"실패(쓰기): {rel} — {exc}")

        return ConvertSummary(
            written_pairs=written_pairs,
            skipped_existing=skipped_existing,
            skipped_no_json=skipped_no_json,
            skipped_invalid=skipped_invalid,
            failed=failed,
        )


class DlaExtractTab(QWidget):
    """탭1: DLA 추출."""

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: LayoutExtractWorker | None = None

        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("예: ...\\3. data\\2. train")

        browse_btn = QPushButton("폴더 선택…")
        browse_btn.clicked.connect(self._pick_folder)

        self._model_edit = QLineEdit(DEFAULT_MODEL_NAME)

        self._model_dir_edit = QLineEdit(DEFAULT_MODEL_DIR)
        self._model_dir_edit.setPlaceholderText(
            r"inference.json 이 있는 폴더 (영문 경로 권장, 예: C:\paddle_test\PP-DocLayoutV3)"
        )
        model_dir_browse = QPushButton("모델 폴더…")
        model_dir_browse.clicked.connect(self._pick_model_dir)

        self._start_btn = QPushButton("시작")
        self._start_btn.clicked.connect(self._start_run)
        self._stop_btn = QPushButton("중단")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_run)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("루트 폴더"))
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("모델명"))
        model_row.addWidget(self._model_edit, stretch=1)

        model_dir_row = QHBoxLayout()
        model_dir_row.addWidget(QLabel("모델 디렉터리"))
        model_dir_row.addWidget(self._model_dir_edit, stretch=1)
        model_dir_row.addWidget(model_dir_browse)

        param_box = QGroupBox("모델 파라미터 (LayoutDetection)")
        self._threshold_edit = QLineEdit(str(DEFAULT_LAYOUT_THRESHOLD))
        self._threshold_edit.setPlaceholderText("0.0 ~ 1.0, 낮출수록 약한 검출 포함")
        self._nms_cb = QCheckBox("layout_nms (겹치는 박스 후처리)")
        self._nms_cb.setChecked(False)
        self._hpi_cb = QCheckBox("enable_hpi — OpenVINO 가속 (Intel 환경 권장, 첫 실행 시 변환 1~2분 소요)")
        self._hpi_cb.setChecked(False)
        self._unclip_edit = QLineEdit(str(DEFAULT_LAYOUT_UNCLIP_RATIO))
        self._unclip_edit.setPlaceholderText("박스 확대 비율 (> 0)")
        self._merge_combo = QComboBox()
        self._merge_combo.addItems(list(LAYOUT_MERGE_BBOX_MODES))
        self._merge_combo.setCurrentIndex(0)

        p_row1 = QHBoxLayout()
        p_row1.addWidget(QLabel("threshold"))
        p_row1.addWidget(self._threshold_edit, stretch=1)
        p_row2 = QHBoxLayout()
        p_row2.addWidget(self._nms_cb)
        p_row2b = QHBoxLayout()
        p_row2b.addWidget(self._hpi_cb)
        p_row3 = QHBoxLayout()
        p_row3.addWidget(QLabel("layout_unclip_ratio"))
        p_row3.addWidget(self._unclip_edit, stretch=1)
        p_row4 = QHBoxLayout()
        p_row4.addWidget(QLabel("박스 병합 모드"))
        p_row4.addWidget(self._merge_combo, stretch=1)

        param_inner = QVBoxLayout()
        param_inner.addLayout(p_row1)
        param_inner.addLayout(p_row2)
        param_inner.addLayout(p_row2b)
        param_inner.addLayout(p_row3)
        param_inner.addLayout(p_row4)
        param_box.setLayout(param_inner)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(1)
        self._progress.setValue(0)

        info_box = QGroupBox("안내 · 스킵 규칙")
        info_label = QLabel(
            "• PaddleInference 는 모델 경로에 한글이 있으면 로딩 실패(parse_error.101)할 수 있습니다. "
            "모델 디렉터리는 영문 경로로 두세요.\n"
            "• 하위 폴더 이름이 table_extract 또는 table_qa 인 경로는 처리하지 않습니다.\n"
            "• PNG와 동일한 이름의 JSON이 이미 있으면 해당 PNG는 건너뜁니다.\n"
            "• 출력 형식은 레이아웃 박스 배열 [{label, score, box}] 입니다.\n"
            "• 모델 파라미터: 놓치는 요소가 많으면 threshold 를 0.3~0.45 로 낮춰 보세요.\n"
            "• enable_hpi: Intel 환경에서 OpenVINO 가속 활성화. 첫 실행 시 변환 시간이 추가됩니다."
        )
        info_label.setWordWrap(True)
        info_inner = QVBoxLayout()
        info_inner.addWidget(info_label)
        info_box.setLayout(info_inner)

        self._log = QTextEdit()
        self._log.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addLayout(folder_row)
        layout.addLayout(model_row)
        layout.addLayout(model_dir_row)
        layout.addWidget(param_box)
        layout.addLayout(btn_row)
        layout.addWidget(self._progress)
        layout.addWidget(info_box)
        layout.addWidget(QLabel("로그"))
        layout.addWidget(self._log, stretch=1)

        self.setLayout(layout)

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "루트 폴더 선택")
        if path:
            self._folder_edit.setText(path)

    def _pick_model_dir(self) -> None:
        """모델 가중치 폴더 선택 (inference.json 위치)."""
        path = QFileDialog.getExistingDirectory(self, "모델 디렉터리 선택 (inference.json)")
        if path:
            self._model_dir_edit.setText(path)

    def _append_log(self, text: str) -> None:
        self._log.append(text)

    def _on_progress(self, current: int, total: int) -> None:
        """추출 진행률 표시."""
        safe_total = max(total, 1)
        self._progress.setMaximum(safe_total)
        self._progress.setValue(min(max(current, 0), safe_total))

    def _start_run(self) -> None:
        folder = self._folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "경로 없음", "루트 폴더를 선택하거나 입력하세요.")
            return

        root_path = Path(folder)
        if not root_path.is_dir():
            QMessageBox.warning(self, "경로 오류", "존재하는 폴더 경로인지 확인하세요.")
            return

        model_name = self._model_edit.text().strip() or DEFAULT_MODEL_NAME

        model_dir_raw = self._model_dir_edit.text().strip()
        model_dir_for_worker: str | None = None
        if model_dir_raw:
            model_path = Path(model_dir_raw)
            if not model_path.is_dir():
                QMessageBox.warning(
                    self,
                    "모델 경로 오류",
                    "모델 디렉터리가 존재하지 않습니다.\n영문 경로로 복사했는지 확인하세요.",
                )
                return
            infer_json = model_path / "inference.json"
            if not infer_json.is_file():
                QMessageBox.warning(
                    self,
                    "모델 파일 없음",
                    "선택한 폴더에 inference.json 이 없습니다.\nPP-DocLayoutV3 폴더를 지정했는지 확인하세요.",
                )
                return
            model_dir_for_worker = str(model_path.resolve())

        threshold_raw = self._threshold_edit.text().strip()
        try:
            threshold_val = float(threshold_raw) if threshold_raw else DEFAULT_LAYOUT_THRESHOLD
        except ValueError:
            QMessageBox.warning(self, "파라미터 오류", "threshold 는 숫자여야 합니다.")
            return
        if not 0.0 <= threshold_val <= 1.0:
            QMessageBox.warning(self, "파라미터 오류", "threshold 는 0.0 ~ 1.0 사이여야 합니다.")
            return

        unclip_raw = self._unclip_edit.text().strip()
        try:
            unclip_val = float(unclip_raw) if unclip_raw else DEFAULT_LAYOUT_UNCLIP_RATIO
        except ValueError:
            QMessageBox.warning(self, "파라미터 오류", "layout_unclip_ratio 는 숫자여야 합니다.")
            return
        if unclip_val <= 0.0:
            QMessageBox.warning(self, "파라미터 오류", "layout_unclip_ratio 는 0보다 커야 합니다.")
            return

        merge_mode = self._merge_combo.currentText()
        if merge_mode not in LAYOUT_MERGE_BBOX_MODES:
            QMessageBox.warning(self, "파라미터 오류", "박스 병합 모드를 확인하세요.")
            return

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._log.clear()
        self._append_log(f"루트: {root_path}")
        self._append_log(f"모델: {model_name}")
        if model_dir_for_worker:
            self._append_log(f"모델 디렉터리: {model_dir_for_worker}")
        else:
            self._append_log("모델 디렉터리: (미지정 → PaddleX 기본 캐시, 한글 경로면 실패할 수 있음)")
        enable_hpi_val = self._hpi_cb.isChecked()
        self._append_log(
            f"파라미터: threshold={threshold_val}, layout_nms={self._nms_cb.isChecked()}, "
            f"unclip={unclip_val}, merge={merge_mode}, enable_hpi={enable_hpi_val}"
        )
        if enable_hpi_val:
            self._append_log("※ enable_hpi=True: 첫 실행 시 OpenVINO 변환으로 1~2분 더 걸릴 수 있습니다.")

        self._thread = QThread()
        self._worker = LayoutExtractWorker(
            root_path,
            model_name=model_name,
            model_dir=model_dir_for_worker,
            threshold=threshold_val,
            layout_nms=self._nms_cb.isChecked(),
            layout_unclip_ratio=unclip_val,
            layout_merge_bboxes_mode=merge_mode,
            enable_hpi=enable_hpi_val,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        # 종료 시 스레드 정리
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _stop_run(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
            self._append_log("중단 요청을 보냈습니다. 현재 파일 처리 후 멈춥니다.")

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setMaximum(1)
        self._progress.setValue(0)

    def _on_finished(self, summary: RunSummary) -> None:
        msg = (
            f"완료 — 저장 {summary.written}개, "
            f"기존 JSON 스킵 {summary.skipped_existing_json}개, "
            f"실패 {summary.failed}개"
        )
        self._append_log(msg)
        QMessageBox.information(self, "완료", msg)

    def _on_failed(self, message: str) -> None:
        self._append_log(f"오류: {message}")
        QMessageBox.critical(self, "오류", message)


class LayoutConvertTab(QWidget):
    """탭2: DLA 배열 JSON → Labelme 형식 + PNG 복사."""

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: LayoutJsonConvertWorker | None = None

        self._in_edit = QLineEdit()
        self._in_edit.setPlaceholderText("DLA 추출이 끝난 루트 (PNG + 동명 JSON)")

        in_btn = QPushButton("입력 폴더…")
        in_btn.clicked.connect(self._pick_input)

        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText(
            "출력 상위 폴더 (예: validation → 결과는 validation/<입력폴더명>/ 아래)"
        )

        out_btn = QPushButton("출력 폴더…")
        out_btn.clicked.connect(self._pick_output)

        self._skip_existing_cb = QCheckBox("출력에 PNG·JSON 쌍이 이미 있으면 건너뛰기")
        self._skip_existing_cb.setChecked(True)

        self._start_btn = QPushButton("변환 시작")
        self._start_btn.clicked.connect(self._start_run)
        self._stop_btn = QPushButton("중단")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_run)

        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("입력 루트"))
        in_row.addWidget(self._in_edit, stretch=1)
        in_row.addWidget(in_btn)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("출력 상위 폴더"))
        out_row.addWidget(self._out_edit, stretch=1)
        out_row.addWidget(out_btn)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(1)
        self._progress.setValue(0)

        info_box = QGroupBox("안내")
        info_label = QLabel(
            "• 입력 루트는 DLA 추출 탭과 동일하게 두면 됩니다. PNG 옆의 배열 JSON[{label, score, box}]을 읽습니다.\n"
            "• 출력 상위 폴더 아래에 입력 폴더 이름과 같은 하위 폴더가 만들어집니다. 예: 출력 validation + 입력 …\\\\test → …\\\\validation\\\\test\\\\...\n"
            "• 그 하위에 입력과 같은 상대 경로로 PNG를 복사하고, 동일 파일명의 Labelme 형식 JSON을 씁니다.\n"
            "• 이미지 크기(imageWidth/Height)는 PIL로 실제 PNG 크기를 사용합니다.\n"
            "• shapes[].label 은 업로드 호환을 위해 대문자로 바꿉니다.\n"
            "• table_extract, table_qa 하위는 처리하지 않습니다.\n"
            "• 최종 출력 경로(출력 상위\\\\입력 폴더명)가 입력 루트의 하위면 안 됩니다."
        )
        info_label.setWordWrap(True)
        info_inner = QVBoxLayout()
        info_inner.addWidget(info_label)
        info_box.setLayout(info_inner)

        self._log = QTextEdit()
        self._log.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addLayout(in_row)
        layout.addLayout(out_row)
        layout.addWidget(self._skip_existing_cb)
        layout.addLayout(btn_row)
        layout.addWidget(self._progress)
        layout.addWidget(info_box)
        layout.addWidget(QLabel("로그"))
        layout.addWidget(self._log, stretch=1)
        self.setLayout(layout)

    def _pick_input(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "입력 루트 선택")
        if path:
            self._in_edit.setText(path)

    def _pick_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "출력 상위 폴더 선택")
        if path:
            self._out_edit.setText(path)

    def _append_log(self, text: str) -> None:
        self._log.append(text)

    def _on_progress(self, current: int, total: int) -> None:
        safe_total = max(total, 1)
        self._progress.setMaximum(safe_total)
        self._progress.setValue(min(max(current, 0), safe_total))

    @staticmethod
    def _is_descendant(child: Path, ancestor: Path) -> bool:
        """child 가 ancestor 의 하위 경로인지 (동일 제외)."""
        try:
            child.resolve().relative_to(ancestor.resolve())
            return True
        except ValueError:
            return False

    def _start_run(self) -> None:
        in_raw = self._in_edit.text().strip()
        out_raw = self._out_edit.text().strip()
        if not in_raw or not out_raw:
            QMessageBox.warning(self, "경로 없음", "입력 루트와 출력 상위 폴더를 모두 지정하세요.")
            return

        input_root = Path(in_raw)
        output_root = Path(out_raw)
        if not input_root.is_dir():
            QMessageBox.warning(self, "경로 오류", "입력 루트가 존재하는 폴더인지 확인하세요.")
            return

        in_res = input_root.resolve()
        out_parent = output_root.resolve()
        effective_output = out_parent / in_res.name

        if in_res == out_parent:
            QMessageBox.warning(
                self,
                "경로 오류",
                "출력 상위 폴더는 입력 루트와 같은 경로일 수 없습니다.",
            )
            return
        if in_res == effective_output:
            QMessageBox.warning(self, "경로 오류", "출력 경로가 입력과 같습니다. 다른 출력 상위 폴더를 지정하세요.")
            return
        if self._is_descendant(out_parent, in_res):
            QMessageBox.warning(
                self,
                "경로 오류",
                "출력 상위 폴더가 입력 루트의 하위면 안 됩니다.",
            )
            return
        if self._is_descendant(effective_output, in_res):
            QMessageBox.warning(
                self,
                "경로 오류",
                f"최종 출력 폴더가 입력 루트 안에 들어갑니다:\n{effective_output}\n"
                "복사본이 다시 입력으로 잡힐 수 있어 중단합니다.",
            )
            return

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._log.clear()
        self._append_log(f"입력 루트: {in_res}")
        self._append_log(f"출력 상위: {out_parent}")
        self._append_log(f"실제 출력 폴더: {effective_output}")

        self._thread = QThread()
        self._worker = LayoutJsonConvertWorker(
            in_res,
            effective_output,
            skip_existing_output=self._skip_existing_cb.isChecked(),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _stop_run(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
            self._append_log("중단 요청을 보냈습니다. 현재 파일 처리 후 멈춥니다.")

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setMaximum(1)
        self._progress.setValue(0)

    def _on_finished(self, summary: ConvertSummary) -> None:
        msg = (
            f"완료 — 쌍 저장 {summary.written_pairs}개, "
            f"출력 스킵 {summary.skipped_existing}개, "
            f"DLA JSON 없음 {summary.skipped_no_json}개, "
            f"형식 오류 스킵 {summary.skipped_invalid}개, "
            f"실패 {summary.failed}개"
        )
        self._append_log(msg)
        QMessageBox.information(self, "완료", msg)

    def _on_failed(self, message: str) -> None:
        self._append_log(f"오류: {message}")
        QMessageBox.critical(self, "오류", message)


class MainWindow(QWidget):
    """탭 통합 메인 창."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PP-DocLayout 레이아웃 도구")
        self.resize(760, 580)

        tabs = QTabWidget()
        tabs.addTab(DlaExtractTab(), "DLA 추출")
        tabs.addTab(LayoutConvertTab(), "JSON 변환")

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        self.setLayout(layout)


def main(argv: Iterable[str] | None = None) -> int:
    """애플리케이션 진입점."""
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("PP-DocLayout 레이아웃 도구")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
