"""색상 시스템과 도메인 상수."""

from PyQt6.QtGui import QColor

# ===== 색상 (메인 툴 라이트 테마 기준) =====
COLOR_BG = "#f2f4f7"              # 앱 배경
COLOR_PANEL = "#ffffff"           # 패널 배경
COLOR_PANEL_MUTED = "#f8fafc"     # 입력/테이블 헤더 배경
COLOR_BORDER = "#d8dee8"          # 일반 테두리
COLOR_BORDER_LIGHT = "#edf1f7"    # 테이블 gridline
COLOR_BORDER_STRONG = "#94a3b8"   # 강조 테두리 (표 선)
COLOR_PRIMARY = "#2563eb"         # 강조 (파랑)
COLOR_PRIMARY_HOVER = "#1d4ed8"
COLOR_TEXT = "#0f172a"            # 제목/강조 본문
COLOR_BODY_TEXT = "#334155"       # 본문
COLOR_SUBTEXT = "#64748b"         # 보조 텍스트
COLOR_DANGER = "#dc2626"
COLOR_SELECT = "#ea580c"          # BBOX 선택 강조 (오렌지)
COLOR_WARN = "#b45309"            # 정합성 경고
COLOR_OK = "#047857"              # 정합성 정상
COLOR_TH_BG = "#f8fafc"           # 표 헤더 배경

# ===== 라벨별 BBOX 색상 =====
LABEL_COLORS = {
    "TABLE": QColor(59, 130, 246, 64),
    "TEXT": QColor(34, 197, 94, 64),
    "CAPTION": QColor(234, 179, 8, 64),
}
LABEL_BORDERS = {
    "TABLE": QColor(59, 130, 246),
    "TEXT": QColor(34, 197, 94),
    "CAPTION": QColor(234, 179, 8),
}
LABELS = ("TABLE", "TEXT", "CAPTION")

# ===== 파일 입력 =====
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}

# ===== AWS S3 =====
DEFAULT_AWS_REGION = "ap-northeast-2"
S3_PATH_PLACEHOLDER = "s3://bucket/prefix"

# ===== SSH / SFTP =====
DEFAULT_SSH_PORT = "22"
SSH_REMOTE_PATH_PLACEHOLDER = "/data/project 또는 storage/project"
