import os
import multiprocessing
import sys
from pathlib import Path
from typing import Optional

import PyQt5
from PyQt5.QtCore import QLibraryInfo
from PyQt5.QtWidgets import QApplication

from app.main_window import MainWindow


def _setup_qt_plugin_path() -> Optional[Path]:
    # 일부 환경에서 Qt가 windows 플랫폼 플러그인(qwindows.dll) 경로를
    # 자동으로 찾지 못하므로, 실행 전에 경로를 명시적으로 지정한다.
    candidates = []

    qlib_path = QLibraryInfo.location(QLibraryInfo.PluginsPath)
    if qlib_path:
        candidates.append(Path(qlib_path))

    # 가장 신뢰할 수 있는 기준: 현재 import된 PyQt5 패키지 위치
    pyqt_import_path = Path(PyQt5.__file__).resolve().parent
    candidates.append(pyqt_import_path / "Qt5" / "plugins")
    candidates.append(pyqt_import_path / "Qt" / "plugins")

    # fallback: sys.prefix 기준 site-packages
    pyqt_pkg = Path(sys.prefix) / "Lib" / "site-packages" / "PyQt5"
    candidates.append(pyqt_pkg / "Qt5" / "plugins")
    candidates.append(pyqt_pkg / "Qt" / "plugins")

    for plugin_root in candidates:
        platform_dir = plugin_root / "platforms"
        if platform_dir.exists():
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_dir)
            os.environ["QT_PLUGIN_PATH"] = str(plugin_root)
            return plugin_root
    return None


def main() -> int:
    plugin_root = _setup_qt_plugin_path()
    app = QApplication(sys.argv)
    if plugin_root is not None:
        # Qt 내부 검색 경로도 동기화해서 "windows" 플러그인 탐색 실패를 방지한다.
        QApplication.setLibraryPaths([str(plugin_root)])
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
