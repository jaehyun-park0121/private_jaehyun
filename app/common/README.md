# app/common

여러 탭과 앱에서 함께 쓰는 공통 코드를 모아두는 폴더입니다.

## 이 폴더에 두는 기준

- 두 개 이상의 탭에서 같은 UI 패턴을 반복할 때
- 설정, 상태 메시지, 라벨 로딩처럼 탭 공통 규칙이 있을 때
- 탭 전용 로직으로 보기 어려운 인프라 성격의 코드일 때

## 구성과 역할

- `config/`: `ConfigManager`, 병렬 처리 설정 계산 등 공통 설정 로직
- `io/`: 인코딩과 파일 입출력 보조 유틸
- `labels/`: `label/*.xlsx`를 읽는 공통 라벨 로더
- `aws_settings_dialog.py`: AWS/S3 설정 대화상자
- `panel_layout.py`: 3분할 패널 기본 너비 정의
- `shared_status_bar.py`: 상태 메시지와 진행률 형식 관리
- `top_bar.py`: 상단 프로젝트 정보 표시 UI

## 사용 원칙

- 실제 라벨 기준표 파일은 여기 두지 않고 루트 `label/`을 사용합니다.
- 탭에서 공통 상태 메시지를 보여줄 때는 `shared_status_bar.py` 형식을 우선 따릅니다.
- 3분할 레이아웃 기본값은 `panel_layout.py`를 기준으로 합니다.
- 두 개 이상의 탭에서 유사한 기능이 있더라도, 우선은 탭별 폴더 안에서 코드를 분리해 유지하는 편을 권장합니다.
- 기능이 비슷하다는 이유만으로 바로 `common/`으로 합치기보다, 탭별 영향 범위와 수정 독립성을 우선 고려합니다.

## 함께 볼 문서

- [config/README.md](../../config/README.md)
- [docs/README.md](../../docs/README.md)
- [label/README.md](../../label/README.md)
