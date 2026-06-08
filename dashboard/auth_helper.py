"""Google Sheets API Service Account 연결 테스트 스크립트.

Service Account 방식은 브라우저 인증이 필요 없습니다.
이 스크립트는 Service Account가 구글 시트에 접근 가능한지 테스트합니다.
"""
import sys
from pathlib import Path
from config import DashboardConfig

def run_auth():
    sys.stdout.reconfigure(encoding="utf-8")
    config = DashboardConfig()

    print("\n[구글 Sheets Service Account 연결 테스트]")
    print(f"- Service Account JSON: {config.gsheet_credential_path}")
    print(f"- 구글 시트 URL: {config.gsheet_url}\n")

    if not config.gsheet_credential_path.exists():
        print(f"❌ Service Account 파일을 찾을 수 없습니다: {config.gsheet_credential_path}")
        return

    try:
        import gspread
    except ImportError:
        print("❌ gspread 패키지가 설치되어 있지 않습니다. 'pip install gspread'를 먼저 실행하세요.")
        return

    try:
        # Service Account 방식: 브라우저 인증 불필요
        client = gspread.service_account(filename=str(config.gsheet_credential_path))
        print("✔ Service Account 인증 성공!")

        # Service Account 이메일 출력
        import json
        with open(config.gsheet_credential_path, encoding='utf-8') as f:
            sa_data = json.load(f)
            print(f"✔ Service Account 이메일: {sa_data['client_email']}")

        # 시트 접근 테스트
        if config.gsheet_url:
            print("\n구글 시트 접근 테스트 중...")
            spreadsheet = client.open_by_url(config.gsheet_url)
            print(f"✔ 성공: '{spreadsheet.title}' 시트에 접근 가능합니다!")
            print("\n🎉 모든 테스트 통과! 구글 시트 연동이 정상적으로 작동합니다.")
        else:
            print("\n⚠ GSHEET_URL이 설정되지 않아 시트 접근 테스트를 건너뜁니다.")
            print("환경변수 GSHEET_URL을 설정하거나 config.py에서 gsheet_url을 지정하세요.")
    except Exception as e:
        print(f"\n❌ 연결 실패: {e}")
        print("\n해결 방법:")
        print("1. Service Account 이메일을 구글 시트에 공유했는지 확인")
        print("   (공유 버튼 → 이메일 입력 → 뷰어 또는 편집자 권한 부여)")
        print("2. Google Sheets API가 프로젝트에 활성화되어 있는지 확인")
        print("   https://console.cloud.google.com/apis/library/sheets.googleapis.com")

if __name__ == "__main__":
    run_auth()
