"""대시보드 Flask 서버.

엑셀 또는 구글 스프레드시트 데이터를 읽어
웹 대시보드로 제공하는 메인 애플리케이션.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config import DashboardConfig
from data_loader import build_dashboard_data

# ── 일정 데이터 파일 경로 ─────────────────────────────────
import json
from pathlib import Path

_SCHEDULE_FILE = Path(__file__).parent / "schedule.json"


def _load_schedule() -> list[dict]:
    """일정 데이터를 JSON 파일에서 로드한다."""
    if _SCHEDULE_FILE.exists():
        with open(_SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_schedule(events: list[dict]) -> None:
    """일정 데이터를 JSON 파일에 저장한다."""
    with open(_SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def _load_data(config: DashboardConfig) -> dict:
    """설정된 데이터 소스에서 대시보드 데이터를 로드한다."""
    if config.data_source == "gsheet":
        from gsheet_loader import build_dashboard_data_from_gsheet
        return build_dashboard_data_from_gsheet(config)
    return build_dashboard_data(config)


def create_app(config: DashboardConfig | None = None) -> Flask:
    """Flask 앱 팩토리."""
    if config is None:
        config = DashboardConfig()

    app = Flask(__name__)

    @app.route("/")
    def index() -> str:
        """대시보드 메인 페이지."""
        return render_template("index.html", auto_refresh_ms=config.auto_refresh_ms)

    @app.route("/api/data")
    def api_data() -> tuple:
        """대시보드 데이터 API."""
        try:
            data = _load_data(config)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify({"error": f"엑셀 파일을 찾을 수 없습니다: {config.excel_path}"}), 404
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    # ── 납품 일정 API ────────────────────────────────────
    @app.route("/api/schedule", methods=["GET"])
    def get_schedule():
        """등록된 납품 일정 목록을 반환한다."""
        return jsonify(_load_schedule())

    @app.route("/api/schedule", methods=["POST"])
    def add_schedule():
        """새 납품 일정을 추가한다."""
        event = request.get_json()
        if not event or not event.get("date") or not event.get("title"):
            return jsonify({"error": "date와 title은 필수입니다."}), 400

        events = _load_schedule()
        import uuid
        event["id"] = str(uuid.uuid4())[:8]
        events.append(event)
        _save_schedule(events)
        return jsonify(event), 201

    @app.route("/api/schedule/<event_id>", methods=["DELETE"])
    def delete_schedule(event_id: str):
        """납품 일정을 삭제한다."""
        events = _load_schedule()
        events = [e for e in events if e.get("id") != event_id]
        _save_schedule(events)
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    import sys
    import os
    import webbrowser
    from threading import Timer

    sys.stdout.reconfigure(encoding="utf-8")

    config = DashboardConfig()

    # 구글 스프레드시트 모드일 때 서버 기동 전 연결 테스트
    if config.data_source == "gsheet":
        print("\n[구글 스프레드시트 모드 연결 확인 중...]")
        try:
            from gsheet_loader import _build_gspread_client
            # Service Account 방식: 브라우저 인증 불필요
            client = _build_gspread_client(config.gsheet_credential_path)
            print("✔ Service Account 인증 확인 완료.")

            # 구글 시트 접근성도 미리 체크
            if config.gsheet_url:
                print("연동된 구글 스프레드시트 접근 테스트 중...")
                client.open_by_url(config.gsheet_url)
                print("✔ 스프레드시트 접근 확인 완료.")
            else:
                print("⚠ GSHEET_URL이 설정되지 않았습니다.")
        except Exception as e:
            import traceback
            print(f"\n❌ 구글 Sheets 연동 실패: {e}")
            traceback.print_exc()
            print("\n해결 방법:")
            print("1. Service Account 이메일을 구글 시트에 공유했는지 확인")
            print("   이메일: 838337608989-compute@developer.gserviceaccount.com")
            print("2. Google Sheets API가 활성화되어 있는지 확인")
            print("3. GSHEET_URL 환경변수가 설정되어 있는지 확인\n")
            sys.exit(1)

    app = create_app(config)
    source_label = (
        "구글 스프레드시트" if config.data_source == "gsheet"
        else f"엑셀 ({config.excel_path})"
    )
    print(f"\n  [대시보드] 서버 시작: http://localhost:{config.port}")
    print(f"  [소스]     {source_label}")
    print(f"  [갱신]     {config.auto_refresh_ms // 1000}초 간격\n")

    # 리로더(Reloader)로 인해 브라우저가 두 번 열리는 것을 방지
    if not config.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        def open_browser():
            webbrowser.open(f"http://localhost:{config.port}")
        Timer(1.2, open_browser).start()

    app.run(host=config.host, port=config.port, debug=config.debug)
