# app/tabs

메인 창에서 사용하는 탭 코드를 모아두는 폴더입니다.

## 공통 구조

대부분의 탭은 아래 구성을 기본으로 사용합니다.

- `page.py`: 탭 상위 조립, splitter 구성, 이벤트 연결
- `panels/`: 좌/중/우 패널 UI
- `features/`: 실행 흐름, worker, 결과 가공, 캐시/스냅샷 처리
- `widgets/`: 탭 전용 보조 위젯
- `README.md`: 탭 문서 진입점

탭마다 예외 구조가 있을 수 있지만, 이유가 있으면 해당 탭 README에 남기는 편을 권장합니다.

## 현재 탭 목록

- 기타 도구(misc_tools): 카드형 보조 앱 모음
- 파싱 전 검사(pre_parse): 파싱 전 단계 결과 JSON/이미지 QC
- 원시 데이터 분석(raw_data_analysis): 원시 박스 데이터 집계, 미리보기, 업로드
- 텍스트 분석(text_analysis): 텍스트 기반 검색, 치환, 특수문자 검사

## 새 탭 구성 시 참고할 원칙

### 1. 기본 폴더 구성

새 탭은 우선 `page.py`, `README.md`, 필요 시 `panels/`, `features/`, `widgets/`를 갖는 구조로 시작하는 편이 좋습니다.

### 2. 패널 구성

- 3분할 구조라면 기본 splitter 크기는 390 / 780 / 430을 우선 사용합니다.
- 왼쪽 패널은 입력/필터/실행, 가운데는 데이터와 결과, 오른쪽은 미리보기와 상세 정보 역할을 먼저 고려합니다.

### 3. 미리보기 흐름

- 가운데 패널의 선택 상태가 바뀌면 오른쪽 미리보기가 갱신되는 흐름을 기본으로 합니다.
- 미리보기 캐시는 `.cache/` 아래에 둡니다.

### 4. 상태 메시지

- 상태창 메시지는 `app/common/shared_status_bar.py` 형식을 따릅니다.
- 진행률과 상세 문구를 분리해 짧고 일정한 형식으로 유지합니다.

### 5. 설정과 라벨 참조

- 공통 설정은 `ConfigManager`를 통해 읽습니다.
- 라벨 값은 직접 입력하지 말고 `label/*.xlsx` 기준표와 공통 로더를 우선 사용합니다.

### 6. 문서화

- 탭 전용 규칙은 해당 탭 `README.md`에 적습니다.
- 여러 탭에 공통으로 적용되는 규칙은 [docs/README.md](../../docs/README.md)에 올립니다.

## 탭별 문서

- [misc_tools/README.md](./misc_tools/README.md)
- [pre_parse/README.md](./pre_parse/README.md)
- [raw_data_analysis/README.md](./raw_data_analysis/README.md)
- [text_analysis/README.md](./text_analysis/README.md)