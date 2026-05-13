import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog, ttk
import boto3
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 설정 파일 경로 (스크립트와 같은 폴더에 저장)
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aws_tool_settings.json")

class S3DownloaderGUI:
    def __init__(self, master):
        self.master = master
        master.title("AWS 데이터 관리 TOOL")
        master.geometry("800x600")  # 크기 크게 변경

        # 설정 불러오기
        self.settings = self._load_settings()

        # 첫 화면: 업로드/다운로드/도서 반려 처리 분기
        self.main_frame = ttk.Frame(master)
        self.main_frame.pack(expand=True)

        ttk.Label(self.main_frame, text="AWS 데이터 관리 TOOL", font=("Arial", 16, "bold")).pack(pady=20)

        btn_frame = ttk.Frame(self.main_frame)
        btn_frame.pack(pady=10)

        self.upload_button = ttk.Button(btn_frame, text="업로드", command=self.show_upload_config)
        self.upload_button.pack(side="left", padx=20)

        self.download_button = ttk.Button(btn_frame, text="다운로드", command=self.show_download_config)
        self.download_button.pack(side="left", padx=20)

        # 리스트 다운로드 버튼 추가
        self.list_download_json_path_var = tk.StringVar()
        self.list_download_files_to_download = []
        self.list_download_total_files_var = tk.StringVar(value="Total files to download: 0")
        self.list_download_button = ttk.Button(btn_frame, text="리스트 다운로드", command=self.show_list_download_config)
        self.list_download_button.pack(side="left", padx=20)

        # 도서 반려 처리 버튼 추가
        self.reject_button = ttk.Button(btn_frame, text="도서 반려 처리", command=self.show_reject_process)
        self.reject_button.pack(side="left", padx=20)

        # 다운로드 관련 변수 초기화
        self.s3 = None
        self.download_dir = os.path.expanduser("~")  # 기본 다운로드 경로
        self.download_path_var = tk.StringVar(value=self.download_dir)
        self.list_download_specific_path_var = tk.StringVar(value=self.download_dir) # For list download

    # ── 설정 저장/불러오기 ──────────────────────────────────────
    def _load_settings(self):
        """JSON 설정 파일에서 저장된 값을 불러온다."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_settings(self):
        """현재 self.settings 를 JSON 파일로 저장한다."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"설정 저장 실패: {e}")

    def _save_section(self, section, access_key, secret_key, region, bucket, project_id):
        """특정 섹션(upload/download/list_download/reject)의 설정을 저장한다."""
        self.settings[section] = {
            "aws_access_key": access_key,
            "aws_secret_key": secret_key,
            "aws_region": region,
            "bucket_name": bucket,
            "project_id": project_id,
        }
        self._save_settings()

    def _get_section(self, section):
        """특정 섹션의 저장된 설정 딕셔너리를 반환한다. 없으면 빈 dict."""
        return self.settings.get(section, {})

    def show_upload_config(self):
        self.main_frame.pack_forget()
        self.aws_frame = ttk.LabelFrame(self.master, text="AWS Configuration")
        self.aws_frame.pack(padx=20, pady=20, fill="x")
        self.create_aws_config_widgets(self.aws_frame, upload_mode=True)
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(self.aws_frame, text="뒤로가기", command=self.back_to_main)
        back_btn.grid(row=6, column=0, columnspan=2, pady=10)

    def show_upload_message(self):
        messagebox.showinfo("업로드", "업로드 기능은 아직 구현되지 않았습니다.")

    def show_download_config(self):
        # 기존 메인 프레임 숨기기
        self.main_frame.pack_forget()

        # 다운로드 설정 프레임 생성 및 표시
        self.aws_frame = ttk.LabelFrame(self.master, text="AWS Configuration")
        self.aws_frame.pack(padx=20, pady=20, fill="x")

        self.create_aws_config_widgets(self.aws_frame)
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(self.aws_frame, text="뒤로가기", command=self.back_to_main)
        back_btn.grid(row=6, column=0, columnspan=2, pady=10)

    def show_list_download_config(self):
        self.main_frame.pack_forget()
        self.list_download_frame = ttk.LabelFrame(self.master, text="리스트 다운로드 - AWS Configuration")
        self.list_download_frame.pack(padx=20, pady=20, fill="x")
        self.create_list_download_widgets(self.list_download_frame)
        back_btn = ttk.Button(self.list_download_frame, text="뒤로가기", command=self.back_to_main)
        # Adjust row index for back_btn due to new UI element
        back_btn.grid(row=9, column=0, columnspan=3, pady=10)

    def create_aws_config_widgets(self, parent, upload_mode=False):
        # 저장된 설정 불러오기 (업로드/다운로드 구분)
        section = "upload" if upload_mode else "download"
        saved = self._get_section(section)

        # AWS Access Key
        ttk.Label(parent, text="AWS Access Key:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.aws_access_key_entry = ttk.Entry(parent, width=50)
        self.aws_access_key_entry.insert(0, saved.get("aws_access_key", ""))
        self.aws_access_key_entry.grid(row=0, column=1, padx=5, pady=5)

        # AWS Secret Key
        ttk.Label(parent, text="AWS Secret Key:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.aws_secret_key_entry = ttk.Entry(parent, width=50, show="*")
        self.aws_secret_key_entry.insert(0, saved.get("aws_secret_key", ""))
        self.aws_secret_key_entry.grid(row=1, column=1, padx=5, pady=5)

        # AWS Region
        ttk.Label(parent, text="AWS Region:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.aws_region_entry = ttk.Entry(parent, width=50)
        self.aws_region_entry.insert(0, saved.get("aws_region", "ap-northeast-2"))
        self.aws_region_entry.grid(row=2, column=1, padx=5, pady=5)

        # Bucket Name
        ttk.Label(parent, text="Bucket Name:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.bucket_name_entry = ttk.Entry(parent, width=50)
        self.bucket_name_entry.insert(0, saved.get("bucket_name", "project-24-pd-021"))
        self.bucket_name_entry.grid(row=3, column=1, padx=5, pady=5)

        # Project ID
        ttk.Label(parent, text="Project ID:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.project_id_entry = ttk.Entry(parent, width=50)
        self.project_id_entry.insert(0, saved.get("project_id", "1760"))
        self.project_id_entry.grid(row=4, column=1, padx=5, pady=5)

        # _current_section 은 저장 시 사용
        self._current_section = section

        if upload_mode:
            self.connect_button = ttk.Button(parent, text="폴더 선택 및 목록 보기", command=self.show_local_folder_list)
            self.connect_button.grid(row=5, column=0, columnspan=2, pady=10)
        else:
            self.connect_button = ttk.Button(parent, text="Connect to S3 and Show Folders", command=self.connect_and_show_folders)
            self.connect_button.grid(row=5, column=0, columnspan=2, pady=10)

    def create_list_download_widgets(self, parent):
        # 저장된 설정 불러오기
        saved = self._get_section("list_download")

        # AWS 입력
        ttk.Label(parent, text="AWS Access Key:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.list_download_aws_access_key_entry = ttk.Entry(parent, width=50)
        self.list_download_aws_access_key_entry.insert(0, saved.get("aws_access_key", ""))
        self.list_download_aws_access_key_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(parent, text="AWS Secret Key:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.list_download_aws_secret_key_entry = ttk.Entry(parent, width=50, show="*")
        self.list_download_aws_secret_key_entry.insert(0, saved.get("aws_secret_key", ""))
        self.list_download_aws_secret_key_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(parent, text="AWS Region:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.list_download_aws_region_entry = ttk.Entry(parent, width=50)
        self.list_download_aws_region_entry.insert(0, saved.get("aws_region", "ap-northeast-2"))
        self.list_download_aws_region_entry.grid(row=2, column=1, padx=5, pady=5)
        ttk.Label(parent, text="Bucket Name:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.list_download_bucket_name_entry = ttk.Entry(parent, width=50)
        self.list_download_bucket_name_entry.insert(0, saved.get("bucket_name", "project-24-pd-021"))
        self.list_download_bucket_name_entry.grid(row=3, column=1, padx=5, pady=5)
        ttk.Label(parent, text="Project ID:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.list_download_project_id_entry = ttk.Entry(parent, width=50)
        self.list_download_project_id_entry.insert(0, saved.get("project_id", "1760"))
        self.list_download_project_id_entry.grid(row=4, column=1, padx=5, pady=5)

        # JSON 파일 선택
        ttk.Label(parent, text="JSON 파일 경로:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        json_path_entry = ttk.Entry(parent, textvariable=self.list_download_json_path_var, width=40)
        json_path_entry.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        json_browse_btn = ttk.Button(parent, text="파일 선택", command=self.select_list_download_json_file)
        json_browse_btn.grid(row=5, column=2, padx=5, pady=5)

        # 다운로드 폴더 경로 설정
        ttk.Label(parent, text="다운로드 폴더 경로:").grid(row=6, column=0, sticky="w", padx=5, pady=5)
        list_download_path_entry = ttk.Entry(parent, textvariable=self.list_download_specific_path_var, width=40)
        list_download_path_entry.grid(row=6, column=1, sticky="w", padx=5, pady=5)
        list_download_browse_btn = ttk.Button(parent, text="폴더 선택", command=self.browse_list_download_specific_dir)
        list_download_browse_btn.grid(row=6, column=2, padx=5, pady=5)

        # 다운로드 옵션 (adjust row index)
        ttk.Label(parent, text="다운로드 옵션:").grid(row=7, column=0, sticky="w", padx=5, pady=5)
        option_frame = ttk.Frame(parent)
        option_frame.grid(row=7, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        self.list_download_option_var = tk.StringVar(value="both")
        ttk.Radiobutton(option_frame, text="JSON만", variable=self.list_download_option_var, value="json").pack(side="left")
        ttk.Radiobutton(option_frame, text="PNG만", variable=self.list_download_option_var, value="png").pack(side="left")
        ttk.Radiobutton(option_frame, text="JSON+PNG", variable=self.list_download_option_var, value="both").pack(side="left")

        # 파일 개수 확인/다운로드 버튼 (adjust row index)
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=8, column=0, columnspan=3, pady=10)
        load_count_btn = ttk.Button(action_frame, text="파일 목록 불러오기 및 개수 확인", command=self.load_and_count_list_download_files)
        load_count_btn.pack(side="left", padx=5)
        self.list_download_total_files_label = ttk.Label(action_frame, textvariable=self.list_download_total_files_var)
        self.list_download_total_files_label.pack(side="left", padx=5)
        download_btn = ttk.Button(action_frame, text="선택 파일 다운로드", command=self.start_list_download_process)
        download_btn.pack(side="left", padx=5)

    def select_list_download_json_file(self):
        file_path = filedialog.askopenfilename(
            title="다운로드 목록 JSON 파일 선택",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
        )
        if file_path:
            self.list_download_json_path_var.set(file_path)
            self.list_download_total_files_var.set("Total files to download: 0") # Reset before loading
            self.list_download_files_to_download = [] # Reset before loading
            self.load_and_count_list_download_files() # Automatically load and count

    def load_and_count_list_download_files(self):
        json_file_path = self.list_download_json_path_var.get()
        if not json_file_path:
            messagebox.showerror("Error", "JSON 파일을 선택해주세요.")
            return

        project_id = self.list_download_project_id_entry.get().strip()
        if not project_id:
            messagebox.showerror("Error", "Project ID를 입력해주세요.")
            # Clear previous count if project ID is missing now
            self.list_download_total_files_var.set("Total files to download: 0")
            self.list_download_files_to_download = []
            return
        s3_base_path = f"project{project_id}/storage"

        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                # import orjson; file_data_from_json = orjson.loads(f.read())  # (선택) 매우 큰 파일일 때
                file_data_from_json = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"JSON 파일 읽기 실패: {e}")
            self.list_download_total_files_var.set("Total files to download: 0")
            self.list_download_files_to_download = []
            return

        if not isinstance(file_data_from_json, dict):
            messagebox.showerror("Error", "JSON 파일은 폴더 이름을 키로, 페이지 번호 리스트를 값으로 하는 딕셔너리 형태여야 합니다.")
            self.list_download_total_files_var.set("Total files to download: 0")
            self.list_download_files_to_download = []
            return

        # set을 사용하여 중복 없이 빠르게 모음
        files_to_download_set = set()
        download_option = self.list_download_option_var.get()
        
        for folder_name, page_list in file_data_from_json.items():
            current_folder_s3_prefix = f"{s3_base_path}/{folder_name}/"
            if not page_list:
                continue
            else:
                for page_number_str in page_list:
                    s3_file_base_name = f"{folder_name}_{page_number_str}"
                    if download_option == "json" or download_option == "both":
                        s3_key = f"{current_folder_s3_prefix}{s3_file_base_name}.json"
                        files_to_download_set.add(s3_key)
                    if download_option == "png" or download_option == "both":
                        s3_key = f"{current_folder_s3_prefix}{s3_file_base_name}.png"
                        files_to_download_set.add(s3_key)

        # set에서 list로 변환
        self.list_download_files_to_download = list(files_to_download_set)
        actual_files_to_download_count = len(self.list_download_files_to_download)

        self.list_download_total_files_var.set(f"Total files to download: {actual_files_to_download_count}")

        # messagebox 호출 최소화
        if actual_files_to_download_count == 0:
            messagebox.showinfo("결과", "JSON 파일 내용 및 선택된 옵션에 따라 다운로드할 파일이 없습니다.")
        else:
            messagebox.showinfo("파일 목록 계산 완료", f"JSON 목록 기준, 다운로드할 파일 {actual_files_to_download_count}개 (S3 존재 여부 미확인).")

    def browse_list_download_specific_dir(self):
        path = filedialog.askdirectory(initialdir=self.list_download_specific_path_var.get())
        if path:
            self.list_download_specific_path_var.set(path)

    def start_list_download_process(self):
        if not self.list_download_files_to_download:
            messagebox.showinfo("다운로드 목록 없음", "먼저 파일 목록을 불러오고 개수를 확인해주세요.")
            return

        download_dir_path = self.list_download_specific_path_var.get()
        if not download_dir_path or not os.path.isdir(download_dir_path):
            messagebox.showerror("잘못된 경로", "유효한 다운로드 폴더를 선택해주세요.")
            return
        # self.download_dir = download_dir_path # No longer update the global default here

        aws_access_key = self.list_download_aws_access_key_entry.get().strip()
        aws_secret_key = self.list_download_aws_secret_key_entry.get().strip()
        aws_region = self.list_download_aws_region_entry.get().strip()
        bucket_name = self.list_download_bucket_name_entry.get().strip()
        project_id = self.list_download_project_id_entry.get().strip()

        if not all([aws_access_key, aws_secret_key, aws_region, bucket_name]):
            messagebox.showerror("Error", "AWS 설정값을 모두 입력해주세요.")
            return

        # 현재 입력값을 설정 파일에 저장
        self._save_section("list_download", aws_access_key, aws_secret_key, aws_region, bucket_name, project_id)

        try:
            s3_client_dl = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region,
            )
        except Exception as e:
            messagebox.showerror("S3 Connection Error", f"S3 연결 실패: {e}")
            return

        self.progress_window = tk.Toplevel(self.master)
        self.progress_window.title("리스트 다운로드 진행")
        self.progress_window.geometry("400x100")
        ttk.Label(self.progress_window, text="다운로드 중...").pack(pady=10)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.progress_window, maximum=len(self.list_download_files_to_download), variable=self.progress_var, length=350)
        self.progress_bar.pack(pady=10)
        self.progress_label = ttk.Label(self.progress_window, text=f"0 / {len(self.list_download_files_to_download)}")
        self.progress_label.pack()

        threading.Thread(target=self._list_download_worker, args=(s3_client_dl, bucket_name, self.list_download_files_to_download, download_dir_path), daemon=True).start()

    def _list_download_worker(self, s3_client, bucket_name, files_to_download, download_dir):
        downloaded_count = 0
        
        # s3_base_path for stripping prefix to create local folder structure
        project_id = self.list_download_project_id_entry.get().strip() # Get project_id for base_path
        s3_base_path_prefix_to_strip = f"project{project_id}/storage/"


        def download_one_listed_file(args):
            s3_key, local_full_path = args
            os.makedirs(os.path.dirname(local_full_path), exist_ok=True)
            try:
                s3_client.download_file(bucket_name, s3_key, local_full_path)
                return True
            except Exception as e:
                print(f"리스트 다운로드 실패 {s3_key}: {e}")
                return False

        file_args_list = []
        for s3_key in files_to_download:
            # Create local path correctly, maintaining folder structure from s3_base_path
            if s3_key.startswith(s3_base_path_prefix_to_strip):
                 relative_path = s3_key[len(s3_base_path_prefix_to_strip):]
            else: # Should not happen if JSON list is correct, but as a fallback
                relative_path = os.path.basename(s3_key) # Fallback to just filename if prefix doesn't match
            
            local_file_path = os.path.join(download_dir, relative_path)
            file_args_list.append((s3_key, local_file_path))

        max_workers = min(8, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(download_one_listed_file, arg_pair) for arg_pair in file_args_list]
            for i, future in enumerate(as_completed(futures), 1):
                if future.result():
                    downloaded_count +=1
                self.master.after(0, self._update_progress, i, len(files_to_download))
        
        self.master.after(0, self._download_complete, downloaded_count)


    def connect_to_s3(self):
        aws_access_key = self.aws_access_key_entry.get().strip()
        aws_secret_key = self.aws_secret_key_entry.get().strip()
        aws_region = self.aws_region_entry.get().strip()

        if not all([aws_access_key, aws_secret_key, aws_region]):
            messagebox.showerror("Error", "Please fill in all AWS configuration fields.")
            return False

        try:
            self.s3 = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region,
            )
            return True
        except Exception as e:
            messagebox.showerror("S3 Connection Error", f"Failed to connect to S3: {e}")
            self.s3 = None
            return False

    def connect_and_show_folders(self):
        if self.connect_to_s3():
            self.bucket_name = self.bucket_name_entry.get().strip()
            self.project_id = self.project_id_entry.get().strip()
            self.s3_base_path = f"project{self.project_id}/storage"
            # 현재 입력값을 설정 파일에 저장
            self._save_section(
                self._current_section,
                self.aws_access_key_entry.get().strip(),
                self.aws_secret_key_entry.get().strip(),
                self.aws_region_entry.get().strip(),
                self.bucket_name,
                self.project_id,
            )
            self.show_s3_folders_window()

    def show_s3_folders_window(self):
        if not self.s3:
            messagebox.showerror("Error", "S3 is not connected.")
            return

        self.folders_window = tk.Toplevel(self.master)
        self.folders_window.title(f"S3 Folders in {self.bucket_name}/{self.s3_base_path}")
        self.folders_window.geometry("800x600")

        main_frame = ttk.Frame(self.folders_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 검색 프레임 추가
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(search_frame, text="폴더명 검색:").pack(side="left")
        self.s3_folder_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.s3_folder_search_var, width=30)
        search_entry.pack(side="left", padx=5)
        ttk.Button(search_frame, text="검색", command=self.filter_s3_folders).pack(side="left")
        ttk.Button(search_frame, text="초기화", command=self.reset_s3_folder_filter).pack(side="left", padx=2)

        # Treeview for displaying folders (다중 선택)
        self.folder_tree = ttk.Treeview(main_frame, columns=("Folder Name", "Item Count"), show="headings", selectmode="extended")
        self.folder_tree.heading("Folder Name", text="Folder Name")
        self.folder_tree.heading("Item Count", text="Item Count")
        self.folder_tree.column("Folder Name", width=500)
        self.folder_tree.column("Item Count", width=100)
        self.folder_tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.folder_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.folder_tree.configure(yscrollcommand=scrollbar.set)

        # 다운로드 옵션 및 버튼/라벨
        bottom_frame = ttk.Frame(self.folders_window)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        # 다운로드 옵션 라디오버튼
        self.download_option = tk.StringVar(value="both")
        ttk.Label(bottom_frame, text="Download:").pack(side="left", padx=(0, 5))
        ttk.Radiobutton(bottom_frame, text="JSON만", variable=self.download_option, value="json").pack(side="left")
        ttk.Radiobutton(bottom_frame, text="PNG만", variable=self.download_option, value="png").pack(side="left")
        ttk.Radiobutton(bottom_frame, text="JSON+PNG", variable=self.download_option, value="both").pack(side="left")

        self.download_button = ttk.Button(bottom_frame, text="Download Selected Folders", command=self.download_selected_folders)
        self.download_button.pack(side="left", padx=(10, 0))
        self.total_count_label = ttk.Label(bottom_frame, text="Total files to download: 0")
        self.total_count_label.pack(side="left", padx=20)

        # 폴더 선택 이벤트 바인딩
        self.folder_tree.bind("<<TreeviewSelect>>", self.update_total_count_label)

        self.load_s3_folders()
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(self.folders_window, text="뒤로가기", command=self.folders_window.destroy)
        back_btn.pack(side="bottom", pady=10)

        # CSV 내보내기 버튼 추가
        export_csv_btn = ttk.Button(main_frame, text="CSV로 내보내기", command=self.export_s3_folder_list_csv)
        export_csv_btn.pack(side="bottom", pady=5)

        # Download path selection UI
        path_frame = ttk.Frame(self.folders_window)
        path_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(path_frame, text="다운로드 폴더:").pack(side="left")
        path_entry = ttk.Entry(path_frame, textvariable=self.download_path_var, width=60)
        path_entry.pack(side="left", padx=5)
        browse_btn = ttk.Button(path_frame, text="폴더 선택", command=self.browse_download_dir)
        browse_btn.pack(side="left", padx=2)

    def export_s3_folder_list_csv(self):
        # 폴더명, 파일개수(csv) 내보내기
        import csv
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], title="폴더 목록 CSV로 저장")
        if not file_path:
            return
        rows = []
        for iid in self.folder_tree.get_children():
            values = self.folder_tree.item(iid, 'values')
            if values:
                folder = values[0]
                item_count = values[1]
                rows.append([folder, item_count])
        with open(file_path, "w", newline='', encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Folder Name", "Item Count"])
            writer.writerows(rows)

    def browse_download_dir(self):
        path = filedialog.askdirectory(initialdir=self.download_path_var.get())
        if path:
            self.download_path_var.set(path)

    def load_s3_folders(self):
        for i in self.folder_tree.get_children():
            self.folder_tree.delete(i)

        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            prefix = self.s3_base_path + '/'
            folders = []
            self.folder_file_counts = {}

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, Delimiter='/'):
                for cp in page.get('CommonPrefixes', []):
                    folder = cp['Prefix'][len(prefix):].strip('/')
                    if folder:
                        folders.append(folder)

            self._all_s3_folders = sorted(folders)  # 전체 폴더 목록 저장
            for folder in self._all_s3_folders:
                self.folder_tree.insert("", "end", values=(folder, ""))

            threading.Thread(target=self._count_files_async, args=(self._all_s3_folders,), daemon=True).start()

        except Exception as e:
            messagebox.showerror("S3 Folder Listing Error", f"Failed to list S3 folders: {e}")

    def filter_s3_folders(self):
        # 검색어로 폴더 필터링
        keyword = self.s3_folder_search_var.get().strip()
        filtered = [f for f in getattr(self, "_all_s3_folders", []) if keyword in f]
        for i in self.folder_tree.get_children():
            self.folder_tree.delete(i)
        for folder in filtered:
            # 기존 파일 개수 정보가 있으면 표시
            counts = self.folder_file_counts.get(folder, None)
            if counts:
                self.folder_tree.insert("", "end", values=(f"{folder} ({counts['png']})", f"JSON:{counts['json']} / PNG:{counts['png']}"))
            else:
                self.folder_tree.insert("", "end", values=(folder, ""))

    def reset_s3_folder_filter(self):
        self.s3_folder_search_var.set("")
        self.filter_s3_folders()

    def _count_files_async(self, folders):
        paginator = self.s3.get_paginator('list_objects_v2')
        prefix = self.s3_base_path + '/'
        for folder in folders:
            folder_prefix = prefix + folder + '/'
            json_count = 0
            png_count = 0
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=folder_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('/'):
                        continue
                    if key.lower().endswith('.json'):
                        json_count += 1
                    elif key.lower().endswith('.png'):
                        png_count += 1
            self.folder_file_counts[folder] = {"json": json_count, "png": png_count}
            self.master.after(0, self._update_folder_count, folder, json_count, png_count)

    def _update_folder_count(self, folder, json_count, png_count):
        for iid in self.folder_tree.get_children():
            values = self.folder_tree.item(iid, 'values')
            if values and values[0] == folder:
                # 폴더명 옆에는 JSON 개수만, ITEM COUNT에는 JSON/PNG 개수 모두 표시
                self.folder_tree.item(iid, values=(f"{folder} ({png_count})", f"JSON:{json_count} / PNG:{png_count}"))
                break

    def update_total_count_label(self, event=None):
        selected_iids = self.folder_tree.selection()
        total_files = 0
        option = self.download_option.get() if hasattr(self, 'download_option') else "both"
        for iid in selected_iids:
            values = self.folder_tree.item(iid, 'values')
            if values and values[0]:
                folder = values[0].split(' (')[0]
                counts = self.folder_file_counts.get(folder, {"json": 0, "png": 0})
                if option == "json":
                    total_files += counts["json"]
                elif option == "png":
                    total_files += counts["png"]
                else:
                    total_files += counts["json"] + counts["png"]
        self.total_count_label.config(text=f"Total files to download: {total_files}")

    def download_selected_folders(self):
        selected_iids = self.folder_tree.selection()
        selected_folders = []
        for iid in selected_iids:
            values = self.folder_tree.item(iid, 'values')
            if values and values[0]:
                folder = values[0].split(' (')[0]
                selected_folders.append(folder)

        if not selected_folders:
            messagebox.showinfo("No Selection", "Please select at least one folder to download.")
            return

        download_dir = self.download_path_var.get()
        if not os.path.isdir(download_dir):
            messagebox.showerror("Invalid Path", "Please select a valid download directory.")
            return

        option = self.download_option.get() if hasattr(self, 'download_option') else "both"
        total_files = self._count_files_for_download(selected_folders, option)

        self.progress_window = tk.Toplevel(self.master)
        self.progress_window.title("Download Progress")
        self.progress_window.geometry("400x100")
        ttk.Label(self.progress_window, text="Downloading...").pack(pady=10)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.progress_window, maximum=total_files, variable=self.progress_var, length=350)
        self.progress_bar.pack(pady=10)
        self.progress_label = ttk.Label(self.progress_window, text="0 / %d" % total_files)
        self.progress_label.pack()

        threading.Thread(target=self._download_folders, args=(selected_folders, download_dir, total_files, option), daemon=True).start()

    def _count_files_for_download(self, folders, option):
        paginator = self.s3.get_paginator('list_objects_v2')
        prefix = self.s3_base_path + '/'
        total = 0
        for folder in folders:
            folder_prefix = prefix + folder + '/'
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=folder_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('/'):
                        continue
                    if option == "json" and key.lower().endswith('.json'):
                        total += 1
                    elif option == "png" and key.lower().endswith('.png'):
                        total += 1
                    elif option == "both" and (key.lower().endswith('.json') or key.lower().endswith('.png')):
                        total += 1
        return total

    def _download_folders(self, folders, download_dir, total_files, option):
        # 멀티쓰레딩 다운로드
        aws_access_key = self.aws_access_key_entry.get().strip()
        aws_secret_key = self.aws_secret_key_entry.get().strip()
        aws_region = self.aws_region_entry.get().strip()
        bucket = self.bucket_name
        prefix = self.s3_base_path + '/'
        file_list = []
        for folder in folders:
            folder_prefix = prefix + folder + '/'
            paginator = self.s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=folder_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('/'):
                        continue
                    if option == "json" and not key.lower().endswith('.json'):
                        continue
                    if option == "png" and not key.lower().endswith('.png'):
                        continue
                    if option == "both" and not (key.lower().endswith('.json') or key.lower().endswith('.png')):
                        continue
                    rel_path = key[len(prefix):]
                    local_path = os.path.join(download_dir, rel_path)
                    file_list.append((bucket, key, local_path))

        def download_one(args):
            bucket, key, local_path = args
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                self.s3.download_file(bucket, key, local_path)
                return True
            except Exception as e:
                print(f"Failed to download {key}: {e}")
                return False

        total_downloaded = 0
        max_workers = min(8, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(download_one, args) for args in file_list]
            for i, future in enumerate(as_completed(futures), 1):
                # 진행률 업데이트
                self.master.after(0, self._update_progress, i, total_files)
        self.master.after(0, self._download_complete, len(file_list))

    def _update_progress(self, downloaded, total):
        if hasattr(self, 'progress_var'):
            self.progress_var.set(downloaded)
        if hasattr(self, 'progress_label'):
            self.progress_label.config(text=f"{downloaded} / {total}")

    def _download_complete(self, total_downloaded):
        if hasattr(self, 'progress_window'):
            self.progress_window.destroy()
        messagebox.showinfo("Download Complete", f"Downloaded {total_downloaded} files.")

    def show_local_folder_list(self):
        # 로컬 폴더 선택
        folder_path = filedialog.askdirectory(title="업로드할 폴더 선택")
        if not folder_path:
            return

        # 하위 폴더 목록 및 파일 개수 집계
        folder_infos = []
        for entry in os.scandir(folder_path):
            if entry.is_dir():
                file_count = sum([len(files) for _, _, files in os.walk(entry.path)])
                folder_infos.append((entry.name, file_count, entry.path))

        # 새 창에 폴더명과 파일 개수 표시
        info_win = tk.Toplevel(self.master)
        info_win.title("로컬 폴더 목록 및 파일 개수")
        info_win.geometry("600x500")

        # 검색 프레임 추가
        search_frame = ttk.Frame(info_win)
        search_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(search_frame, text="폴더명 검색:").pack(side="left")
        local_folder_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=local_folder_search_var, width=30)
        search_entry.pack(side="left", padx=5)
        def filter_local_folders():
            keyword = local_folder_search_var.get().strip()
            tree.delete(*tree.get_children())
            for name, count, _ in folder_infos:
                if keyword in name:
                    tree.insert("", "end", values=(name, count))
            update_upload_count()
        ttk.Button(search_frame, text="검색", command=filter_local_folders).pack(side="left")
        ttk.Button(search_frame, text="초기화", command=lambda: (local_folder_search_var.set(""), filter_local_folders())).pack(side="left", padx=2)

        tree = ttk.Treeview(info_win, columns=("Folder Name", "File Count"), show="headings", selectmode="extended")
        tree.heading("Folder Name", text="Folder Name")
        tree.heading("File Count", text="File Count")
        tree.column("Folder Name", width=350)
        tree.column("File Count", width=100)
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        for name, count, _ in folder_infos:
            tree.insert("", "end", values=(name, count))

        # 업로드 파일 개수 라벨
        file_count_label = ttk.Label(info_win, text="Total files to upload: 0")
        file_count_label.pack(pady=5)

        def update_upload_count(event=None):
            selected = tree.selection()
            total_files = 0
            selected_folders = []
            for iid in selected:
                values = tree.item(iid, 'values')
                if values:
                    for name, count, path in folder_infos:
                        if name == values[0]:
                            selected_folders.append((name, path, count))
            if not selected_folders:
                selected_folders = [(name, path, count) for name, count, path in folder_infos]
            # 폴더별 파일 개수의 합만 집계 (폴더 전체 업로드)
            total_files = sum(count for _, _, count in selected_folders)
            file_count_label.config(text=f"Total files to upload: {total_files}")

        tree.bind("<<TreeviewSelect>>", update_upload_count)
        update_upload_count()  # 초기 표시

        # 업로드 버튼
        def on_upload():
            selected = tree.selection()
            selected_folders = []
            for iid in selected:
                values = tree.item(iid, 'values')
                if values:
                    for name, count, path in folder_infos:
                        if name == values[0]:
                            selected_folders.append((name, path, count))
            if not selected_folders:
                selected_folders = [(name, path, count) for name, count, path in folder_infos]

            # 업로드 대상 파일 개수 집계 (폴더별 파일 개수의 합)
            upload_count = sum(count for _, _, count in selected_folders)

            # 업로드 경로 확인 (프로젝트 버킷/프로젝트id/storage/)
            bucket = self.bucket_name_entry.get().strip()
            project_id = self.project_id_entry.get().strip()
            s3_base_path = f"project{project_id}/storage"
            dest_info = f"Bucket: {bucket}\nPrefix: {s3_base_path}/"
            if not messagebox.askyesno("업로드 확인", f"총 {upload_count}개 파일이 아래 경로로 업로드됩니다.\n\n{dest_info}\n\n업로드 하시겠습니까?"):
                return

            # 업로드 진행 바 창
            progress_win = tk.Toplevel(info_win)
            progress_win.title("Upload Progress")
            progress_win.geometry("400x100")
            ttk.Label(progress_win, text="Uploading...").pack(pady=10)
            progress_var = tk.DoubleVar(value=0)
            progress_bar = ttk.Progressbar(progress_win, maximum=upload_count, variable=progress_var, length=350)
            progress_bar.pack(pady=10)
            progress_label = ttk.Label(progress_win, text=f"0 / {upload_count}")
            progress_label.pack()

            aws_access_key = self.aws_access_key_entry.get().strip()
            aws_secret_key = self.aws_secret_key_entry.get().strip()
            aws_region = self.aws_region_entry.get().strip()
            bucket = self.bucket_name_entry.get().strip()
            project_id = self.project_id_entry.get().strip()
            s3_base_path = f"project{project_id}/storage"

            # 현재 입력값을 설정 파일에 저장
            self._save_section("upload", aws_access_key, aws_secret_key, aws_region, bucket, project_id)

            # 업로드할 파일 목록 생성
            file_list = []
            for name, path, _ in selected_folders:
                for root, _, files in os.walk(path):
                    for f in files:
                        local_file = os.path.join(root, f)
                        rel_path = os.path.relpath(local_file, path)
                        s3_key = f"{s3_base_path}/{name}/{rel_path.replace(os.sep, '/')}"
                        file_list.append((local_file, bucket, s3_key))

            def upload_one(args):
                local_file, bucket, s3_key = args
                try:
                    self.s3.upload_file(local_file, bucket, s3_key)
                    return True
                except Exception as e:
                    print(f"Failed to upload {local_file}: {e}")
                    return False

            def upload_thread():
                uploaded = 0
                if not self.s3:
                    if not self.connect_to_s3():
                        progress_win.destroy()
                        return
                max_workers = min(8, os.cpu_count() or 4)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(upload_one, args) for args in file_list]
                    for i, future in enumerate(as_completed(futures), 1):
                        progress_win.after(0, progress_var.set, i)
                        progress_win.after(0, progress_label.config, {"text": f"{i} / {upload_count}"})
                progress_win.after(0, progress_win.destroy)
                messagebox.showinfo("Upload Complete", f"Uploaded {len(file_list)} files.")

            threading.Thread(target=upload_thread, daemon=True).start()

        upload_btn = ttk.Button(info_win, text="업로드", command=on_upload)
        upload_btn.pack(pady=10)
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(info_win, text="뒤로가기", command=info_win.destroy)
        back_btn.pack(pady=5)

        # CSV 내보내기 버튼 추가
        def export_local_folder_list_csv():
            import csv
            from tkinter import filedialog
            file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], title="폴더 목록 CSV로 저장")
            if not file_path:
                return
            rows = []
            for iid in tree.get_children():
                values = tree.item(iid, 'values')
                if values:
                    rows.append([values[0], values[1]])
            with open(file_path, "w", newline='', encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Folder Name", "File Count"])
                writer.writerows(rows)
        export_csv_btn = ttk.Button(info_win, text="CSV로 내보내기", command=export_local_folder_list_csv)
        export_csv_btn.pack(pady=5)

    def show_reject_process(self):
        # 1. AWS 설정 입력 UI
        self.main_frame.pack_forget()
        self.reject_frame = ttk.LabelFrame(self.master, text="도서 반려 처리 - AWS Configuration")
        self.reject_frame.pack(padx=20, pady=20, fill="x")
        self.create_reject_config_widgets(self.reject_frame)
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(self.reject_frame, text="뒤로가기", command=self.back_to_main)
        back_btn.grid(row=9, column=0, columnspan=2, pady=10)

    def create_reject_config_widgets(self, parent):
        # 저장된 설정 불러오기
        saved = self._get_section("reject")

        # AWS Access Key
        ttk.Label(parent, text="AWS Access Key:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.reject_aws_access_key_entry = ttk.Entry(parent, width=50)
        self.reject_aws_access_key_entry.insert(0, saved.get("aws_access_key", ""))
        self.reject_aws_access_key_entry.grid(row=0, column=1, padx=5, pady=5)

        # AWS Secret Key
        ttk.Label(parent, text="AWS Secret Key:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.reject_aws_secret_key_entry = ttk.Entry(parent, width=50, show="*")
        self.reject_aws_secret_key_entry.insert(0, saved.get("aws_secret_key", ""))
        self.reject_aws_secret_key_entry.grid(row=1, column=1, padx=5, pady=5)

        # AWS Region
        ttk.Label(parent, text="AWS Region:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.reject_aws_region_entry = ttk.Entry(parent, width=50)
        self.reject_aws_region_entry.insert(0, saved.get("aws_region", "ap-northeast-2"))
        self.reject_aws_region_entry.grid(row=2, column=1, padx=5, pady=5)

        # Bucket Name
        ttk.Label(parent, text="Bucket Name:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.reject_bucket_name_entry = ttk.Entry(parent, width=50)
        self.reject_bucket_name_entry.insert(0, saved.get("bucket_name", "project-24-pd-021"))
        self.reject_bucket_name_entry.grid(row=3, column=1, padx=5, pady=5)

        # Project ID
        ttk.Label(parent, text="Project ID:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.reject_project_id_entry = ttk.Entry(parent, width=50)
        self.reject_project_id_entry.insert(0, saved.get("project_id", "1760"))
        self.reject_project_id_entry.grid(row=4, column=1, padx=5, pady=5)

        # source_suffix, target_suffix, all_reject 입력
        ttk.Label(parent, text="완료된 폴더 뒤 3자리:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.source_suffix_entry = ttk.Entry(parent, width=20)
        self.source_suffix_entry.insert(0, "_out")
        self.source_suffix_entry.grid(row=5, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(parent, text="반려 폴더 뒤 3자리(필요 시 설정):").grid(row=6, column=0, sticky="w", padx=5, pady=5)
        self.target_suffix_entry = ttk.Entry(parent, width=20)
        self.target_suffix_entry.insert(0, "")
        self.target_suffix_entry.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        # 반려 옵션 체크박스 추가
        self.all_reject_var = tk.BooleanVar(value=False)
        self.f_tag_reject_var = tk.BooleanVar(value=False)
        self.is_problem_reject_var = tk.BooleanVar(value=False)
        ttk.Label(parent, text="반려 옵션:").grid(row=7, column=0, sticky="w", padx=5, pady=5)
        option_frame = ttk.Frame(parent)
        option_frame.grid(row=7, column=1, sticky="w", padx=5, pady=5)
        self.all_reject_check = ttk.Checkbutton(option_frame, text="모두 이동", variable=self.all_reject_var)
        self.all_reject_check.pack(side="left", padx=2)
        self.f_tag_reject_check = ttk.Checkbutton(option_frame, text="f태그 불일치", variable=self.f_tag_reject_var)
        self.f_tag_reject_check.pack(side="left", padx=2)
        self.is_problem_reject_check = ttk.Checkbutton(option_frame, text="확인필요(is_problem)", variable=self.is_problem_reject_var)
        self.is_problem_reject_check.pack(side="left", padx=2)

        # 폴더 목록 불러오기 버튼
        self.load_folders_btn = ttk.Button(parent, text="폴더 목록 불러오기", command=self.load_reject_folder_list)
        self.load_folders_btn.grid(row=8, column=0, columnspan=2, pady=10)

    def load_reject_folder_list(self):
        # S3 접속
        aws_access_key = self.reject_aws_access_key_entry.get().strip()
        aws_secret_key = self.reject_aws_secret_key_entry.get().strip()
        aws_region = self.reject_aws_region_entry.get().strip()
        bucket = self.reject_bucket_name_entry.get().strip()
        project_id = self.reject_project_id_entry.get().strip()
        s3_base_path = f"project{project_id}/storage"

        # 현재 입력값을 설정 파일에 저장
        self._save_section("reject", aws_access_key, aws_secret_key, aws_region, bucket, project_id)

        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region,
            )
        except Exception as e:
            messagebox.showerror("S3 Connection Error", f"Failed to connect to S3: {e}")
            return

        # S3 폴더 목록 가져오기
        folders = []
        try:
            paginator = s3.get_paginator('list_objects_v2')
            prefix = s3_base_path + '/'
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/'):
                for cp in page.get('CommonPrefixes', []):
                    folder = cp['Prefix'][len(prefix):].strip('/')
                    if folder:
                        folders.append(folder)
        except Exception as e:
            messagebox.showerror("S3 Folder Listing Error", f"Failed to list S3 folders: {e}")
            return

        # 폴더 선택 창
        folder_win = tk.Toplevel(self.master)
        folder_win.title("도서 반려 처리 - 폴더 선택")
        folder_win.geometry("600x500")

        # 검색 프레임 추가
        search_frame = ttk.Frame(folder_win)
        search_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(search_frame, text="폴더명 검색:").pack(side="left")
        reject_folder_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=reject_folder_search_var, width=30)
        search_entry.pack(side="left", padx=5)
        def filter_reject_folders():
            keyword = reject_folder_search_var.get().strip()
            tree.delete(*tree.get_children())
            for name in sorted(folders):
                if keyword in name:
                    tree.insert("", "end", values=(name,))
            update_selected_label()
        ttk.Button(search_frame, text="검색", command=filter_reject_folders).pack(side="left")
        ttk.Button(search_frame, text="초기화", command=lambda: (reject_folder_search_var.set(""), filter_reject_folders())).pack(side="left", padx=2)

        tree = ttk.Treeview(folder_win, columns=("Folder Name",), show="headings", selectmode="extended")
        tree.heading("Folder Name", text="Folder Name")
        tree.column("Folder Name", width=400)
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        for name in sorted(folders):
            tree.insert("", "end", values=(name,))

        # 선택 폴더 리스트 라벨
        selected_label = ttk.Label(folder_win, text="선택된 폴더: 0")
        selected_label.pack(pady=5)

        def update_selected_label(event=None):
            selected = tree.selection()
            selected_label.config(text=f"선택된 폴더: {len(selected)}")

        tree.bind("<<TreeviewSelect>>", update_selected_label)
        update_selected_label()

        # 실행 버튼
        def on_reject_execute():
            # 옵션 체크: 하나라도 체크되어야 함
            if not (self.all_reject_var.get() or self.f_tag_reject_var.get() or self.is_problem_reject_var.get()):
                messagebox.showwarning("옵션 미선택", "반려 옵션이 선택되지 않았습니다.")
                return
            selected = tree.selection()
            folder_list = []
            source_suffix = self.source_suffix_entry.get().strip()
            for iid in selected:
                values = tree.item(iid, 'values')
                if values:
                    folder_name = values[0]
                    # source_suffix로 끝나는지 판별
                    if not folder_name.endswith(source_suffix):
                        messagebox.showwarning("작업중이거나 반려 대상 폴더가 아님", f"'{folder_name}' 폴더는 작업중이거나 반려 대상 폴더가 아닙니다.\n완료된 폴더({source_suffix}로 끝나는 폴더)만 선택하세요.")
                        return
                    folder_list.append(folder_name)
            if not folder_list:
                messagebox.showinfo("No Selection", "폴더를 선택하세요.")
                return

            # 파라미터 수집
            params = {
                "aws_access_key": aws_access_key,
                "aws_secret_key": aws_secret_key,
                "aws_region": aws_region,
                "bucket": bucket,
                "project_id": project_id,
                "s3_base_path": s3_base_path,
                "source_suffix": source_suffix,
                "target_suffix": self.target_suffix_entry.get().strip(),
                "all_reject": self.all_reject_var.get(),
                "f_tag_reject": self.f_tag_reject_var.get(),
                "is_problem_reject": self.is_problem_reject_var.get(),
                "folder_list": folder_list,
            }
            folder_win.destroy()
            # 반려 로그 창 생성
            self.reject_log_window = tk.Toplevel(self.master)
            self.reject_log_window.title("반려 처리 진행")
            self.reject_log_window.geometry("700x400")
            # 진행바 및 상태 라벨 추가
            progress_frame = ttk.Frame(self.reject_log_window)
            progress_frame.pack(fill="x", padx=10, pady=5)
            self.reject_progress_var = tk.DoubleVar(value=0)
            self.reject_progress_bar = ttk.Progressbar(progress_frame, variable=self.reject_progress_var, maximum=1, length=500)
            self.reject_progress_bar.pack(side="left", fill="x", expand=True)
            self.reject_progress_label = ttk.Label(progress_frame, text="0 / 0")
            self.reject_progress_label.pack(side="left", padx=10)
            # 로그 텍스트
            self.reject_log_text = tk.Text(self.reject_log_window, state="disabled", wrap="none")
            self.reject_log_text.pack(fill="both", expand=True)
            self.run_reject_process(params)

        exec_btn = ttk.Button(folder_win, text="도서 반려 처리 실행", command=on_reject_execute)
        exec_btn.pack(pady=10)
        # 뒤로가기 버튼 추가
        back_btn = ttk.Button(folder_win, text="뒤로가기", command=folder_win.destroy)
        back_btn.pack(pady=5)

    def run_reject_process(self, params):
        # 실제 처리 함수 (비동기 실행)
        threading.Thread(target=self._reject_process_worker, args=(params,), daemon=True).start()

    def _reject_process_worker(self, params):
        import json
        import boto3
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # S3 클라이언트
        s3 = boto3.client(
            "s3",
            aws_access_key_id=params["aws_access_key"],
            aws_secret_access_key=params["aws_secret_key"],
            region_name=params["aws_region"],
        )
        bucket_name = params["bucket"]
        source_suffix = params["source_suffix"]
        target_suffix = params["target_suffix"]
        all_reject = params["all_reject"]
        f_tag_reject = params.get("f_tag_reject", False)
        is_problem_reject = params.get("is_problem_reject", False)
        s3_base_path = params["s3_base_path"]
        folder_list = params["folder_list"]

        def is_inline_formula(shape, text_bboxes):
            x1, y1 = shape["points"][0]
            x2, y2 = shape["points"][1]
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            for tx1, ty1, tx2, ty2 in text_bboxes:
                left = min(tx1, tx2)
                right = max(tx1, tx2)
                top = min(ty1, ty2)
                bottom = max(ty1, ty2)
                if left <= cx <= right and top <= cy <= bottom:
                    return True
            return False

        def list_all_objects(bucket_name, prefix):
            paginator = s3.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
            for page in page_iterator:
                for obj in page.get('Contents', []):
                    yield obj

        def log_message(msg):
            def append():
                if hasattr(self, 'reject_log_text'):
                    self.reject_log_text.config(state="normal")
                    self.reject_log_text.insert("end", msg + "\n")
                    self.reject_log_text.see("end")
                    self.reject_log_text.config(state="disabled")
            self.master.after(0, append)

        # 파일 개수 세기 및 작업 목록 생성
        file_tasks = []
        for folder in folder_list:
            base_folder = f"{s3_base_path}/{folder}"
            if not folder.endswith(source_suffix):
                continue
            dest_folder_name = folder[:-len(source_suffix)]
            source_folder = f"{base_folder}/"
            destination_folder = f"{s3_base_path}/{dest_folder_name}/"
            for obj in list_all_objects(bucket_name, source_folder):
                file_key = obj['Key']
                if file_key.endswith('.json'):
                    file_tasks.append((folder, dest_folder_name, source_folder, destination_folder, file_key))

        total_files = len(file_tasks)

        # 진행바 최대값 설정
        def set_progress_max():
            if hasattr(self, 'reject_progress_bar'):
                self.reject_progress_bar.config(maximum=total_files)
            if hasattr(self, 'reject_progress_label'):
                self.reject_progress_label.config(text=f"0 / {total_files}")
        self.master.after(0, set_progress_max)

        processed = 0

        def process_one(args):
            folder, dest_folder_name, source_folder, destination_folder, file_key = args
            file_name_without_ext = file_key.replace(source_folder, '').replace('.json', '')
            json_destination_key = f'{destination_folder}{file_name_without_ext}.json'
            png_source_key = f'{source_folder}{file_name_without_ext}.png'
            png_destination_key = f'{destination_folder}{file_name_without_ext}.png'
            try:
                response = s3.get_object(Bucket=bucket_name, Key=file_key)
                content = response['Body'].read().decode('utf-8')
                json_data = json.loads(content)
            except Exception as e:
                print(f"JSON 로드 실패: {file_key} ({e})")
                return False, folder, dest_folder_name, file_name_without_ext

            has_problem = False
            total_f_tag_count = 0
            total_formula_count = 0

            text_bboxes = [
                (shape['points'][0][0], shape['points'][0][1], shape['points'][1][0], shape['points'][1][1])
                for shape in json_data.get('shapes', [])
                if shape.get('label') in ['TEXT', 'FOOTNOTE', 'REFERENCE']
            ]

            for shape in json_data.get('shapes', []):
                if shape.get('is_problem') == True:
                    has_problem = True
                    shape['is_problem'] = True
                if shape.get('label') in ['TEXT', 'FOOTNOTE', 'REFERENCE']:
                    latex_text = shape.get('latex', "")
                    total_f_tag_count += latex_text.count("{f}")
                if shape.get('label') == 'FORMULA' and is_inline_formula(shape, text_bboxes):
                    total_formula_count += 1

            # 반려 조건: 옵션별로 적용
            reject_this = False
            if all_reject:
                reject_this = True
            if f_tag_reject and (total_f_tag_count != total_formula_count):
                reject_this = True
            if is_problem_reject and has_problem:
                reject_this = True

            if reject_this:
                try:
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=json_destination_key,
                        Body=json.dumps(json_data, ensure_ascii=False)
                    )
                except Exception as e:
                    print(f"JSON 업로드 실패: {json_destination_key} ({e})")

                try:
                    s3.copy_object(CopySource={'Bucket': bucket_name, 'Key': png_source_key},
                                   Bucket=bucket_name, Key=png_destination_key)
                    s3.delete_object(Bucket=bucket_name, Key=png_source_key)
                except Exception:
                    print(f"No PNG file found for {file_name_without_ext}.png")

                try:
                    s3.delete_object(Bucket=bucket_name, Key=file_key)
                except Exception as e:
                    print(f"원본 JSON 삭제 실패: {file_key} ({e})")
                return True, folder, dest_folder_name, file_name_without_ext
            else:
                return False, folder, dest_folder_name, file_name_without_ext

        max_workers = min(8, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_one, args) for args in file_tasks]
            for i, future in enumerate(as_completed(futures), 1):
                result, src_folder, dst_folder, file_name_without_ext = future.result()
                if result:
                    file_short = file_name_without_ext + ".json"
                    log_message(f"{src_folder}의 {file_short}를 {dst_folder}로 반려합니다. [{i}/{total_files}]")
                def update_progress(i=i):
                    if hasattr(self, 'reject_progress_var'):
                        self.reject_progress_var.set(i)
                    if hasattr(self, 'reject_progress_label'):
                        self.reject_progress_label.config(text=f"{i} / {total_files}")
                self.master.after(0, update_progress)

        self.master.after(0, lambda: messagebox.showinfo("도서 반려 처리 완료", "도서 반려 처리가 완료되었습니다."))

    def back_to_main(self):
        # 모든 서브 프레임 숨기고 메인 프레임만 보이게
        for widget in self.master.winfo_children():
            if widget != self.main_frame:
                widget.pack_forget()
                widget.destroy()
        self.main_frame.pack(expand=True)

if __name__ == "__main__":
    root = tk.Tk()
    app = S3DownloaderGUI(root)
    root.mainloop()
