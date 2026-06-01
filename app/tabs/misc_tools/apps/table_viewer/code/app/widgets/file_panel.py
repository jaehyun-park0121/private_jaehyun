"""좌측 파일 패널 — 로컬/S3/SSH 모드 지원, 폴더 트리 형태 파일 목록."""

from pathlib import PurePosixPath

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    COLOR_SUBTEXT,
    DEFAULT_AWS_REGION,
    DEFAULT_SSH_PORT,
    S3_PATH_PLACEHOLDER,
    SSH_REMOTE_PATH_PLACEHOLDER,
)
from ..io_utils import ImageEntry


# QTreeWidgetItem.UserRole 데이터 타입 구분자
_ROLE_KIND = Qt.ItemDataRole.UserRole          # "folder" | "file"
_ROLE_INDEX = Qt.ItemDataRole.UserRole + 1     # 파일 노드의 entries 인덱스
_ROLE_PATH = Qt.ItemDataRole.UserRole + 2      # 폴더 노드의 상대 경로
_SETTINGS_ORG = "SelectstarDataTeam2"
_SETTINGS_APP = "TableViewer"
_SSH_SETTINGS_GROUP = "ssh"


class FilePanel(QFrame):
    """파일 트리 + 입력 모드 전환(로컬/S3/SSH).

    사용자가 파일 노드를 클릭하면 `file_selected(entry)` emit.
    """

    file_selected = pyqtSignal(object)             # ImageEntry
    local_open_requested = pyqtSignal()            # 폴더 선택 다이얼로그 요청
    s3_scan_requested = pyqtSignal(dict)           # S3 입력 dict
    ssh_scan_requested = pyqtSignal(dict)          # SSH/SFTP 입력 dict
    mode_changed = pyqtSignal(str)                 # "local" | "s3" | "ssh"
    table_filter_requested = pyqtSignal(bool)      # TABLE 포함 파일 필터 적용/해제

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(390)
        self._all_entries: list[ImageEntry] = []
        self._entries: list[ImageEntry] = []
        self._file_items: list[QTreeWidgetItem] = []  # leaf 순차 (단축키 이동용)
        self._display_root = ""
        self._table_filter_scope_folder: str | None = None
        self._build_ui()
        self._load_ssh_settings()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("입력 / 파일")
        title.setObjectName("title")
        root.addWidget(title)

        input_group = QGroupBox("입력 소스")
        input_layout = QVBoxLayout(input_group)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        def field_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            label.setFixedWidth(58)
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            return label

        # 모드 선택
        mode_row = QHBoxLayout()
        mode_row.addWidget(field_label("모드"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("로컬 폴더", "local")
        self.mode_combo.addItem("AWS S3", "s3")
        self.mode_combo.addItem("SSH/SFTP", "ssh")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, 1)
        input_layout.addLayout(mode_row)

        # 로컬 그룹
        self.local_group = QGroupBox("로컬")
        local_layout = QVBoxLayout(self.local_group)
        local_layout.setContentsMargins(8, 8, 8, 8)
        self.btn_open_folder = QPushButton("폴더 열기")
        self.btn_open_folder.setToolTip("Ctrl+O")
        self.btn_open_folder.clicked.connect(self.local_open_requested.emit)
        local_layout.addWidget(self.btn_open_folder)
        input_layout.addWidget(self.local_group)

        # S3 그룹
        self.s3_group = QGroupBox("AWS S3")
        s3_layout = QFormLayout(self.s3_group)
        s3_layout.setContentsMargins(8, 8, 8, 8)
        s3_layout.setHorizontalSpacing(8)
        s3_layout.setVerticalSpacing(4)
        s3_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.aws_access_key_edit = QLineEdit()
        self.aws_access_key_edit.setPlaceholderText("AWS Access Key")

        self.aws_secret_key_edit = QLineEdit()
        self.aws_secret_key_edit.setPlaceholderText("AWS Secret Key")
        self.aws_secret_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.aws_session_token_edit = QLineEdit()
        self.aws_session_token_edit.setPlaceholderText("Session Token (선택)")
        self.aws_session_token_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.aws_region_edit = QLineEdit()
        self.aws_region_edit.setPlaceholderText(DEFAULT_AWS_REGION)

        self.s3_path_edit = QLineEdit()
        self.s3_path_edit.setPlaceholderText(S3_PATH_PLACEHOLDER)

        s3_layout.addRow(field_label("Access"), self.aws_access_key_edit)
        s3_layout.addRow(field_label("Secret"), self.aws_secret_key_edit)
        s3_layout.addRow(field_label("Session"), self.aws_session_token_edit)
        s3_layout.addRow(field_label("Region"), self.aws_region_edit)
        s3_layout.addRow(field_label("S3"), self.s3_path_edit)

        self.btn_s3_scan = QPushButton("연결 / 스캔")
        self.btn_s3_scan.setObjectName("primary")
        self.btn_s3_scan.setToolTip("Ctrl+Shift+S")
        self.btn_s3_scan.clicked.connect(self._on_s3_scan_clicked)
        s3_layout.addRow(self.btn_s3_scan)
        input_layout.addWidget(self.s3_group)

        # SSH/SFTP 그룹
        self.ssh_group = QGroupBox("SSH/SFTP")
        ssh_layout = QFormLayout(self.ssh_group)
        ssh_layout.setContentsMargins(8, 8, 8, 8)
        ssh_layout.setHorizontalSpacing(8)
        ssh_layout.setVerticalSpacing(4)
        ssh_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.ssh_host_edit = QLineEdit()
        self.ssh_host_edit.setPlaceholderText("server.example.com 또는 IP")

        self.ssh_port_edit = QLineEdit()
        self.ssh_port_edit.setText(DEFAULT_SSH_PORT)
        self.ssh_port_edit.setPlaceholderText(DEFAULT_SSH_PORT)

        self.ssh_user_edit = QLineEdit()
        self.ssh_user_edit.setPlaceholderText("SSH 사용자명")

        self.ssh_pem_path_edit = QLineEdit()
        self.ssh_pem_path_edit.setPlaceholderText("PEM 파일 경로")
        self.btn_browse_pem = QPushButton("찾기")
        self.btn_browse_pem.clicked.connect(self._on_browse_pem_clicked)
        pem_widget = QWidget()
        pem_layout = QHBoxLayout(pem_widget)
        pem_layout.setContentsMargins(0, 0, 0, 0)
        pem_layout.setSpacing(4)
        pem_layout.addWidget(self.ssh_pem_path_edit, 1)
        pem_layout.addWidget(self.btn_browse_pem, 0)

        self.ssh_passphrase_edit = QLineEdit()
        self.ssh_passphrase_edit.setPlaceholderText("PEM Passphrase (선택)")
        self.ssh_passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.ssh_remote_root_edit = QLineEdit()
        self.ssh_remote_root_edit.setPlaceholderText(SSH_REMOTE_PATH_PLACEHOLDER)

        ssh_layout.addRow(field_label("Host"), self.ssh_host_edit)
        ssh_layout.addRow(field_label("Port"), self.ssh_port_edit)
        ssh_layout.addRow(field_label("User"), self.ssh_user_edit)
        ssh_layout.addRow(field_label("PEM"), pem_widget)
        ssh_layout.addRow(field_label("Pass"), self.ssh_passphrase_edit)
        ssh_layout.addRow(field_label("Root"), self.ssh_remote_root_edit)

        self.btn_ssh_scan = QPushButton("연결 / 스캔")
        self.btn_ssh_scan.setObjectName("primary")
        self.btn_ssh_scan.setToolTip("Ctrl+Shift+S")
        self.btn_ssh_scan.clicked.connect(self._on_ssh_scan_clicked)
        ssh_layout.addRow(self.btn_ssh_scan)
        input_layout.addWidget(self.ssh_group)
        root.addWidget(input_group, 0)

        count_row = QHBoxLayout()
        count_row.setContentsMargins(0, 0, 0, 0)
        count_row.setSpacing(8)

        self.count_label = QLabel("0개 파일")
        self.count_label.setObjectName("subtitle")
        count_row.addWidget(self.count_label, 1)

        self.btn_table_only = QPushButton("표만 보기")
        self.btn_table_only.setObjectName("toggle")
        self.btn_table_only.setCheckable(True)
        self.btn_table_only.setToolTip("TABLE shape가 있는 JSON만 표시")
        self.btn_table_only.toggled.connect(self._on_table_only_toggled)
        count_row.addWidget(self.btn_table_only, 0)
        root.addLayout(count_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.tree, 1)

        self._apply_mode_visibility("local")

    # ---------- 외부 API ----------
    def set_entries(self, entries: list[ImageEntry], display_root: str):
        self._all_entries = list(entries)
        self._display_root = display_root or ""
        self._table_filter_scope_folder = None
        self._rebuild_tree()

    def current_mode(self) -> str:
        return self.mode_combo.currentData() or "local"

    def is_table_only(self) -> bool:
        return self.btn_table_only.isChecked()

    def visible_entries(self) -> list[ImageEntry]:
        return list(self._entries)

    def all_entries(self) -> list[ImageEntry]:
        return list(self._all_entries)

    def set_table_only_checked(self, checked: bool):
        if not checked:
            self._table_filter_scope_folder = None
        blocked = self.btn_table_only.blockSignals(True)
        self.btn_table_only.setChecked(checked)
        self.btn_table_only.blockSignals(blocked)

    def set_table_filter_busy(self, busy: bool):
        self.btn_table_only.setEnabled((not busy) and bool(self._all_entries))

    def refresh_entries(self):
        self._rebuild_tree()

    def update_entries(self, entries: list[ImageEntry], display_root: str | None = None):
        self._all_entries = list(entries)
        if display_root is not None:
            self._display_root = display_root or ""
        self._rebuild_tree()

    def has_unresolved_table_entries(self) -> bool:
        return any(
            entry.has_json and entry.has_table is None
            for entry in self.table_filter_entries()
        )

    def table_filter_entries(self) -> list[ImageEntry]:
        return [
            entry for entry in self._all_entries
            if self._entry_in_table_filter_scope(entry)
        ]

    def table_filter_scope_text(self) -> str:
        return self._table_filter_scope_folder or ""

    def update_resolved_entries(self, entries: list[ImageEntry]):
        resolved_by_key = {entry.image_key: entry for entry in entries}
        self._all_entries = [
            resolved_by_key.get(entry.image_key, entry)
            for entry in self._all_entries
        ]
        self._rebuild_tree()

    def remember_ssh_settings(self, params: dict):
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.beginGroup(_SSH_SETTINGS_GROUP)
        settings.setValue("host", params.get("host") or "")
        settings.setValue("port", params.get("port") or DEFAULT_SSH_PORT)
        settings.setValue("username", params.get("username") or "")
        settings.setValue("pem_path", params.get("pem_path") or "")
        settings.setValue("remote_root", params.get("remote_root") or "")
        settings.endGroup()
        settings.sync()

    def _rebuild_tree(self):
        current_key = self._current_image_key()
        self._entries = self._filtered_entries()
        self.tree.clear()
        self._file_items = []

        # 폴더 노드 캐시: PurePosixPath('a/b') -> QTreeWidgetItem
        folder_nodes: dict[PurePosixPath, QTreeWidgetItem] = {}

        def get_folder(folder_rel: PurePosixPath) -> QTreeWidgetItem | None:
            if str(folder_rel) in (".", ""):
                return None  # 루트는 트리 최상위
            if folder_rel in folder_nodes:
                return folder_nodes[folder_rel]
            parent_node = get_folder(folder_rel.parent)
            node = QTreeWidgetItem([folder_rel.name])
            node.setData(0, _ROLE_KIND, "folder")
            if parent_node is None:
                self.tree.addTopLevelItem(node)
            else:
                parent_node.addChild(node)
            folder_nodes[folder_rel] = node
            node.setData(0, _ROLE_PATH, folder_rel.as_posix())
            return node

        for idx, e in enumerate(self._entries):
            rel = PurePosixPath(e.image_path.as_posix())
            parent = get_folder(rel.parent)
            file_node = QTreeWidgetItem([rel.name])
            file_node.setData(0, _ROLE_KIND, "file")
            file_node.setData(0, _ROLE_INDEX, idx)
            if not e.has_json:
                file_node.setForeground(0, QColor(COLOR_SUBTEXT))
            if parent is None:
                self.tree.addTopLevelItem(file_node)
            else:
                parent.addChild(file_node)
            self._file_items.append(file_node)

        # 폴더가 단일 트리거나 적으면 펼쳐서 보여주기 (3개 이하)
        if len(folder_nodes) <= 3:
            self.tree.expandAll()
        self._restore_selection(current_key)
        self._update_count_label()
        self.btn_table_only.setEnabled(bool(self._all_entries))

    def select_relative(self, delta: int):
        """파일 노드만 순차적으로 delta칸 이동 + 선택 emit."""
        if not self._file_items:
            return
        cur = self.tree.currentItem()
        try:
            cur_idx = self._file_items.index(cur) if cur is not None else -1
        except ValueError:
            cur_idx = -1
        if cur_idx < 0:
            new_idx = 0 if delta >= 0 else len(self._file_items) - 1
        else:
            new_idx = max(0, min(len(self._file_items) - 1, cur_idx + delta))
        if new_idx == cur_idx:
            return
        target = self._file_items[new_idx]
        # 부모 폴더 펼치기
        p = target.parent()
        while p is not None:
            p.setExpanded(True)
            p = p.parent()
        self.tree.setCurrentItem(target)
        self._emit_file(target)

    def trigger_s3_scan(self):
        """외부 호출 — '연결 / 스캔' 버튼과 동일."""
        self._on_s3_scan_clicked()

    def trigger_ssh_scan(self):
        """외부 호출 — '연결 / 스캔' 버튼과 동일."""
        self._on_ssh_scan_clicked()

    def select_in_book(self, delta: int):
        """같은 폴더(도서) 내 다음/이전 페이지."""
        cur_global = self._current_global_index()
        if cur_global is None:
            return
        cur_folder = self._folder_of(self._entries[cur_global])
        same_folder = [i for i, e in enumerate(self._entries) if self._folder_of(e) == cur_folder]
        if not same_folder:
            return
        pos = same_folder.index(cur_global)
        new_pos = max(0, min(len(same_folder) - 1, pos + delta))
        if new_pos == pos:
            return
        self._jump_to_global(same_folder[new_pos])

    def select_book(self, delta: int):
        """다른 폴더(도서)의 첫 페이지로 이동 (트리 등장 순서 유지)."""
        if not self._entries:
            return
        first_index_of: dict[str, int] = {}
        order: list[str] = []
        for i, e in enumerate(self._entries):
            f = self._folder_of(e)
            if f not in first_index_of:
                first_index_of[f] = i
                order.append(f)
        cur_global = self._current_global_index()
        if cur_global is None:
            self._jump_to_global(first_index_of[order[0]])
            return
        cur_folder = self._folder_of(self._entries[cur_global])
        cur_pos = order.index(cur_folder) if cur_folder in order else 0
        new_pos = max(0, min(len(order) - 1, cur_pos + delta))
        if new_pos == cur_pos:
            return
        self._jump_to_global(first_index_of[order[new_pos]])

    @staticmethod
    def _folder_of(entry: ImageEntry) -> str:
        """페이지/도서 이동에서 같은 폴더로 묶을 식별자. 루트는 '.'"""
        parent = entry.image_path.parent.as_posix()
        return parent if parent not in ("", ".") else "."

    def _current_global_index(self) -> int | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        idx = item.data(0, _ROLE_INDEX)
        if idx is None or idx < 0 or idx >= len(self._entries):
            return None
        return idx

    def _jump_to_global(self, global_index: int):
        if global_index < 0 or global_index >= len(self._file_items):
            return
        target = self._file_items[global_index]
        p = target.parent()
        while p is not None:
            p.setExpanded(True)
            p = p.parent()
        self.tree.setCurrentItem(target)
        self._emit_file(target)

    # ---------- 내부 ----------
    def _on_mode_changed(self, _index: int):
        mode = self.current_mode()
        self._apply_mode_visibility(mode)
        self.mode_changed.emit(mode)

    def _apply_mode_visibility(self, mode: str):
        self.local_group.setVisible(mode == "local")
        self.s3_group.setVisible(mode == "s3")
        self.ssh_group.setVisible(mode == "ssh")

    def _on_table_only_toggled(self, _checked: bool):
        if self.is_table_only():
            self._table_filter_scope_folder = self._selected_folder_scope()
        else:
            self._table_filter_scope_folder = None
        self.table_filter_requested.emit(self.is_table_only())

    def _on_s3_scan_clicked(self):
        self.s3_scan_requested.emit({
            "raw_path": self.s3_path_edit.text(),
            "region": self.aws_region_edit.text().strip(),
            "access_key": self.aws_access_key_edit.text().strip(),
            "secret_key": self.aws_secret_key_edit.text().strip(),
            "session_token": self.aws_session_token_edit.text().strip(),
        })

    def _on_browse_pem_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "PEM 파일 선택",
            "",
            "Key Files (*.pem *.key *);;All Files (*)",
        )
        if path:
            self.ssh_pem_path_edit.setText(path)

    def _on_ssh_scan_clicked(self):
        self.ssh_scan_requested.emit({
            "host": self.ssh_host_edit.text().strip(),
            "port": self.ssh_port_edit.text().strip(),
            "username": self.ssh_user_edit.text().strip(),
            "pem_path": self.ssh_pem_path_edit.text().strip(),
            "passphrase": self.ssh_passphrase_edit.text(),
            "remote_root": self.ssh_remote_root_edit.text().strip(),
        })

    def _load_ssh_settings(self):
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.beginGroup(_SSH_SETTINGS_GROUP)
        self.ssh_host_edit.setText(str(settings.value("host", "") or ""))
        self.ssh_port_edit.setText(str(settings.value("port", DEFAULT_SSH_PORT) or DEFAULT_SSH_PORT))
        self.ssh_user_edit.setText(str(settings.value("username", "") or ""))
        self.ssh_pem_path_edit.setText(str(settings.value("pem_path", "") or ""))
        self.ssh_remote_root_edit.setText(str(settings.value("remote_root", "") or ""))
        settings.endGroup()

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int):
        kind = item.data(0, _ROLE_KIND)
        if kind == "folder":
            item.setExpanded(not item.isExpanded())
            return
        if kind == "file":
            self._emit_file(item)

    def _emit_file(self, item: QTreeWidgetItem):
        idx = item.data(0, _ROLE_INDEX)
        if idx is None or idx < 0 or idx >= len(self._entries):
            return
        self.file_selected.emit(self._entries[idx])

    def _filtered_entries(self) -> list[ImageEntry]:
        if not self.is_table_only():
            return list(self._all_entries)
        return [
            entry for entry in self._all_entries
            if self._entry_in_table_filter_scope(entry) and entry.has_table
        ]

    def _selected_folder_scope(self) -> str | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        if item.data(0, _ROLE_KIND) != "folder":
            return None
        value = item.data(0, _ROLE_PATH)
        if not value or value == ".":
            return None
        return str(value)

    def _entry_in_table_filter_scope(self, entry: ImageEntry) -> bool:
        scope = self._table_filter_scope_folder
        if not scope:
            return True
        folder = self._folder_of(entry)
        return folder == scope or folder.startswith(f"{scope}/")

    def _current_image_key(self) -> str:
        item = self.tree.currentItem()
        if item is None:
            return ""
        idx = item.data(0, _ROLE_INDEX)
        if idx is None or idx < 0 or idx >= len(self._entries):
            return ""
        return self._entries[idx].image_key

    def _restore_selection(self, image_key: str):
        if not image_key:
            self.tree.clearSelection()
            return
        for item in self._file_items:
            idx = item.data(0, _ROLE_INDEX)
            if idx is None or idx < 0 or idx >= len(self._entries):
                continue
            if self._entries[idx].image_key != image_key:
                continue
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self.tree.setCurrentItem(item)
            return
        self.tree.clearSelection()

    def _update_count_label(self):
        total = len(self._all_entries)
        visible = len(self._entries)
        root = self._display_root or "소스 미선택"
        if self.is_table_only():
            scoped_total = len(self.table_filter_entries())
            scope = self.table_filter_scope_text()
            if scope:
                text = f"{visible} / {scoped_total}개 파일 | 폴더: {scope} | {root}"
            else:
                text = f"{visible} / {total}개 파일 | {root}"
        else:
            text = f"{visible}개 파일 | {root}"
        self.count_label.setText(text)
