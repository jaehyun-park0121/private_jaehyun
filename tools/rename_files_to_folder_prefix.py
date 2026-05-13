"""폴더별 파일명 정규화: 각 디렉터리 안 파일을 `{그폴더이름}_번호.확장자` 형태로 변경합니다.

사용 예:
  python rename_files_to_folder_prefix.py
    → PyQt5 폴더 대화상자에서 상위 경로 선택

  python rename_files_to_folder_prefix.py --root "D:\\data\\validation"
    → 지정 루트 아래 모든 하위 폴더 순회

  python rename_files_to_folder_prefix.py --root "D:\\data\\validation" --dry-run
    → 실제 이름 변경 없이 미리보기만 출력
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


# 파일명(확장자 제외) 끝의 `_숫자` 패턴 (예: ..._0001)
_TRAILING_NUM_SUFFIX = re.compile(r"_(\d+)$")


def collect_all_directories(root: Path) -> list[Path]:
    """루트 및 그 아래 모든 디렉터리를 깊이·경로 문자열 순으로 정렬해 반환합니다."""
    resolved = root.resolve()
    dirs_set: set[Path] = {resolved}
    dirs_set.update(p.resolve() for p in resolved.rglob("*") if p.is_dir())
    return sorted(dirs_set, key=lambda p: (len(p.parts), str(p)))


def propose_new_filename(folder_name: str, file_path: Path) -> str | None:
    """stem 끝에 `_숫자`가 있으면 `{folder_name}_{숫자}{suffix}` 를 반환, 없으면 None."""
    stem = file_path.stem
    m = _TRAILING_NUM_SUFFIX.search(stem)
    if not m:
        return None
    num_suffix = m.group(0)  # 예: "_0001"
    return f"{folder_name}{num_suffix}{file_path.suffix}"


def rename_files_in_folder(folder: Path, *, dry_run: bool) -> tuple[int, int, int]:
    """한 폴더 안의 파일만 대상으로 이름 변경. (성공, 스킵, 충돌) 개수 반환."""
    ok = skip = conflict = 0
    entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())

    planned: dict[str, Path] = {}  # new_name -> 기존 경로 (충돌 검사)

    for old_path in entries:
        if not old_path.is_file():
            continue
        folder_name = folder.name
        new_name = propose_new_filename(folder_name, old_path)
        if new_name is None:
            skip += 1
            continue
        if new_name == old_path.name:
            skip += 1
            continue
        dest = old_path.with_name(new_name)
        if new_name in planned and planned[new_name] != old_path:
            print(f"  [충돌] 같은 목표 이름: {new_name}")
            conflict += 1
            continue
        planned[new_name] = old_path

    for new_name, old_path in planned.items():
        dest = old_path.with_name(new_name)
        if dest.exists() and dest.resolve() != old_path.resolve():
            print(f"  [충돌·스킵] 이미 존재: {dest.name}")
            conflict += 1
            continue
        if dry_run:
            print(f"  [예정] {old_path.name} → {new_name}")
            ok += 1
        else:
            old_path.rename(dest)
            print(f"  OK    {old_path.name} → {new_name}")
            ok += 1

    return ok, skip, conflict


def process_tree(root: Path, *, dry_run: bool) -> None:
    """루트 아래 모든 디렉터리에서 파일 이름 정규화."""
    dirs_list = collect_all_directories(root)
    total_ok = total_skip = total_conflict = 0

    for folder in dirs_list:
        files_here = [p for p in folder.iterdir() if p.is_file()]
        if not files_here:
            continue

        print(f"\n[{folder}] ({len(files_here)}개 파일)")
        ok, skip, cf = rename_files_in_folder(folder, dry_run=dry_run)
        total_ok += ok
        total_skip += skip
        total_conflict += cf
        if skip and ok == 0 and cf == 0:
            print(f"  (변경 없음 · 패턴 불일치 스킵 {skip}개)")
        elif skip and (ok or cf):
            print(f"  (패턴 불일치 등 스킵 {skip}개)")

    mode = "DRY-RUN" if dry_run else "실행"
    print(f"\n=== 요약 [{mode}] ===")
    print(f"  이름 변경(예정): {total_ok}")
    print(f"  스킵(파일명 끝에 _숫자 없음 또는 이미 목표 이름): {total_skip}")
    print(f"  충돌: {total_conflict}")


def pick_folder_gui() -> Path | None:
    """PyQt5 폴더 선택 대화상자."""
    try:
        import PyQt5

        os.environ.setdefault(
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforms"),
        )
        from PyQt5.QtWidgets import QApplication, QFileDialog
    except ImportError:
        print("PyQt5 가 없습니다. --root 로 경로를 넘겨 주세요.", file=sys.stderr)
        return None

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    folder_str = QFileDialog.getExistingDirectory(None, "상위 폴더 선택", "")
    if not folder_str:
        return None
    return Path(folder_str)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="각 하위 폴더 안 파일을 `{폴더명}_번호.확장자` 로 통일합니다."
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="상위 폴더 경로 (미지정 시 폴더 선택 창)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 이름 변경 없이 출력만",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root: Path | None
    if args.root:
        root = Path(args.root).expanduser()
        if not root.is_dir():
            print(f"폴더가 아닙니다: {root}", file=sys.stderr)
            return 1
    else:
        root = pick_folder_gui()
        if root is None:
            print("취소됨.", file=sys.stderr)
            return 1

    process_tree(root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
