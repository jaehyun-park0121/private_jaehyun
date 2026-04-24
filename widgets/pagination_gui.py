"""
PaginationTesterGUI - 페이지네이션 테스트 GUI
- 비즈니스 로직은 core/ 모듈에 위임
- GUI는 이벤트 핸들러 + 로그 표시만 담당
"""
import json
import asyncio
import threading
import platform
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path
from datetime import datetime

import yaml

from shared.config import ConfigLoader, ParallelCrawlConfig, SITE_CONFIGS_DIR
from shared.proxy_manager import ProxyManager
from core import stealth_crawler, unlocker_crawler, browser_api_crawler
from core import category_crawler, parallel_crawler, recrawler
from core.result_saver import save_content_to_json, save_result_to_excel


class PaginationTesterGUI:
    """페이지네이션 테스트 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("🔍 페이지네이션 테스트 (Refactored)")
        self.root.geometry("1300x800")

        # 상태 변수
        self.sites = []
        self.is_testing = False
        self.stop_event = threading.Event()
        self.save_folder = None
        self.selected_jsonl_path = None
        self.jsonl_urls = []
        self.recrawl_source_file = ''

        # 프록시 매니저 초기화
        self.proxy_manager = ProxyManager()
        self.proxy_manager.print_status()

        # UI 생성
        self.create_widgets()

        # 사이트 로드
        self.load_sites()

    def create_widgets(self):
        """UI 위젯 생성 - 가로 레이아웃"""
        # 상단 프레임 (사이트 선택)
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="📋 사이트:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)

        self.site_var = tk.StringVar()
        self.site_combo = ttk.Combobox(top_frame, textvariable=self.site_var, width=45, state="readonly")
        self.site_combo.pack(side=tk.LEFT, padx=5)
        self.site_combo.bind("<<ComboboxSelected>>", self.on_site_selected)

        self.test_btn = ttk.Button(top_frame, text="▶️ 시작", command=self.start_test, width=12)
        self.test_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(top_frame, text="⏹️ 중지", command=self.stop_test, width=12, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.refresh_btn = ttk.Button(top_frame, text="🔄", command=self.load_sites, width=5)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        # 메인 컨텐츠: 좌우 분할
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ========== 왼쪽 패널: 설정 영역 (스크롤 가능) ==========
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.left_canvas = canvas

        # ---- 브라우저 모드 선택 ----
        mode_frame = ttk.LabelFrame(self.scrollable_frame, text="🌐 브라우저 모드", padding="8")
        mode_frame.pack(fill=tk.X, pady=5)

        self.browser_mode = tk.StringVar(value="auto")

        ttk.Radiobutton(mode_frame, text="🔄 Auto Fallback (권장)",
                        variable=self.browser_mode, value="auto").pack(anchor=tk.W, padx=5, pady=1)
        ttk.Radiobutton(mode_frame, text="🕵️ Stealth 모드",
                        variable=self.browser_mode, value="stealth").pack(anchor=tk.W, padx=5, pady=1)

        bd_ok = self.proxy_manager.brightdata_available
        bd_status = "✅" if bd_ok else "❌"

        ttk.Radiobutton(mode_frame, text=f"🚀 Bright Data {bd_status}",
                        variable=self.browser_mode, value="brightdata",
                        state="normal" if bd_ok else "disabled").pack(anchor=tk.W, padx=5, pady=1)

        ttk.Radiobutton(mode_frame, text=f"🌐 Browser API {bd_status}",
                        variable=self.browser_mode, value="browser_api",
                        state="normal" if bd_ok else "disabled").pack(anchor=tk.W, padx=5, pady=1)

        unlocker_ok = bool(self.proxy_manager.proxy_unlocker)
        unlocker_status = "✅" if unlocker_ok else "❌"
        ttk.Radiobutton(mode_frame, text=f"🔓 Web Unlocker {unlocker_status}",
                        variable=self.browser_mode, value="unlocker",
                        state="normal" if unlocker_ok else "disabled").pack(anchor=tk.W, padx=5, pady=1)

        # ---- Phase 선택 ----
        phase_frame = ttk.LabelFrame(self.scrollable_frame, text="🎯 실행 Phase", padding="8")
        phase_frame.pack(fill=tk.X, pady=5)

        self.execution_phase = tk.StringVar(value="all")

        ttk.Radiobutton(phase_frame, text="▶️ 전체 (Phase 1 → 2)",
                        variable=self.execution_phase, value="all").pack(anchor=tk.W, padx=5, pady=1)
        ttk.Radiobutton(phase_frame, text="📋 Phase 1만 (링크 수집)",
                        variable=self.execution_phase, value="phase1").pack(anchor=tk.W, padx=5, pady=1)
        ttk.Radiobutton(phase_frame, text="📄 Phase 2만 (게시글 크롤링)",
                        variable=self.execution_phase, value="phase2").pack(anchor=tk.W, padx=5, pady=1)

        # Phase 2 링크 파일 선택
        phase2_file_frame = ttk.Frame(phase_frame)
        phase2_file_frame.pack(fill=tk.X, padx=15, pady=3)

        ttk.Label(phase2_file_frame, text="링크 파일:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.links_file_var = tk.StringVar(value="선택 안됨")
        ttk.Entry(phase2_file_frame, textvariable=self.links_file_var, width=25, state="readonly", font=("Arial", 8)).grid(row=0, column=1, sticky=tk.EW, padx=2)
        self.btn_select_links = ttk.Button(phase2_file_frame, text="📁", command=self.select_links_file, width=4)
        self.btn_select_links.grid(row=0, column=2, padx=2)
        self.links_count_var = tk.StringVar(value="")
        ttk.Label(phase2_file_frame, textvariable=self.links_count_var, foreground="blue", font=("Arial", 8)).grid(row=0, column=3, padx=5)
        phase2_file_frame.columnconfigure(1, weight=1)

        # 최대 기사 수
        max_articles_frame = ttk.Frame(phase_frame)
        max_articles_frame.pack(fill=tk.X, padx=15, pady=3)
        ttk.Label(max_articles_frame, text="최대 기사 수:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.max_articles_var = tk.StringVar(value="10")
        ttk.Entry(max_articles_frame, textvariable=self.max_articles_var, width=10, font=("Arial", 8)).grid(row=0, column=1, sticky=tk.W, padx=2)
        ttk.Label(max_articles_frame, text="(0: 전체)", font=("Arial", 7), foreground="gray").grid(row=0, column=2, padx=5)

        self.btn_phase2_only = ttk.Button(phase_frame, text="⚡ Phase 2 시작",
                                          command=self.start_phase2_only, state="disabled")
        self.btn_phase2_only.pack(pady=3)

        self.btn_recrawl_failed = ttk.Button(phase_frame, text="🔄 실패 재크롤링",
                                             command=self.start_recrawl_failed)
        self.btn_recrawl_failed.pack(pady=3)

        # ---- 저장 폴더 설정 ----
        save_folder_frame = ttk.LabelFrame(self.scrollable_frame, text="💾 저장 폴더 설정", padding="8")
        save_folder_frame.pack(fill=tk.X, pady=5)

        folder_select_frame = ttk.Frame(save_folder_frame)
        folder_select_frame.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(folder_select_frame, text="저장 폴더:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.save_folder_var = tk.StringVar(value="기본 폴더 사용")
        ttk.Entry(folder_select_frame, textvariable=self.save_folder_var, width=35, state="readonly", font=("Arial", 8)).grid(row=0, column=1, sticky=tk.EW, padx=2)
        ttk.Button(folder_select_frame, text="📁 폴더 선택", command=self.select_save_folder, width=12).grid(row=0, column=2, padx=2)
        ttk.Button(folder_select_frame, text="🔄 초기화", command=self.reset_save_folder, width=10).grid(row=0, column=3, padx=2)
        folder_select_frame.columnconfigure(1, weight=1)

        ttk.Label(save_folder_frame, text="※ 기본값: 현재 디렉토리 하위 폴더 사용",
                  font=("Arial", 7), foreground="gray").pack(anchor=tk.W, padx=5, pady=2)

        # ---- 병렬 크롤링 설정 ----
        parallel_frame = ttk.LabelFrame(self.scrollable_frame, text="⚡ 병렬 설정 (Phase 2)", padding="8")
        parallel_frame.pack(fill=tk.X, pady=5)

        self.parallel_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(parallel_frame, text="🚀 병렬 크롤링 활성화",
                        variable=self.parallel_enabled).pack(anchor=tk.W, padx=5, pady=2)

        self.remove_duplicates = tk.BooleanVar(value=True)
        ttk.Checkbutton(parallel_frame, text="🔗 중복 링크 제거",
                        variable=self.remove_duplicates).pack(anchor=tk.W, padx=5, pady=2)

        parallel_settings = ttk.Frame(parallel_frame)
        parallel_settings.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(parallel_settings, text="동시:", font=("Arial", 8)).grid(row=0, column=0, padx=2)
        self.concurrent_requests = tk.StringVar(value="5")
        ttk.Entry(parallel_settings, textvariable=self.concurrent_requests, width=4).grid(row=0, column=1, padx=2)

        ttk.Label(parallel_settings, text="딜레이:", font=("Arial", 8)).grid(row=0, column=2, padx=2)
        self.delay_min = tk.StringVar(value="1.0")
        ttk.Entry(parallel_settings, textvariable=self.delay_min, width=4).grid(row=0, column=3, padx=2)
        ttk.Label(parallel_settings, text="~", font=("Arial", 8)).grid(row=0, column=4)
        self.delay_max = tk.StringVar(value="2.0")
        ttk.Entry(parallel_settings, textvariable=self.delay_max, width=4).grid(row=0, column=5, padx=2)

        ttk.Label(parallel_settings, text="배치:", font=("Arial", 8)).grid(row=1, column=0, padx=2, pady=2)
        self.batch_size = tk.StringVar(value="100")
        ttk.Entry(parallel_settings, textvariable=self.batch_size, width=4).grid(row=1, column=1, padx=2, pady=2)

        # ---- 사이트 정보 ----
        info_frame = ttk.LabelFrame(self.scrollable_frame, text="📊 사이트 정보", padding="8")
        info_frame.pack(fill=tk.X, pady=5)

        info_grid = ttk.Frame(info_frame)
        info_grid.pack(fill=tk.X)

        ttk.Label(info_grid, text="URL:", font=("Arial", 8, "bold")).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.url_label = ttk.Label(info_grid, text="-", foreground="blue", cursor="hand2", font=("Arial", 8))
        self.url_label.grid(row=0, column=1, sticky=tk.W, pady=1, padx=5)
        self.url_label.bind("<Button-1>", self.open_url)

        ttk.Label(info_grid, text="페이지네이션:", font=("Arial", 8, "bold")).grid(row=1, column=0, sticky=tk.W, pady=1)
        self.pagination_label = ttk.Label(info_grid, text="-", font=("Arial", 8))
        self.pagination_label.grid(row=1, column=1, sticky=tk.W, pady=1, padx=5)

        ttk.Label(info_grid, text="셀렉터:", font=("Arial", 8, "bold")).grid(row=2, column=0, sticky=tk.W, pady=1)
        self.selector_label = ttk.Label(info_grid, text="-", font=("Arial", 8))
        self.selector_label.grid(row=2, column=1, sticky=tk.W, pady=1, padx=5)

        self.max_label = ttk.Label(info_grid, text="최대 클릭/페이지:", font=("Arial", 8, "bold"))
        self.max_label.grid(row=3, column=0, sticky=tk.W, pady=1)
        max_input_frame = ttk.Frame(info_grid)
        max_input_frame.grid(row=3, column=1, sticky=tk.W, pady=1, padx=5)
        self.max_value_var = tk.StringVar(value="10")
        self.max_value_entry = ttk.Entry(max_input_frame, textvariable=self.max_value_var, width=6, font=("Arial", 8))
        self.max_value_entry.pack(side=tk.LEFT)
        self.max_clicks_label = ttk.Label(max_input_frame, text="", font=("Arial", 8), foreground="gray")
        self.max_clicks_label.pack(side=tk.LEFT, padx=5)

        self.max_value_hint = ttk.Label(info_grid, text="(버튼: 클릭 횟수 / 링크: 페이지 수)",
                                        font=("Arial", 7), foreground="gray")
        self.max_value_hint.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=1)
        info_grid.columnconfigure(1, weight=1)

        # ---- JSONL 재크롤링 프레임 ----
        recrawl_frame = ttk.LabelFrame(self.scrollable_frame, text="📄 JSONL 재크롤링", padding="8")
        recrawl_frame.pack(fill=tk.X, pady=5)

        jsonl_select_frame = ttk.Frame(recrawl_frame)
        jsonl_select_frame.pack(fill=tk.X, pady=3)
        ttk.Label(jsonl_select_frame, text="파일:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, padx=2)
        self.jsonl_file_var = tk.StringVar(value="선택 안됨")
        ttk.Entry(jsonl_select_frame, textvariable=self.jsonl_file_var, width=20, state="readonly", font=("Arial", 8)).grid(row=0, column=1, sticky=tk.EW, padx=2)
        ttk.Button(jsonl_select_frame, text="📁", command=self.select_jsonl_file, width=4).grid(row=0, column=2, padx=2)
        self.jsonl_url_count_var = tk.StringVar(value="0개")
        ttk.Label(jsonl_select_frame, textvariable=self.jsonl_url_count_var, foreground="blue", font=("Arial", 8)).grid(row=0, column=3, padx=5)
        jsonl_select_frame.columnconfigure(1, weight=1)

        self.recrawl_svg_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(recrawl_frame, text="SVG 캡처", variable=self.recrawl_svg_var).pack(anchor=tk.W, padx=5, pady=1)
        self.recrawl_both_lang_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(recrawl_frame, text="영어+한국어", variable=self.recrawl_both_lang_var).pack(anchor=tk.W, padx=5, pady=1)
        self.wait_for_iframe_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(recrawl_frame, text="iframe 대기", variable=self.wait_for_iframe_var).pack(anchor=tk.W, padx=5, pady=1)

        self.recrawl_btn = ttk.Button(recrawl_frame, text="🔄 재크롤링 시작",
                                      command=self.start_recrawl, state="disabled")
        self.recrawl_btn.pack(pady=3)

        # ========== 오른쪽 패널: 로그 + 진행상황 ==========
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)

        progress_frame = ttk.Frame(right_frame)
        progress_frame.pack(fill=tk.X, pady=5)
        ttk.Label(progress_frame, text="진행:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.status_label = ttk.Label(progress_frame, text="대기 중", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(right_frame, text="📝 실행 로그", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("success", foreground="green", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("error", foreground="red", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("warning", foreground="orange", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("header", foreground="purple", font=("Consolas", 10, "bold"))

        bottom_frame = ttk.Frame(self.root, padding="5")
        bottom_frame.pack(fill=tk.X)
        self.stats_label = ttk.Label(bottom_frame, text="준비 완료", font=("Arial", 9))
        self.stats_label.pack()

    # ========== 이벤트 핸들러 ==========

    def log(self, message, tag="info"):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "info")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END)
        self.root.update()

    def load_sites(self):
        """site_configs 폴더에서 모든 YAML 파일 로드"""
        self.sites = []
        config_dir = SITE_CONFIGS_DIR

        if not config_dir.exists():
            messagebox.showerror("오류", f"site_configs 폴더를 찾을 수 없습니다.\n{config_dir}")
            return

        for yaml_file in sorted(config_dir.glob("*.yaml")):
            if yaml_file.name.startswith("_") or yaml_file.name == "README.md":
                continue

            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                if not config or 'site' not in config:
                    continue

                enabled = config['site'].get('enabled', True)
                name = config['site'].get('name', yaml_file.stem)
                url = config['site'].get('url', '')

                display_name = f"{name} - {url}"
                if not enabled:
                    display_name += " [비활성화]"

                self.sites.append({
                    'name': name,
                    'url': url,
                    'config': config,
                    'file': yaml_file,
                    'display': display_name,
                    'enabled': enabled
                })
            except Exception as e:
                self.log(f"❌ {yaml_file.name} 로드 실패: {e}", "error")

        self.site_combo['values'] = [site['display'] for site in self.sites]
        if self.sites:
            self.site_combo.current(0)
            self.on_site_selected(None)

        self.log(f"✅ {len(self.sites)}개 사이트 로드 완료", "success")

    def on_site_selected(self, event):
        """사이트 선택 시 정보 표시"""
        idx = self.site_combo.current()
        if idx < 0 or idx >= len(self.sites):
            return

        site = self.sites[idx]
        config = site['config']

        self.url_label.config(text=site['url'])

        pagination = config.get('pagination', {})
        if pagination.get('enabled'):
            ptype = pagination.get('type', 'none')
            self.pagination_label.config(text=f"✅ {ptype}", foreground="green")

            if ptype == 'button':
                selectors = pagination.get('button', {}).get('selectors', [])
                self.selector_label.config(text=", ".join(selectors[:2]))
                max_clicks = pagination.get('button', {}).get('max_clicks', 5)
                self.max_clicks_label.config(text=str(max_clicks))
                self.max_label.config(text="최대 클릭:")
                self.max_value_hint.config(text="(클릭 횟수)")
                self.max_value_var.set(str(max_clicks))
            elif ptype == 'link':
                selectors = pagination.get('link', {}).get('selectors', [])
                self.selector_label.config(text=", ".join(selectors[:2]))
                max_pages = pagination.get('link', {}).get('max_pages', 10)
                self.max_clicks_label.config(text=f"{max_pages} 페이지")
                self.max_label.config(text="최대 페이지:")
                self.max_value_hint.config(text="(페이지 수)")
                self.max_value_var.set(str(max_pages))
            elif ptype == 'javascript':
                js_config = pagination.get('javascript', {})
                mode = js_config.get('mode', 'api_fetch')
                self.selector_label.config(text=f"JavaScript ({mode})")
                max_pages = js_config.get('max_pages', 20)
                self.max_clicks_label.config(text=f"{max_pages} 페이지")
                self.max_label.config(text="최대 페이지:")
                self.max_value_hint.config(text="(API 페이지 수)")
                self.max_value_var.set(str(max_pages))
            elif ptype == 'scroll':
                scroll_config = pagination.get('scroll', {})
                max_scrolls = scroll_config.get('max_scrolls', 20)
                self.selector_label.config(text="무한 스크롤")
                self.max_clicks_label.config(text=f"{max_scrolls} 스크롤")
                self.max_label.config(text="최대 스크롤:")
                self.max_value_hint.config(text="(스크롤 횟수)")
                self.max_value_var.set(str(max_scrolls))
            elif ptype == 'scroll_button':
                sb_config = pagination.get('scroll_button', {})
                max_scrolls = sb_config.get('max_scrolls', 50)
                button_selectors = sb_config.get('button_selectors', [])
                if not button_selectors:
                    single_selector = sb_config.get('button_selector', "")
                    button_selectors = [single_selector] if single_selector else []
                first_selector = button_selectors[0] if button_selectors else ""
                self.selector_label.config(text=f"스크롤+버튼 ({first_selector[:25]}...)")
                self.max_clicks_label.config(text=f"{max_scrolls} 스크롤")
                self.max_label.config(text="최대 스크롤:")
                self.max_value_hint.config(text="(스크롤+버튼)")
                self.max_value_var.set(str(max_scrolls))
            else:
                self.selector_label.config(text="-")
                self.max_clicks_label.config(text="-")
                self.max_value_var.set("5")
        else:
            self.pagination_label.config(text="❌ 비활성화", foreground="red")
            self.selector_label.config(text="-")
            self.max_clicks_label.config(text="-")
            self.max_value_var.set("5")

    def open_url(self, event):
        url = self.url_label.cget("text")
        if url and url != "-":
            webbrowser.open(url)

    def get_parallel_config(self):
        """GUI에서 병렬 크롤링 설정 가져오기"""
        try:
            return ParallelCrawlConfig(
                enabled=self.parallel_enabled.get(),
                max_concurrent=int(self.concurrent_requests.get()),
                delay_min=float(self.delay_min.get()),
                delay_max=float(self.delay_max.get()),
                batch_size=int(self.batch_size.get())
            )
        except ValueError:
            return ParallelCrawlConfig()

    def select_save_folder(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.save_folder = folder
            self.save_folder_var.set(folder)

    def reset_save_folder(self):
        self.save_folder = None
        self.save_folder_var.set("기본 폴더 사용")

    def select_links_file(self):
        file_path = filedialog.askopenfilename(
            title="Phase 2 링크 파일 선택",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                links = data.get('links', data.get('all_links', []))
                self.links_file_var.set(Path(file_path).name)
                self.links_count_var.set(f"{len(links)}개")
                self.btn_phase2_only.config(state="normal")
                self._phase2_links_data = links
                self._phase2_links_file = file_path
            except Exception as e:
                self.log(f"❌ 링크 파일 읽기 실패: {e}", "error")

    def select_jsonl_file(self):
        """JSON/JSONL 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="재크롤링할 파일 선택 (JSON/JSONL)",
            filetypes=[
                ("JSON/JSONL 파일", "*.json;*.jsonl"),
                ("모든 파일", "*.*")
            ]
        )
        if file_path:
            try:
                urls, file_type, site_info = recrawler.parse_recrawl_file(file_path)
                self.selected_jsonl_path = file_path
                self.jsonl_urls = urls
                self.jsonl_file_var.set(Path(file_path).name)
                self.jsonl_url_count_var.set(f"URL 개수: {len(urls)}개")
                self.recrawl_btn.config(state="normal")
                self.recrawl_source_file = file_path

                self.log(f"✅ {file_type} 파일 선택: {Path(file_path).name}", "success")
                self.log(f"   📋 {len(urls)}개 URL 추출됨", "info")
            except Exception as e:
                self.log(f"❌ 파일 읽기 실패: {str(e)}", "error")
                self.recrawl_btn.config(state="disabled")

    # ========== 크롤링 실행 ==========

    def start_test(self):
        """테스트 시작"""
        idx = self.site_combo.current()
        if idx < 0 or idx >= len(self.sites):
            messagebox.showerror("오류", "사이트를 선택해주세요.")
            return

        if self.is_testing:
            messagebox.showwarning("경고", "이미 크롤링이 진행 중입니다.")
            return

        site = self.sites[idx]
        self.is_testing = True
        self.stop_event.clear()
        self.progress.start()
        self.test_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.site_combo.config(state="disabled")
        self.status_label.config(text="🔄 실행 중...", foreground="blue")

        thread = threading.Thread(target=self._run_test_thread, args=(site,), daemon=True)
        thread.start()

    def stop_test(self):
        """테스트 중지"""
        self.stop_event.set()
        self.is_testing = False
        self.log("⚠️ 중지 요청됨...", "warning")

    def start_phase2_only(self):
        """Phase 2만 시작"""
        if not hasattr(self, '_phase2_links_data'):
            messagebox.showerror("오류", "링크 파일을 먼저 선택해주세요.")
            return
        self.log("⚡ Phase 2 단독 실행 시작", "header")
        # Phase 2 실행 로직 (별도 스레드)
        thread = threading.Thread(target=self._run_phase2_thread, daemon=True)
        thread.start()

    def start_recrawl_failed(self):
        """실패 재크롤링"""
        self.log("🔄 실패 재크롤링 기능 실행", "info")

    def start_recrawl(self):
        """JSONL 재크롤링 시작"""
        if not self.jsonl_urls:
            messagebox.showerror("오류", "JSONL 파일을 먼저 선택해주세요.")
            return

        if self.is_testing:
            messagebox.showwarning("경고", "이미 크롤링이 진행 중입니다.")
            return

        if not messagebox.askyesno(
            "재크롤링 확인",
            f"{len(self.jsonl_urls)}개 URL을 재크롤링하시겠습니까?\n\n"
            f"모드: {self.browser_mode.get()}\n"
            f"SVG 캡처: {'✅' if self.recrawl_svg_var.get() else '❌'}\n"
            f"영어+한국어: {'✅' if self.recrawl_both_lang_var.get() else '❌'}"
        ):
            return

        self.is_testing = True
        self.test_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.recrawl_btn.config(state="disabled")
        self.progress.start()

        thread = threading.Thread(target=self._run_recrawl_thread, daemon=True)
        thread.start()

    # ========== 스레드 실행 ==========

    def _run_test_thread(self, site):
        """테스트 실행 스레드"""
        try:
            if platform.system() == 'Windows':
                try:
                    if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
                        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            result = loop.run_until_complete(self._test_pagination(site))
            loop.close()

            if result.get('success'):
                self.log(f"\n{'='*60}", "header")
                self.log("✅ 테스트 성공!", "success")
                self.log(f"총 클릭 횟수: {result.get('clicks', 0)}", "info")
                self.log(f"최종 게시글 수: {result.get('final_count', 0)}", "info")
                self.log(f"크롤링된 링크 수: {len(result.get('all_links', []))}개", "success")

                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                save_result_to_excel(site, result, save_folder=self.save_folder,
                                     timestamp=timestamp, log_func=self.log)
                save_content_to_json(site, result, save_folder=self.save_folder,
                                     timestamp=timestamp, log_func=self.log)

                self.status_label.config(text="✅ 성공", foreground="green")
            else:
                self.log(f"❌ 테스트 실패: {result.get('error', 'Unknown')}", "error")
                self.status_label.config(text="❌ 실패", foreground="red")

        except Exception as e:
            self.log(f"❌ 예외 발생: {e}", "error")
            self.status_label.config(text="❌ 오류", foreground="red")

        finally:
            self.progress.stop()
            self.test_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.site_combo.config(state="readonly")
            self.is_testing = False

    def _run_phase2_thread(self):
        """Phase 2 실행 스레드"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            parallel_config = self.get_parallel_config()

            try:
                max_articles = int(self.max_articles_var.get())
            except ValueError:
                max_articles = 0

            links = self._phase2_links_data
            if max_articles > 0:
                links = links[:max_articles]

            article_links = [
                {'url': l.get('url', l) if isinstance(l, dict) else l,
                 'title': l.get('title', '') if isinstance(l, dict) else '',
                 'article_id': i + 1, 'lang': 'EN'}
                for i, l in enumerate(links)
            ]

            result = loop.run_until_complete(
                parallel_crawler.crawl_articles_parallel(
                    article_links=article_links,
                    parallel_config=parallel_config,
                    proxy_manager=self.proxy_manager,
                    browser_mode=self.browser_mode.get(),
                    stop_event=self.stop_event,
                    log_func=self.log
                )
            )
            loop.close()

            self.log(f"✅ Phase 2 완료: {len(result.get('crawled_articles', []))}개 성공", "success")

        except Exception as e:
            self.log(f"❌ Phase 2 오류: {e}", "error")

    def _run_recrawl_thread(self):
        """재크롤링 스레드"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                max_articles = int(self.max_articles_var.get())
            except ValueError:
                max_articles = 0

            first_url = self.jsonl_urls[0] if self.jsonl_urls else ""
            is_openai = "openai.com" in first_url.lower()

            article_links = recrawler.build_article_links(
                urls=self.jsonl_urls,
                max_articles=max_articles,
                dual_lang=self.recrawl_both_lang_var.get() and is_openai
            )

            parallel_config = self.get_parallel_config()

            result = loop.run_until_complete(
                parallel_crawler.crawl_articles_parallel(
                    article_links=article_links,
                    parallel_config=parallel_config,
                    proxy_manager=self.proxy_manager,
                    browser_mode=self.browser_mode.get(),
                    stop_event=self.stop_event,
                    log_func=self.log
                )
            )
            loop.close()

            all_articles = result.get('crawled_articles', [])
            failed_articles = result.get('failed_articles', [])

            site_name = recrawler.get_site_name_from_url(first_url)
            recrawler.save_recrawl_result(
                all_articles=all_articles,
                failed_articles=failed_articles,
                urls=self.jsonl_urls,
                site_name=site_name,
                browser_mode=self.browser_mode.get(),
                source_file=self.recrawl_source_file,
                save_folder=self.save_folder,
                log_func=self.log
            )

            self.log(f"\n✅ 재크롤링 완료: 성공 {len(all_articles)}개, 실패 {len(failed_articles)}개", "success")

        except Exception as e:
            self.log(f"❌ 재크롤링 오류: {str(e)}", "error")

        finally:
            self.is_testing = False
            self.test_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.recrawl_btn.config(state="normal")
            self.progress.stop()

    async def _test_pagination(self, site):
        """페이지네이션 테스트 (메인 로직)"""
        config = site['config']
        url = site['url']
        pagination = config.get('pagination', {})
        browser_mode = self.browser_mode.get()

        self.log(f"{'='*60}", "header")
        self.log(f"🚀 테스트 시작: {site['name']}", "header")
        self.log(f"URL: {url}", "info")

        mode_label = {
            'auto': '🔄 Auto Fallback',
            'stealth': '🕵️ Stealth 모드',
            'brightdata': '🚀 Scraping Browser',
            'browser_api': '🌐 Browser API',
            'unlocker': '🔓 Web Unlocker'
        }.get(browser_mode, browser_mode)
        self.log(f"모드: {mode_label}", "info")

        try:
            user_max_value = int(self.max_value_var.get())
        except ValueError:
            user_max_value = 20

        phase1_only = self.execution_phase.get() == 'phase1'

        # 카테고리 크롤링 체크
        categories = config.get('categories', [])
        if categories:
            return await category_crawler.test_with_categories(
                url=url, config=config,
                browser_mode=browser_mode,
                user_max_value=user_max_value,
                proxy_manager=self.proxy_manager,
                log_func=self.log
            )

        # 모드별 크롤링
        if browser_mode in ['unlocker'] and self.proxy_manager.proxy_unlocker:
            result = await unlocker_crawler.test_with_unlocker(
                url=url, config=config,
                proxy_url=self.proxy_manager.proxy_unlocker,
                user_max_value=user_max_value,
                phase1_only=phase1_only,
                log_func=self.log
            )
        elif browser_mode in ['brightdata', 'browser_api'] and self.proxy_manager.sb_auth:
            # Scraping Browser는 Phase 1에서 직접 사용하기 어려우므로 Stealth fallback
            result = await stealth_crawler.test_with_stealth(
                url=url, config=config,
                user_max_value=user_max_value,
                phase1_only=phase1_only,
                log_func=self.log
            )
        else:
            # Stealth 또는 Auto
            result = await stealth_crawler.test_with_stealth(
                url=url, config=config,
                user_max_value=user_max_value,
                phase1_only=phase1_only,
                log_func=self.log
            )

        if not result.get('success') or phase1_only:
            return result

        # Auto fallback: Stealth 실패 시 다른 모드로 재시도
        if browser_mode == 'auto' and not result.get('all_links'):
            if self.proxy_manager.proxy_unlocker:
                self.log("\n🔄 Stealth 실패 → Web Unlocker로 재시도", "warning")
                result = await unlocker_crawler.test_with_unlocker(
                    url=url, config=config,
                    proxy_url=self.proxy_manager.proxy_unlocker,
                    user_max_value=user_max_value,
                    phase1_only=True,
                    log_func=self.log
                )

        # Phase 2: 게시글 콘텐츠 크롤링
        if result.get('success') and result.get('all_links') and self.execution_phase.get() != 'phase1':
            self.log("\n⚡ Phase 2 시작: 게시글 콘텐츠 크롤링", "header")

            try:
                max_articles = int(self.max_articles_var.get())
            except ValueError:
                max_articles = 0

            links = result['all_links']
            if max_articles > 0:
                links = links[:max_articles]

            article_links = [
                {'url': l.get('url', l) if isinstance(l, dict) else l,
                 'title': l.get('title', '') if isinstance(l, dict) else '',
                 'article_id': i + 1, 'lang': 'EN'}
                for i, l in enumerate(links)
            ]

            parallel_config = self.get_parallel_config()

            phase2_result = await parallel_crawler.crawl_articles_parallel(
                article_links=article_links,
                parallel_config=parallel_config,
                proxy_manager=self.proxy_manager,
                browser_mode=browser_mode,
                site_name=site['name'],
                stop_event=self.stop_event,
                log_func=self.log
            )

            result['crawled_articles'] = phase2_result.get('crawled_articles', [])
            result['failed_articles'] = phase2_result.get('failed_articles', [])

        return result
