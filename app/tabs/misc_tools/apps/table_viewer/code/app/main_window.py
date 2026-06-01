"""메인 윈도우 — 패널 조립 및 시그널 배선."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .io_utils import (
    ImageEntry,
    LocalBackend,
    S3Backend,
    S3BackendError,
    S3Config,
    SSHBackend,
    SSHBackendError,
    SSHConfig,
    StorageBackend,
    StorageBackendError,
    parse_s3_path,
)
from .widgets.file_panel import FilePanel
from .widgets.image_panel import ImagePanel
from .widgets.review_panel import ReviewPanel


DEFAULT_THREE_PANEL_SPLITTER_SIZES = [390, 700, 510]


class DetachableWindow(QDialog):
    """패널을 독립 창으로 띄우기 위한 다이얼로그."""

    def __init__(self, title: str, widget: QWidget, parent=None, header_buttons: list = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 900)
        self._widget = widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 헤더 추가 (버튼이 있는 경우)
        if header_buttons:
            header = self._build_header(title, header_buttons)
            layout.addWidget(header)

        layout.addWidget(widget)

    def _build_header(self, title: str, buttons: list) -> QFrame:
        """분리된 창의 헤더 생성."""
        frame = QFrame()
        frame.setObjectName("darkHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("darkTitle")
        layout.addWidget(title_label)
        layout.addStretch()

        for btn_config in buttons:
            btn = QPushButton(btn_config.get("text", ""))
            btn.setObjectName("headerActionBtn")
            if "tooltip" in btn_config:
                btn.setToolTip(btn_config["tooltip"])
            if "checkable" in btn_config:
                btn.setCheckable(btn_config["checkable"])
            if "checked" in btn_config:
                btn.setChecked(btn_config["checked"])
            if "callback" in btn_config:
                if btn_config.get("checkable"):
                    btn.toggled.connect(btn_config["callback"])
                else:
                    btn.clicked.connect(btn_config["callback"])
            layout.addWidget(btn)

        return frame

    def closeEvent(self, event):
        """창이 닫힐 때 부모 윈도우에 알림."""
        super().closeEvent(event)


class TablePresenceWorker(QObject):
    progress = pyqtSignal(int, int, object)
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, backend: StorageBackend, entries: list[ImageEntry]):
        super().__init__()
        self._backend = backend
        self._entries = list(entries)

    def run(self):
        try:
            resolved = self._backend.resolve_table_presence(
                self._entries,
                progress_callback=lambda done, total, entry: self.progress.emit(done, total, entry),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(resolved)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("테이블 검수 뷰어")
        self.resize(1700, 960)

        self.backend: Optional[StorageBackend] = None
        self.current_entry: Optional[ImageEntry] = None
        self.data: Optional[dict] = None
        self.shapes: list[dict] = []
        self.current_shape_index: int = -1
        self._table_filter_thread: Optional[QThread] = None
        self._table_filter_worker: Optional[TablePresenceWorker] = None
        self._table_filter_progress: Optional[QProgressDialog] = None
        self._focus_mode_enabled = False
        self._focus_mode_saved_splitter_sizes: Optional[list[int]] = None
        self._focus_mode_saved_filters: Optional[dict[str, bool]] = None

        # 분리된 창 관리
        self._detached_image_window: Optional[DetachableWindow] = None
        self._detached_review_window: Optional[DetachableWindow] = None
        self._image_panel_saved_sizes: Optional[list[int]] = None
        self._review_panel_saved_sizes: Optional[list[int]] = None

        self._build_ui()
        self._wire_signals()
        self._install_shortcuts()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        root.addWidget(self._build_header())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.file_panel = FilePanel()
        self.image_panel = ImagePanel()
        self.review_panel = ReviewPanel()
        self.splitter.addWidget(self.file_panel)
        self.splitter.addWidget(self.image_panel)
        self.splitter.addWidget(self.review_panel)
        self.splitter.setCollapsible(0, True)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 6)
        self.splitter.setStretchFactor(2, 4)
        self.splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        root.addWidget(self.splitter, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_status("대기 중: 좌측에서 입력 모드를 선택하세요.")

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("darkHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        title = QLabel("테이블 검수 뷰어")
        title.setObjectName("darkTitle")
        layout.addWidget(title)

        source_tag = QLabel("Source")
        source_tag.setObjectName("infoTag")
        layout.addWidget(source_tag)

        source_frame = QFrame()
        source_frame.setObjectName("metaPill")
        source_layout = QHBoxLayout(source_frame)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_label = QLabel("(소스 미선택)")
        self.source_label.setObjectName("infoValue")
        self.source_label.setMinimumWidth(280)
        self.source_label.setMaximumWidth(760)
        source_layout.addWidget(self.source_label)
        layout.addWidget(source_frame, 1)

        layout.addStretch()

        self.btn_shortcuts = QPushButton("단축키")
        self.btn_shortcuts.setObjectName("headerActionBtn")
        self.btn_shortcuts.setToolTip("단축키 목록 보기")
        self.btn_shortcuts.clicked.connect(self._show_shortcuts_dialog)
        layout.addWidget(self.btn_shortcuts)

        self.btn_detach_image = QPushButton("이미지 분리")
        self.btn_detach_image.setObjectName("headerActionBtn")
        self.btn_detach_image.setToolTip("이미지 패널을 별도 창으로 분리 (Ctrl+Shift+I)")
        self.btn_detach_image.clicked.connect(self._toggle_detach_image)
        layout.addWidget(self.btn_detach_image)

        self.btn_detach_review = QPushButton("검수창 분리")
        self.btn_detach_review.setObjectName("headerActionBtn")
        self.btn_detach_review.setToolTip("검수 패널을 별도 창으로 분리 (Ctrl+Shift+R)")
        self.btn_detach_review.clicked.connect(self._toggle_detach_review)
        layout.addWidget(self.btn_detach_review)

        self.btn_focus_mode = QPushButton("표 집중 모드")
        self.btn_focus_mode.setObjectName("headerActionBtn")
        self.btn_focus_mode.setCheckable(True)
        self.btn_focus_mode.setToolTip("Ctrl+F")
        self.btn_focus_mode.toggled.connect(self._on_focus_mode_toggled)
        layout.addWidget(self.btn_focus_mode)

        self.btn_save = QPushButton("현재 JSON 저장")
        self.btn_save.setObjectName("headerActionBtn")
        self.btn_save.setToolTip("Ctrl+S")
        self.btn_save.clicked.connect(self.save_current)
        layout.addWidget(self.btn_save)

        return frame

    def _set_status(self, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            text = "대기 중"
        if not text.startswith("최근 작업 로그:"):
            text = f"최근 작업 로그: {text}"
        self.status.showMessage(text)

    # ---------- 단축키 ----------
    def _install_shortcuts(self):
        """애플리케이션 전역 단축키.

        조합 키:
          - Ctrl+S         : 현재 JSON 저장 (로컬/S3 백엔드 자동)
          - Ctrl+E         : 표 편집 모드 토글
          - Ctrl+F         : 표 집중 모드 토글
          - Ctrl+O         : 로컬 폴더 열기 (로컬 모드일 때)
          - Ctrl+Shift+S   : 원격 연결/스캔 (S3/SSH 모드일 때, 입력값 사용)
          - Ctrl+Shift+I   : 이미지 패널 분리/복귀
          - Ctrl+Shift+R   : 검수 패널 분리/복귀
          - Ctrl+↓ / Ctrl+↑: 다음 / 이전 파일
          - Ctrl+0         : 이미지 화면 맞춤 (zoom reset)

        표 편집 단축키 (편집 모드에서만 작동):
          - Ctrl+B         : 셀 병합
          - Ctrl+G         : 열 추가 (오른쪽)
          - Ctrl+H         : 행 추가 (아래)
          - Ctrl+U         : 셀 분할
          - Ctrl+Shift+G   : 열 추가 (왼쪽)
          - Ctrl+Shift+H   : 행 추가 (위)

        탐색 키 (텍스트 입력/표 편집기에 포커스 있을 땐 무시):
          - Q / E          : 이전 / 다음 TABLE (다른 라벨은 건너뜀)
          - A / D          : 같은 폴더 내 이전 / 다음 페이지
          - Z / C          : 이전 / 다음 폴더의 첫 페이지
        """
        ctx = Qt.ShortcutContext.ApplicationShortcut

        def add(seq: str, slot):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(ctx)
            sc.activated.connect(slot)
            return sc

        def nav(action):
            return lambda: self._nav_if_not_typing(action)

        add("Ctrl+S", self.save_current)
        add("Ctrl+E", self.review_panel.toggle_edit_mode)
        add("Ctrl+F", self.toggle_table_focus_mode)
        add("Ctrl+O", self._shortcut_open_local)
        add("Ctrl+Shift+S", self._shortcut_scan_remote)
        add("Ctrl+Shift+I", self._toggle_detach_image)
        add("Ctrl+Shift+R", self._toggle_detach_review)
        add("Ctrl+Down", lambda: self.file_panel.select_relative(+1))
        add("Ctrl+Up", lambda: self.file_panel.select_relative(-1))
        add("Ctrl+0", self.image_panel.reset_zoom)

        # 표 편집 단축키
        add("Ctrl+B", lambda: self._table_edit_shortcut("mergeSelection"))
        add("Ctrl+G", lambda: self._table_edit_shortcut("addColRight"))
        add("Ctrl+H", lambda: self._table_edit_shortcut("addRowBelow"))
        add("Ctrl+U", lambda: self._table_edit_shortcut("splitCell"))
        add("Ctrl+Shift+G", lambda: self._table_edit_shortcut("addColLeft"))
        add("Ctrl+Shift+H", lambda: self._table_edit_shortcut("addRowAbove"))

        # 단일 키 탐색 — 텍스트 입력 위젯/WebView 포커스 시 자동 무시
        add("Q", nav(lambda: self._select_shape_relative(-1)))
        add("E", nav(lambda: self._select_shape_relative(+1)))
        add("A", nav(lambda: self.file_panel.select_in_book(-1)))
        add("D", nav(lambda: self.file_panel.select_in_book(+1)))
        add("Z", nav(lambda: self.file_panel.select_book(-1)))
        add("C", nav(lambda: self.file_panel.select_book(+1)))

    def _nav_if_not_typing(self, action):
        """텍스트 입력 위젯이나 표 편집 WebView에 포커스가 있으면 키 입력을
        그대로 그쪽으로 가게 하기 위해 단축키를 발화하지 않는다."""
        fw = QApplication.instance().focusWidget()
        if fw is not None:
            if isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit)):
                return
            # WebEngine 위젯(편집 가능한 셀)은 클래스명에 'WebEngine'이 들어감
            node = fw
            while node is not None:
                if "WebEngine" in node.metaObject().className():
                    return
                node = node.parent() if hasattr(node, "parent") else None
        action()

    def _shortcut_open_local(self):
        if self.file_panel.current_mode() != "local":
            self._set_status("로컬 모드에서만 사용 가능")
            return
        self._open_local_folder()

    def _shortcut_scan_remote(self):
        mode = self.file_panel.current_mode()
        if mode == "s3":
            self.file_panel.trigger_s3_scan()
            return
        if mode == "ssh":
            self.file_panel.trigger_ssh_scan()
            return
        self._set_status("S3 또는 SSH 모드에서만 사용 가능")

    def _table_edit_shortcut(self, op: str):
        """표 편집 단축키 - 편집 모드일 때만 작동."""
        if not self.review_panel.editor.is_edit_mode():
            return
        self.review_panel.editor.run_table_op(op)

    def _show_shortcuts_dialog(self):
        """단축키 목록 다이얼로그 표시."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("단축키 목록")
        dialog.setIcon(QMessageBox.Icon.Information)

        shortcuts_text = """
<h3>기본 단축키</h3>
<table cellpadding="4">
<tr><td><b>Ctrl+S</b></td><td>현재 JSON 저장</td></tr>
<tr><td><b>Ctrl+E</b></td><td>표 편집 모드 토글</td></tr>
<tr><td><b>Ctrl+F</b></td><td>표 집중 모드 토글</td></tr>
<tr><td><b>Ctrl+O</b></td><td>로컬 폴더 열기</td></tr>
<tr><td><b>Ctrl+Shift+S</b></td><td>원격 연결/스캔</td></tr>
<tr><td><b>Ctrl+Shift+I</b></td><td>이미지 패널 분리/복귀</td></tr>
<tr><td><b>Ctrl+Shift+R</b></td><td>검수 패널 분리/복귀</td></tr>
<tr><td><b>Ctrl+↓ / Ctrl+↑</b></td><td>다음/이전 파일</td></tr>
<tr><td><b>Ctrl+0</b></td><td>이미지 화면 맞춤</td></tr>
</table>

<h3>표 편집 단축키 (편집 모드)</h3>
<table cellpadding="4">
<tr><td><b>Ctrl+B</b></td><td>셀 병합</td></tr>
<tr><td><b>Ctrl+G</b></td><td>열 추가 (오른쪽)</td></tr>
<tr><td><b>Ctrl+H</b></td><td>행 추가 (아래)</td></tr>
<tr><td><b>Ctrl+U</b></td><td>셀 분할</td></tr>
<tr><td><b>Ctrl+Shift+G</b></td><td>열 추가 (왼쪽)</td></tr>
<tr><td><b>Ctrl+Shift+H</b></td><td>행 추가 (위)</td></tr>
</table>

<h3>탐색 키</h3>
<table cellpadding="4">
<tr><td><b>Q / E</b></td><td>이전/다음 TABLE</td></tr>
<tr><td><b>A / D</b></td><td>같은 폴더 내 이전/다음 페이지</td></tr>
<tr><td><b>Z / C</b></td><td>이전/다음 폴더의 첫 페이지</td></tr>
</table>
        """

        dialog.setText(shortcuts_text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    # ---------- 시그널 배선 ----------
    def _wire_signals(self):
        self.file_panel.file_selected.connect(self._load_entry)
        self.file_panel.local_open_requested.connect(self._open_local_folder)
        self.file_panel.s3_scan_requested.connect(self._connect_s3)
        self.file_panel.ssh_scan_requested.connect(self._connect_ssh)
        self.file_panel.table_filter_requested.connect(self._on_table_filter_requested)
        self.file_panel.mode_changed.connect(self._on_mode_changed)
        self.image_panel.bbox_clicked.connect(self._on_bbox_clicked)
        self.review_panel.shape_selected.connect(self._on_table_list_selected)
        self.review_panel.status_message.connect(self._set_status)

    # ---------- 모드/백엔드 ----------
    def _on_mode_changed(self, _mode: str):
        self._cleanup_table_filter_worker()
        self._close_backend()
        # 모드 전환 시 기존 백엔드/엔트리 초기화
        self.backend = None
        self.current_entry = None
        self.data = None
        self.shapes = []
        self.current_shape_index = -1
        self.source_label.setText("(소스 미선택)")
        self.source_label.setToolTip("(소스 미선택)")
        self.file_panel.set_entries([], "")
        self.image_panel.set_image(QPixmap())
        self.image_panel.set_shapes([])
        self.review_panel.set_shapes([])

    def _on_table_filter_requested(self, enabled: bool):
        if self._table_filter_thread is not None:
            return
        if self.backend is None:
            self.file_panel.refresh_entries()
            return

        if enabled and self.file_panel.has_unresolved_table_entries():
            self._start_table_presence_resolution()
            return
        else:
            self.file_panel.refresh_entries()

        visible = len(self.file_panel.visible_entries())
        total = len(self.file_panel.table_filter_entries())
        scope = self.file_panel.table_filter_scope_text()
        if enabled:
            if scope:
                self._set_status(f"TABLE 필터 적용: {scope} | {visible} / {total}개 파일")
            else:
                self._set_status(f"TABLE 필터 적용: {visible} / {total}개 파일")
        else:
            self._set_status(f"TABLE 필터 해제: {len(self.file_panel.all_entries())}개 파일")

    def _open_local_folder(self):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not path:
            return
        backend = LocalBackend(folder=Path(path))
        self._activate_backend(backend)

    def _connect_s3(self, params: dict):
        access_key = params.get("access_key") or ""
        secret_key = params.get("secret_key") or ""
        if bool(access_key) != bool(secret_key):
            QMessageBox.critical(self, "오류", "Access Key와 Secret Key는 함께 입력해야 합니다.")
            return

        try:
            bucket, prefix = parse_s3_path(params.get("raw_path", ""))
        except ValueError as exc:
            QMessageBox.critical(self, "오류", str(exc))
            return

        config = S3Config(
            bucket=bucket,
            prefix=prefix,
            region=params.get("region") or None,
            access_key=access_key or None,
            secret_key=secret_key or None,
            session_token=params.get("session_token") or None,
        )

        try:
            backend = S3Backend(config)
        except S3BackendError as exc:
            QMessageBox.critical(self, "AWS 오류", str(exc))
            return

        self._activate_backend(backend)

    def _connect_ssh(self, params: dict):
        try:
            port = int(params.get("port") or "22")
            if port < 1 or port > 65535:
                raise ValueError("Port는 1~65535 사이여야 합니다.")
            pem_path = (params.get("pem_path") or "").strip()
            if not pem_path:
                raise ValueError("PEM 파일 경로를 입력해주세요.")
            config = SSHConfig(
                host=params.get("host") or "",
                port=port,
                username=params.get("username") or "",
                pem_path=Path(pem_path).expanduser(),
                passphrase=params.get("passphrase") or None,
                remote_root=params.get("remote_root") or "",
            )
        except ValueError as exc:
            QMessageBox.critical(self, "오류", str(exc))
            return

        try:
            backend = SSHBackend(config)
        except SSHBackendError as exc:
            QMessageBox.critical(self, "SSH 오류", str(exc))
            return

        self._activate_backend(backend)
        if self.backend is backend:
            self.file_panel.remember_ssh_settings(params)

    def _activate_backend(self, backend: StorageBackend):
        self._close_backend()
        self.backend = backend
        self.current_entry = None
        self.data = None
        self.shapes = []
        try:
            entries = backend.scan()
        except StorageBackendError as exc:
            QMessageBox.critical(self, "소스 오류", str(exc))
            self._close_backend()
            self.backend = None
            return

        root = backend.display_root()
        self.source_label.setText(root)
        self.source_label.setToolTip(root)
        self.file_panel.set_entries(entries, root)
        self.image_panel.set_image(QPixmap())
        self.image_panel.set_shapes([])
        self.review_panel.set_shapes([])
        self._set_status(f"소스 로드 완료: {len(entries)}개 이미지")

    def _start_table_presence_resolution(self):
        if self.backend is None:
            return
        pending = [
            entry for entry in self.file_panel.table_filter_entries()
            if entry.has_json and entry.has_table is None
        ]
        total = len(pending)
        if total == 0:
            self.file_panel.refresh_entries()
            return

        self.file_panel.set_table_filter_busy(True)
        self._set_status(f"TABLE 포함 파일 확인 중... ({total}개)")

        progress = QProgressDialog("TABLE 포함 여부 확인 중...", None, 0, total, self)
        progress.setWindowTitle("TABLE 필터")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.show()
        self._table_filter_progress = progress

        thread = QThread(self)
        worker = TablePresenceWorker(self.backend, self.file_panel.table_filter_entries())
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_table_filter_progress)
        worker.finished.connect(self._on_table_filter_finished)
        worker.failed.connect(self._on_table_filter_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._cleanup_table_filter_worker)

        self._table_filter_thread = thread
        self._table_filter_worker = worker
        thread.start()

    def _on_table_filter_progress(self, done: int, total: int, entry: ImageEntry):
        if self._table_filter_progress is None:
            return
        self._table_filter_progress.setLabelText(
            f"TABLE 포함 여부 확인 중... ({done}/{total})\n{entry.image_path.name}"
        )
        self._table_filter_progress.setValue(done)

    def _on_table_filter_finished(self, entries: list[ImageEntry]):
        if self._table_filter_progress is not None:
            self._table_filter_progress.setValue(self._table_filter_progress.maximum())
            self._table_filter_progress.close()
            self._table_filter_progress = None

        self.file_panel.update_resolved_entries(entries)
        self.file_panel.set_table_filter_busy(False)
        if self.current_entry is not None:
            for entry in self.file_panel.all_entries():
                if entry.image_key == self.current_entry.image_key:
                    self.current_entry = entry
                    break

        visible = len(self.file_panel.visible_entries())
        total = len(self.file_panel.table_filter_entries())
        scope = self.file_panel.table_filter_scope_text()
        if scope:
            self._set_status(f"TABLE 필터 적용: {scope} | {visible} / {total}개 파일")
        else:
            self._set_status(f"TABLE 필터 적용: {visible} / {total}개 파일")

    def _on_table_filter_failed(self, message: str):
        if self._table_filter_progress is not None:
            self._table_filter_progress.close()
            self._table_filter_progress = None
        self.file_panel.set_table_only_checked(False)
        self.file_panel.set_table_filter_busy(False)
        self.file_panel.refresh_entries()
        QMessageBox.critical(self, "TABLE 필터 오류", message)
        self._set_status("TABLE 필터 실패")

    def _cleanup_table_filter_worker(self):
        self.file_panel.set_table_filter_busy(False)
        self._table_filter_worker = None
        self._table_filter_thread = None

    # ---------- 파일 로드 ----------
    def _load_entry(self, entry: ImageEntry):
        if self.backend is None:
            return
        # 편집 중이던 변경사항을 이전 shape에 반영한 뒤 새 entry 로드
        self.review_panel.ensure_pulled(lambda: self._do_load_entry(entry))

    def _do_load_entry(self, entry: ImageEntry):
        try:
            image_bytes = self.backend.load_image_bytes(entry)
        except (OSError, StorageBackendError) as exc:
            QMessageBox.critical(self, "오류", f"이미지 로드 실패: {exc}")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes):
            QMessageBox.critical(self, "오류", f"이미지 디코딩 실패: {entry.image_path.name}")
            return

        self.current_entry = entry
        self.image_panel.set_image(pixmap)

        self.data = None
        self.shapes = []
        self.current_shape_index = -1
        if entry.has_json:
            try:
                self.data = self.backend.load_json(entry)
                self.shapes = self.data.get("shapes", [])
            except (OSError, ValueError, StorageBackendError) as exc:
                QMessageBox.critical(self, "오류", f"JSON 로드 실패: {exc}")
                self.data = None
                self.shapes = []

        self.image_panel.set_shapes(self.shapes)
        if self._focus_mode_enabled:
            self.image_panel.set_table_only_filter()
            self.review_panel.set_shapes(self.shapes, self._select_focus_mode_table)
        else:
            self.review_panel.set_shapes(self.shapes)

        msg = f"{entry.image_path.name} | {pixmap.width()}×{pixmap.height()}"
        msg += f" | shapes: {len(self.shapes)}" if entry.has_json else " | (JSON 없음)"
        self._set_status(msg)

    # ---------- 선택 동기화 ----------
    def _on_bbox_clicked(self, idx: int):
        if idx == self.current_shape_index:
            self.image_panel.select_shape(idx)
            self.review_panel.select_shape(idx)
            return
        self._select_shape(idx)

    def _on_table_list_selected(self, idx: int):
        self._select_shape(idx)
        self.image_panel.center_on(idx)

    def _select_shape(self, idx: int):
        if idx < 0 or idx >= len(self.shapes):
            return
        if idx == self.current_shape_index:
            self.image_panel.select_shape(idx)
            self.review_panel.select_shape(idx)
            return
        self.current_shape_index = idx
        self.image_panel.select_shape(idx)
        self.review_panel.select_shape(idx)
        shape = self.shapes[idx]
        self._set_status(f"선택: shape #{idx} ({shape.get('label')})")

    # ---------- 표 집중 모드 ----------
    def toggle_table_focus_mode(self):
        self.btn_focus_mode.setChecked(not self.btn_focus_mode.isChecked())

    def _on_focus_mode_toggled(self, enabled: bool):
        if enabled == self._focus_mode_enabled:
            return
        if enabled:
            self._enter_focus_mode()
        else:
            self._leave_focus_mode()

    def _enter_focus_mode(self):
        self._focus_mode_enabled = True
        self._focus_mode_saved_splitter_sizes = self.splitter.sizes()
        self._focus_mode_saved_filters = self.image_panel.label_filter_states()

        self.file_panel.hide()
        self.review_panel.set_focus_mode(True)
        self.image_panel.set_table_only_filter()
        self.review_panel.set_edit_mode(True)
        self._select_focus_mode_table()
        self.splitter.setSizes([0, 1000, 700])
        self._set_status("표 집중 모드 ON")

    def _leave_focus_mode(self):
        self._focus_mode_enabled = False
        self.file_panel.show()
        self.review_panel.set_focus_mode(False)
        if self._focus_mode_saved_filters is not None:
            self.image_panel.set_label_filter_states(self._focus_mode_saved_filters)
        if self._focus_mode_saved_splitter_sizes:
            self.splitter.setSizes(self._focus_mode_saved_splitter_sizes)
        else:
            self.splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        self._focus_mode_saved_splitter_sizes = None
        self._focus_mode_saved_filters = None
        self._set_status("표 집중 모드 OFF")

    def _select_focus_mode_table(self):
        table_indices = [i for i, s in enumerate(self.shapes) if s.get("label") == "TABLE"]
        if not table_indices:
            self._set_status("현재 페이지에 TABLE이 없습니다.")
            return
        if self.current_shape_index in table_indices:
            target = self.current_shape_index
        else:
            target = table_indices[0]
        self._select_shape(target)
        self.image_panel.center_on(target)

    def _select_shape_relative(self, delta: int):
        """TABLE 라벨 shape만 순회하며 ±delta 위치로 이동 + 이미지 중심 이동."""
        table_indices = [i for i, s in enumerate(self.shapes) if s.get("label") == "TABLE"]
        if not table_indices:
            return
        cur = self.current_shape_index
        if cur in table_indices:
            pos = table_indices.index(cur)
        else:
            # 비-TABLE을 보고 있던 상태 → 다음(또는 이전) 첫 TABLE로
            pos = -1 if delta >= 0 else len(table_indices)
        new_pos = max(0, min(len(table_indices) - 1, pos + delta))
        new = table_indices[new_pos]
        if new == cur:
            return
        self._select_shape(new)
        self.image_panel.center_on(new)

    # ---------- 창 분리 ----------
    def _toggle_detach_image(self):
        if self._detached_image_window is None:
            self._detach_image_panel()
        else:
            self._reattach_image_panel()

    def _toggle_detach_review(self):
        if self._detached_review_window is None:
            self._detach_review_panel()
        else:
            self._reattach_review_panel()

    def _detach_image_panel(self):
        """이미지 패널을 별도 창으로 분리."""
        if self._detached_image_window is not None:
            return

        # 현재 splitter 크기 저장
        self._image_panel_saved_sizes = self.splitter.sizes()

        # 패널을 splitter에서 분리 (부모 제거)
        self.image_panel.setParent(None)

        # 헤더 버튼 구성
        header_buttons = [
            {
                "text": "화면 맞춤",
                "tooltip": "이미지를 화면에 맞춤 (Ctrl+0)",
                "callback": self.image_panel.reset_zoom,
            },
        ]

        # 새 창 생성
        self._detached_image_window = DetachableWindow(
            "원본 이미지", self.image_panel, self, header_buttons
        )
        self._detached_image_window.finished.connect(self._reattach_image_panel)
        self._detached_image_window.show()
        self._detached_image_window.showMaximized()

        self.btn_detach_image.setText("이미지 복귀")
        self._set_status("이미지 패널이 별도 창으로 분리되었습니다")

    def _reattach_image_panel(self):
        """이미지 패널을 메인 윈도우로 복귀."""
        if self._detached_image_window is None:
            return

        # 창 닫기
        if self._detached_image_window.isVisible():
            self._detached_image_window.close()

        # 패널을 다시 splitter에 추가 (file_panel과 review_panel 사이, 인덱스 1)
        self.image_panel.setParent(None)
        self.splitter.insertWidget(1, self.image_panel)

        # 이전 크기 복원
        if hasattr(self, '_image_panel_saved_sizes') and self._image_panel_saved_sizes:
            self.splitter.setSizes(self._image_panel_saved_sizes)

        self._detached_image_window = None
        self.btn_detach_image.setText("이미지 분리")
        self._set_status("이미지 패널이 복귀되었습니다")

    def _detach_review_panel(self):
        """검수 패널을 별도 창으로 분리."""
        if self._detached_review_window is not None:
            return

        # 현재 splitter 크기 저장
        self._review_panel_saved_sizes = self.splitter.sizes()

        # 패널을 splitter에서 분리 (부모 제거)
        self.review_panel.setParent(None)

        # 헤더 버튼 구성
        header_buttons = [
            {
                "text": "표 편집 모드",
                "tooltip": "표 편집 모드 토글 (Ctrl+E)",
                "checkable": True,
                "checked": self.review_panel.editor.is_edit_mode(),
                "callback": self.review_panel.toggle_edit_mode,
            },
            {
                "text": "현재 JSON 저장",
                "tooltip": "현재 JSON 파일 저장 (Ctrl+S)",
                "callback": self.save_current,
            },
        ]

        # 새 창 생성
        self._detached_review_window = DetachableWindow(
            "표 검수 창", self.review_panel, self, header_buttons
        )
        self._detached_review_window.finished.connect(self._reattach_review_panel)
        self._detached_review_window.show()
        self._detached_review_window.showMaximized()

        self.btn_detach_review.setText("검수창 복귀")
        self._set_status("검수 패널이 별도 창으로 분리되었습니다")

    def _reattach_review_panel(self):
        """검수 패널을 메인 윈도우로 복귀."""
        if self._detached_review_window is None:
            return

        # 창 닫기
        if self._detached_review_window.isVisible():
            self._detached_review_window.close()

        # 패널을 다시 splitter에 추가 (맨 끝에, 인덱스 2)
        self.review_panel.setParent(None)
        self.splitter.addWidget(self.review_panel)

        # 이전 크기 복원
        if hasattr(self, '_review_panel_saved_sizes') and self._review_panel_saved_sizes:
            self.splitter.setSizes(self._review_panel_saved_sizes)

        self._detached_review_window = None
        self.btn_detach_review.setText("검수창 분리")
        self._set_status("검수 패널이 복귀되었습니다")

    # ---------- 저장 ----------
    def save_current(self):
        """편집 중 변경사항을 풀백한 뒤 사용자 확인 후 저장."""
        if self.backend is None or self.current_entry is None or self.data is None:
            QMessageBox.information(self, "안내", "먼저 JSON이 있는 파일을 선택하세요.")
            return

        # 소스 탭에 있으면 먼저 미리보기에 적용
        self.review_panel.editor.apply_source_if_on_source_tab()

        # 편집 모드 변경사항 풀백 후 저장
        self.review_panel.ensure_pulled(self._confirm_and_save)

    def _confirm_and_save(self):
        if self.backend is None or self.current_entry is None or self.data is None:
            return

        target = self.backend.json_target_display(self.current_entry)
        kind = self.backend.target_kind()

        ans = QMessageBox.question(
            self,
            "저장 확인",
            f"{kind}에 변경사항을 저장하시겠습니까?\n\n{target}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self._set_status("저장 취소됨")
            return

        try:
            self.backend.save_json(self.current_entry, self.data)
        except (OSError, StorageBackendError) as exc:
            QMessageBox.critical(self, "저장 오류", str(exc))
            return
        self._set_status(f"저장됨: {target}")

    def _close_backend(self):
        backend = self.backend
        if backend is None:
            return
        close = getattr(backend, "close", None)
        if callable(close):
            close()

    def closeEvent(self, event):
        # 분리된 창들 정리
        if self._detached_image_window is not None:
            self._detached_image_window.close()
        if self._detached_review_window is not None:
            self._detached_review_window.close()
        self._close_backend()
        super().closeEvent(event)
