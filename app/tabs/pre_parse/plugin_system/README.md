# pre_parse/plugin_system

파싱 전 검사 탭의 플러그인 공통 계약, 로딩 규칙, 실행 흐름을 모아둔 폴더입니다.

## 폴더 구성

- `base.py`: `BasePlugin`, `BaseCheckPlugin` 정의
- `context.py`: 플러그인 `run()`에 전달되는 `PageContext` 정의
- `result_model.py`: `CheckResult`, `Issue` 정의
- `loader.py`: `plugins/` 폴더 스캔, import, `PLUGIN_ID` 부여
- `registry.py`: 로드된 플러그인 등록/조회
- `runner.py`: 선택된 플러그인 실행과 예외 처리

## 로딩 및 실행 흐름

1. `loader.py`가 `plugins/` 아래의 `*.py` 파일을 이름순으로 스캔합니다.
2. 파일명이 `_`로 시작하면 로드하지 않습니다.
3. 각 파일에서 `Plugin` 클래스를 찾고, `BasePlugin` 계열인지 확인한 뒤 인스턴스를 만듭니다.
4. 로더는 인스턴스에 `source_file`과 `PLUGIN_ID = 파일명(stem)`을 강제로 설정합니다.
5. `state_ui.py`가 `metadata()`와 `option_schema()`를 읽어 좌측 패널 체크 카드 UI를 만듭니다.
6. 사용자가 선택한 옵션은 `left_panel.py`에서 수집되어 `page_context.config[plugin_id]`로 전달됩니다.
7. `runner.py`가 각 페이지마다 `run(page_context)`를 호출하고, 반환된 `CheckResult`를 결과 표/통계/CSV export로 넘깁니다.
8. 플러그인 실행 중 예외가 나면 `runner.py`가 `PLUGIN_RUNTIME_ERROR`로 감싸서 결과에 포함합니다.

## `template_check.py` 존재와 사용 방법

- `app/tabs/pre_parse/plugins/template_check.py`는 새 플러그인 작성용 참고 템플릿입니다.
- 이 파일이 `plugins/` 폴더에 그대로 있으면 실제 플러그인처럼 로드되고, 좌측 패널에도 표시됩니다.
- 새 플러그인을 만들 때는 `template_check.py`를 복사한 뒤, 실제 목적에 맞는 파일명으로 바꿔서 작성하는 방식을 권장합니다.
- 템플릿 파일을 운영 목록에서 숨기고 싶다면 파일명을 `_template_check.py`처럼 `_`로 시작하게 바꾸거나 폴더 밖으로 이동해야 합니다.

## 작성 시 가장 중요한 규칙

### 파일명

- 파일명(stem)은 곧 `plugin_id`입니다.
- 현재 구현에서는 클래스에 어떤 `PLUGIN_ID`를 적더라도 로더가 최종적으로 파일명으로 덮어씁니다.
- 이 값은 아래 위치에 직접 반영됩니다.
  - 좌측 패널 카드 제목 기본값
  - 옵션 저장 키 `page_context.config[plugin_id]`
  - `CheckResult.check_id`
  - 결과 집계의 `failed_checks`
  - `issues.csv`의 `check_id`

파일명을 바꾸면 곧 결과 식별자와 옵션 키가 바뀌는 것이므로, 운영 중인 플러그인은 이름 변경에 특히 주의해야 합니다.

### `TAG`

- 짧은 분류 문자열입니다.
- 현재 UI에서는 좌측 패널 카드 제목 앞에 `[TAG] 파일명` 형태로 붙습니다.
- 현재 코드 기준으로 `필수`, `선택`, `optional` 같은 짧은 값을 사용하고 있습니다.

### `DESCRIPTION`

- 플러그인 설명 문자열입니다.
- 좌측 패널 카드의 `i` 툴팁에 그대로 표시됩니다.
- 결과 데이터의 `description` 필드에도 반영되어, 어떤 검사를 수행한 플러그인인지 설명하는 기준이 됩니다.

### `option_schema()`

`option_schema()`는 좌측 패널 카드 하단 옵션 폼을 구성합니다. 현재 UI가 읽는 주요 키는 아래와 같습니다.

- `key`: 실제 옵션 저장 키. `page_context.config[self.PLUGIN_ID][key]`로 전달됩니다.
- `label`: 좌측 패널 폼 라벨 텍스트
- `type`: 현재 지원 타입은 `bool`, `select`, `text`, `multi_select`, `multi_select_buttons`, `buttons`
- `choices`: `select`, `multi_select_buttons`에서 표시할 값 목록
- `default`: 초기값
- `placeholder`: `text`, `select`의 안내 문구
- `columns`: `multi_select_buttons` 버튼 열 개수

현재 UI 반영 방식은 아래와 같습니다.

- `bool`: 체크박스
- `select`: 드롭다운
- `text`: 한 줄 입력창
- `multi_select`, `multi_select_buttons`, `buttons`: 모두 다중 선택 버튼 묶음으로 처리

지원하지 않는 키는 현재 UI에서 무시됩니다.

## `PageContext`에 들어오는 값

`run(page_context)`에서 기본으로 사용할 수 있는 값은 아래와 같습니다.

- `project_id`: 현재 프로젝트 ID
- `book_id`: 도서 ID
- `page_no`: 페이지 번호
- `json_data`: 검사 대상 페이지 JSON payload
- `image_path`: 필요 시 사용할 수 있는 이미지 경로
- `ocr_text`: 필요 시 사용할 수 있는 OCR 텍스트
- `config`: 선택된 플러그인 옵션 묶음

현재 플러그인 대부분은 `json_data`와 `config`를 중심으로 동작합니다.

## `CheckResult`와 `Issue`가 반영되는 위치

### `CheckResult`

- `check_id`
  - 보통 `self.PLUGIN_ID`를 그대로 넣습니다.
  - 어떤 플러그인에서 나온 결과인지 식별하는 기준입니다.
- `status`
  - `"PASS"` 또는 `"FAIL"`을 사용합니다.
  - 페이지별 실패 여부, `failed_checks`, 통계 계산에 반영됩니다.
- `issues`
  - 오류 항목 리스트입니다.
  - 길이가 곧 이 플러그인의 `issue_count`가 됩니다.
- `debug_message`
  - 페이지 레벨 메시지가 필요할 때 사용합니다.
  - `issues`가 없어도 별도 행으로 표시될 수 있습니다.

### `Issue`

- `shape_index`
  - 0 이상이면 해당 shape와 연결됩니다.
  - `-1`이면 특정 박스가 아니라 페이지 전체에 대한 오류로 처리됩니다.
- `error_type`
  - 결과 표의 오류 유형 필터와 우측 패널 오류 유형 통계에 반영됩니다.
- `error_message`
  - 결과 표 상세 내용과 `issues.csv`의 `error_message` 컬럼에 반영됩니다.
- `issue_code`
  - 내부 식별용 안정 코드입니다.
  - 현재 주요 UI에는 직접 노출되지 않지만, 규칙 분기와 향후 자동화 기준으로 쓰기 좋습니다.
  - 영문 대문자 + `_` 조합을 권장합니다.

## `template_check.py` 기준 변수별 반영 예시

`template_check.py`는 각 필드가 어디에 반영되는지 보기 좋은 예시입니다.

- 파일명 `template_check.py`
  - `plugin_id`, `check_id`, 옵션 저장 키가 모두 `template_check`가 됩니다.
- `TAG = "optional"`
  - 좌측 패널 카드 제목이 `[optional] template_check`처럼 보입니다.
- `DESCRIPTION`
  - 카드 우측 `i` 툴팁 설명으로 표시됩니다.
- `option_schema()`의 `enabled`
  - 좌측 패널 체크박스로 표시됩니다.
  - `False`이면 `run()` 초반에 바로 `PASS`를 반환합니다.
- `option_schema()`의 `result_mode`
  - 드롭다운으로 표시됩니다.
  - `FAIL_DEMO`를 선택하면 예시 오류를 하나 생성합니다.
- `option_schema()`의 `demo_text`
  - 한 줄 입력창으로 표시됩니다.
  - 비워두면 코드 안의 기본 메시지를 사용합니다.
- `option_schema()`의 `target_labels`
  - 다중 선택 버튼으로 표시됩니다.
  - 현재 템플릿에서는 실제 필터링에는 쓰지 않고, 오류 메시지 안에 대상 라벨 목록을 덧붙이는 예시로만 사용합니다.
- `Issue(shape_index=0, error_type="[템플릿 예시 오류]", error_message=..., issue_code="TEMPLATE_DEMO_ISSUE")`
  - shape index `0` 행에 오류가 연결됩니다.
  - `error_type`는 오류 유형 통계/필터에 잡히고, `error_message`는 상세 내용에 표시됩니다.

## 구현 메모

- 현재 좌측 패널 UI는 체크 카드가 단일 선택 방식입니다.
  - 다른 플러그인을 체크하면 기존 선택이 해제됩니다.
  - 백엔드 실행부는 여러 `plugin_id`를 받을 수 있지만, 현재 화면은 한 번에 하나를 중심으로 쓰는 구조입니다.
- 플러그인 설명이나 옵션 의미가 바뀌면 [plugins/README.md](../plugins/README.md)도 같은 커밋에서 함께 갱신하는 것을 권장합니다.

## 관련 문서

- [pre_parse/README.md](../README.md)
- [plugins/README.md](../plugins/README.md)
