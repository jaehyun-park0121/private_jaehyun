# label

프로그램에서 참조하는 기본 라벨 기준표(`*.xlsx`)를 두는 폴더입니다.

## 이 폴더의 역할

- 라벨 ID 기준값 제공
- 라벨 표시명과 색상 기준 제공
- 라벨 선택 UI와 라벨 기반 검사 로직의 공통 기준 제공

## 권장 파일 형식

- 위치: `label/<파일명>.xlsx`
- 첫 번째 시트를 기준으로 사용
- 권장 컬럼
  - `id`
  - `title`
  - `color`

`color` 값은 `#RRGGBB` 형식을 권장합니다.

## 사용 원칙

- 코드에서 라벨 값을 직접 하드코딩하지 않고 `label/` 기준표를 우선 참조합니다.
- 여러 파일이 있으면 현재 로더는 이름순 첫 번째 `*.xlsx`를 기준으로 읽습니다.
- 기준표 구조가 바뀌면 관련 탭 README와 `docs/README.md`도 함께 확인합니다.

## 관련 코드

- `app/common/labels/label_reference.py`
- `app/tabs/pre_parse/plugins/빈 라벨 값 검사.py`
- `app/tabs/raw_data_analysis/ui_shared.py`