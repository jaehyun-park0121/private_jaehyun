# 테이블 검수 뷰어

## 업데이트 일시 및 작성자

- huni-coder, 2026.05.07

## 폴더 구조

- `__init__.py`: misc tools 카드 진입점. 전용 가상환경 확인/설치 후 PyQt6 뷰어를 별도 프로세스로 실행합니다.
- `code/viewer.py`: PyQt6 뷰어 실행 진입점입니다.
- `code/requirements.txt`: `PyQt6`, `PyQt6-WebEngine`, `boto3`, `paramiko` 의존성을 정의합니다.
- `code/app/main_window.py`: 3패널 메인 창, 파일 로드, 필터, 저장 흐름을 조립합니다.
- `code/app/widgets/`: 입력 파일 트리, 이미지/BBOX 뷰, TABLE 검수 패널 UI를 제공합니다.
- `code/app/editor/`: 렌더링 편집, HTML/Markdown 원본 편집, 포맷 변환 로직을 담당합니다.
- `code/app/assets/`: WebView 편집 스크립트와 MathJax 자산을 보관합니다.
- `.gitignore`: 앱 전용 가상환경, 설치 로그, 캐시 파일 제외 규칙을 관리합니다.

## 제공하는 기능

- 로컬 폴더, AWS S3, SSH/SFTP 서버 파일시스템에서 이미지와 JSON을 열고 TABLE shape 중심으로 검수합니다.
- 좌측 패널에서 입력 소스와 파일 목록을 계속 확인할 수 있습니다.
- TABLE 검수 패널의 렌더링 편집 모드에서 렌더된 표 좌측 세로 편집 레일을 사용할 수 있습니다.
- 편집 레일의 항목은 마우스를 올리면 좌측으로 메뉴가 펼쳐지고, 커서가 편집 레일과 메뉴를 벗어나면 닫힙니다.
- 파일 목록은 파일명 중심으로 표시하고, TABLE 포함 파일만 보는 필터를 지원합니다. 폴더를 선택한 상태에서 `표만 보기`를 켜면 해당 폴더 안에서만 TABLE 포함 여부를 확인합니다.
- 이미지 BBOX, TABLE 목록, 렌더링 결과, HTML/Markdown 원본을 한 화면에서 함께 확인합니다.
- 이미지가 회전된 상태로 제공된 경우 이미지/BBOX 뷰어에서 90도 단위 회전을 지원합니다.
- SSH/SFTP 연결이 성공하면 Host, Port, User, PEM 경로, 원격 루트 경로를 사용자 설정에 저장해 다음 실행 때 다시 채웁니다. PEM Passphrase는 저장하지 않습니다.
- 렌더링 편집 도구에서 행/열/셀 편집, 잘라내기/복사/붙여넣기, 열 정합 보정, `Ctrl+Z` 5단계 실행취소를 지원합니다.
- 셀 선택 상태에서 화살표로 셀을 이동하고, 바로 입력하거나 `Enter`로 입력 모드에 진입합니다. 입력 중 `Enter`는 아래 셀, `Tab`은 다음 셀로 이동하며 줄바꿈은 `Ctrl+Enter`로 입력합니다.
- 표 포맷 자동 선택과 HTML/Markdown 원본 편집을 지원합니다.
- HTML/Markdown 소스 탭에서 `Pretty뷰`로 소스를 보기 좋게 정렬할 수 있습니다.
- 수정한 표 내용을 원본 로컬 JSON 파일, S3 JSON 키, SSH/SFTP 원격 JSON 경로로 다시 저장할 수 있습니다.

## 코드의 사용 방법

1. 메인 앱에서 실행합니다.
   - 루트에서 `run_app.bat` 또는 `python main.py`로 메인 앱을 실행합니다.
   - `기타 도구` 탭에서 `테이블 검수 뷰어` 카드를 클릭합니다.
   - 전용 가상환경이 없으면 `app/tabs/misc_tools/apps/table_viewer/code/.venv` 생성 및 패키지 설치 여부를 먼저 묻습니다.
2. 단독 실행이 필요하면 전용 가상환경에서 실행합니다.

```powershell
cd app/tabs/misc_tools/apps/table_viewer/code
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe viewer.py
```

## 그 외

- 실행 예시:

```powershell
cd app/tabs/misc_tools/apps/table_viewer/code
.venv\Scripts\python.exe viewer.py
```

- 주의 사항:
  - 메인 앱은 PyQt5, `table_viewer`는 PyQt6 + WebEngine 기반이라 같은 프로세스/가상환경에 섞지 않는 것을 기본 경로로 사용합니다.
  - S3 모드에서는 버킷/프리픽스 입력이 필요하고, `Access Key`와 `Secret Key`는 함께 입력해야 합니다.
  - SSH/SFTP 모드에서는 `Host`, `User`, `PEM 파일`, 원격 루트 경로 입력이 필요하며, 원격 루트는 서버 환경에 따라 절대 경로(`/data/project`) 또는 접속 후 기준 상대 경로(`storage/project`)를 사용할 수 있습니다. 파일 내용은 로컬 파일로 캐시하지 않고 메모리로 읽어 처리합니다.
  - 렌더링 편집 모드에서는 표 셀을 먼저 선택한 뒤 렌더된 표 좌측의 편집 레일에서 행/열/셀 작업을 실행합니다.
  - 입력 중 `Enter` 또는 `Tab`으로 이동한 뒤에는 다시 셀 선택 상태가 됩니다.
  - 렌더링 편집 결과는 현재 선택한 JSON에 반영되므로 저장 전 대상 파일 또는 S3 키를 확인하는 편이 좋습니다.
- 미검증 부분:
  - launcher 코드 기준으로 Windows `Scripts/python.exe`, `pythonw.exe` 흐름은 반영되어 있지만, macOS/Linux 직접 실행 흐름은 별도 정리되지 않았습니다.
  - GUI 상호작용은 수동 검수 위주이며, 자동 UI 테스트 문서는 아직 없습니다.
