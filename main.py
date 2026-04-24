#!/usr/bin/env python3
"""
크롤링 도구 - 페이지네이션 테스터 (Refactored)

사용법:
    python main.py

구조:
    shared/   - 공유 상수, 설정, 프록시 관리
    utils/    - 유틸리티 (쿠키, Cloudflare, SVG, 언어)
    core/     - 크롤링 핵심 로직 (7개 모듈)
    widgets/  - Tkinter GUI
"""
import sys
import os

# 프로젝트 루트를 sys.path에 추가 (패키지 import 지원)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# .env 파일 로드 (원본 Crawling Code 디렉토리의 .env도 확인)
from dotenv import load_dotenv

# 현재 디렉토리의 .env
load_dotenv()

# 원본 Crawling Code 디렉토리의 .env (fallback)
original_env = os.path.join(PROJECT_ROOT, '..', 'Crawling Code', '.env')
if os.path.exists(original_env):
    load_dotenv(original_env)


def main():
    """GUI 실행"""
    import tkinter as tk
    from widgets.pagination_gui import PaginationTesterGUI

    root = tk.Tk()

    # DPI 인식 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = PaginationTesterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
