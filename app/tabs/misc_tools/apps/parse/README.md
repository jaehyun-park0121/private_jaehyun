# 문서 파서 앱

페이지별 JSON/PNG를 문서 단위 결과 JSON과 산출물로 변환하는 misc tools 앱입니다. 현재 `misc_tools/apps` 안에서 가장 실제 구현 비중이 큰 앱이며, 하위 상세 README를 따로 두지 않고 이 문서를 대표 문서로 사용합니다.

## 폴더 구조

- `__init__.py`: misc tools 탭에서 여는 앱 진입점
- `launcher_dialog/`: 설정 입력, 실행, 로그 표시를 담당하는 다이얼로그
- `document_parser/`: 실제 파싱 로직 패키지
- `config/parser_config.json`: 파서 동작 설정 파일
- `sample/`: 입력/출력 예시와 메타데이터 샘플
- `post_parse/`: 파싱 결과 검증용 후처리 보조 코드
- `requirements.txt`: 앱 실행에 필요한 추가 의존성

## 실행 흐름

1. 기타 도구 탭에서 `문서 파서` 카드를 누르면 전용 다이얼로그가 열립니다.
2. 다이얼로그에서 입력/출력 경로, 메타데이터 엑셀, 병렬 처리, 라벨 규칙 등을 확인합니다.
3. `document_parser.cli`가 설정 파일을 읽어 `DocumentParser`를 생성합니다.
4. `DocumentParser.parse_all_documents()`가 문서 목록을 순차 또는 병렬로 실행합니다.
5. 각 문서는 페이지 JSON 검증, 부모-자식 관계 계산, 렌더링, `pages/` 복사, `crop/` 저장을 거쳐 문서 단위 결과로 저장됩니다.

## 주요 코드 역할

### `launcher_dialog/`

- `dialog.py`: 실행 다이얼로그 본체
- `ui_sections.py`, `widgets.py`, `styles.py`: 다이얼로그 UI 구성
- `config_io.py`: 설정 읽기/쓰기 보조
- `process_runner.py`: CLI 실행과 로그 연결
- `log_handler.py`: 실행 로그 수집

### `document_parser/`

- `cli.py`: CLI 진입점
- `config.py`: `parser_config.json`을 설정 객체로 변환
- `document_parser.py`: 문서 단위 파싱 오케스트레이션
- `models.py`, `errors.py`: 내부 모델과 예외 정의
- `metadata/`: 엑셀 메타데이터 로딩
- `parsing/`: 페이지 JSON 검증, 부모-자식 판정, 렌더링
- `execution/`: 문서 단위 순차/병렬 실행 제어
- `io/`: `pages/` 복사와 `crop/` 저장
- `utils/`: bbox, 좌표 계산 유틸리티

### `post_parse/`

- `validator.py`, `cli.py`: 파싱 결과 구조를 후검증하는 보조 코드
- `post_parse_config.json`: 후검증 설정

## 설정 파일 요약

`config/parser_config.json`은 아래 최상위 섹션을 사용합니다.

- `paths`: 입력 루트, 출력 루트
- `excel`: 메타데이터 엑셀 경로, 시트, 헤더 매핑
- `schema`: 페이지 JSON 검증 기준
- `parser`: 페이지 번호 추출, crop 경로 템플릿, JSON indent, page PNG 저장 여부
- `execution`: 문서 단위 병렬 처리 사용 여부와 worker 수
- `labels`: 라벨별 type, 본문 사용 방식, marker, crop, description 규칙

### `paths`

- `input_root`: 입력 문서 루트
- `output_root`: 출력 문서 루트
- 결과 문서 JSON, `pages/`, `crop/` 폴더가 이 경로 아래 생성됩니다.

### `excel`

- `workbook_path`: 메타데이터 엑셀 파일 경로. `""`이면 메타데이터를 사용하지 않습니다.
- `sheet_name`: 메타데이터 시트 이름
- `header_row`: 헤더 행 번호
- `columns`: 출력 메타 필드와 엑셀 헤더명 연결

### `schema`

- `top_level_shapes_key`: 페이지 JSON에서 shape 목록이 들어 있는 최상위 키
- `required_shape_fields`: 실제 파싱에 사용하는 필드 목록
- `strict_required_fields`: 필수 필드 구조 엄격 검증 여부
- `stop_on_validation_error`: 현재 구현에서는 페이지 단위 경고 후 건너뛰기 방식으로 동작

### `parser`

- `page_number_pattern`: 파일명에서 페이지 번호를 추출하는 정규식
- `crop_dir_template`: `add_info.file_path`와 crop 저장 경로에 사용하는 템플릿
- `output_indent`: 출력 JSON 저장 시 indent 값
- `export_pages`: `true`이면 `contents`에 포함된 페이지의 원본 PNG를 `pages/` 폴더로 복사

### `execution`

- `parallel_enabled`: 문서 단위 병렬 처리 사용 여부
- `max_workers`: 병렬 처리 시 사용할 최대 worker 수

### `labels`

- `labels.{LABEL}.type`: 최종 `type` 값과 tag 내부 type 문자열
- `labels.{LABEL}.use_in_contents`: `text` 또는 `tag`
- `labels.{LABEL}.marker`: 부모 `flags.text` 안에서 자식 tag로 치환할 marker 문자열
- `labels.{LABEL}.crop`: 해당 라벨의 crop 이미지 저장 여부
- `labels.{LABEL}.description_mode`: `none`, `flags_text`, `children_rendered`
- `labels.{LABEL}.chapter_source`: `chapter` 계산에 쓰는 라벨인지 여부

설정을 바꾸면 코드뿐 아니라 이 README 설명도 함께 맞춰 두는 편이 좋습니다.

## 세부 파싱 규칙

### 1. 처리 흐름 요약

1. 페이지 JSON에서 `shapes`를 읽습니다.
2. `label`, `points`, `flags.text` 중심으로 입력 스키마를 검증합니다.
3. `points`를 좌상단/우하단 기준으로 정규화합니다.
4. bbox 완전 포함 관계로 direct parent를 계산합니다.
5. direct parent를 기준으로 각 shape의 ancestor chain을 한 번만 구성합니다.
6. `use_in_contents == "tag"` 라벨에 페이지 내 순서대로 tag를 부여합니다.
7. marker 치환, caption 수집, item description 생성 규칙을 적용해 `page_contents`와 `add_info`를 만듭니다.
8. 페이지 렌더링 후 누락 검증과 tag 참조 검증을 수행합니다.

### 2. 입력 검증 기준

- 페이지 JSON에서 주로 사용하는 필드는 `label`, `points`, `flags.text`입니다.
- `points`는 항상 좌상단/우하단 기준으로 정규화합니다.
- `flags.text`가 없으면 경고 후 빈 문자열로 보정합니다.
- 출력 JSON key는 모두 소문자를 사용합니다.
- `identifiers`, `description` 같은 가변 영역을 제외한 스키마는 고정입니다.
- 값이 없을 때는 `None` 대신 `""`, `{}`, `[]` 같은 빈 값을 사용합니다.

### 3. 메타데이터 처리

- 메타데이터는 `document_parser/metadata`에서 처리합니다.
- `work_id` 기준으로 엑셀 행을 매칭합니다.
- 엑셀 파일명, 시트명, 헤더명 매핑은 모두 `config/parser_config.json`에서 관리합니다.
- 엑셀을 사용하지 않거나 행이 없으면 빈 메타데이터로 계속 진행합니다.

메타데이터 fallback 규칙은 아래와 같습니다.

- `excel.workbook_path == ""`: 빈 메타데이터로 진행
- 문서 ID에 맞는 행이 없음: 해당 문서는 빈 메타데이터로 진행
- 개별 헤더가 없음: 해당 필드만 `""`로 채우고 경고 출력
- `work_id`용 ID 헤더가 없음: 행 매칭이 불가능하므로 빈 메타데이터로 진행

메타데이터 값 정규화는 아래 기준을 따릅니다.

- `published_date`를 제외한 메타 필드: `str(value).strip()` 기준 문자열화
- `published_date`: 날짜/시간 객체는 ISO 문자열, 나머지는 문자열 변환

### 4. 정렬 기준

- 정렬 기능은 별도 단계에서 처리된다고 가정합니다.
- 현재 파서는 입력 JSON의 shape 순서를 그대로 사용합니다.

### 5. 부모-자식 관계 계산

- 부모-자식 판정은 입력 JSON의 bbox 포함 관계만 사용합니다.
- 기준은 완전 포함입니다.
- direct parent는 나를 포함하는 박스들 중 가장 작은 박스입니다.
- direct parent가 정해진 뒤 각 shape의 ancestor chain을 한 번만 계산합니다.
- 이후 ancestor 여부가 필요한 모든 로직은 이 chain을 재사용합니다.

### 6. tag 부여

- `use_in_contents == "tag"` 라벨에만 tag를 부여합니다.
- 내부 저장값은 `{type}_{work_id}_{page}_{seq}` 형식입니다.
- 문자열에 삽입될 때는 `{tag}` 형태로 감싸서 사용합니다.
- `seq`는 부모-자식 여부와 무관하게 페이지 내 같은 type의 등장 순서입니다.
- `add_info.tag`, crop 파일명, `file_path`에는 중괄호 없는 tag 값을 저장합니다.

### 7. `contents` 기본 생성 방식

- 기본 단위는 페이지 내 shape 순서입니다.
- 현재 구현은 부모-자식 관계를 기반으로, 부모에게 실제로 흡수된 박스만 본문에서 제외하고 흡수되지 않은 박스는 독립 박스로 유지하는 방식입니다.
- `use_in_contents == "text"` 라벨은 `flags.text`를 본문에 사용합니다.
- `use_in_contents == "tag"` 라벨은 본문에 `{tag}`를 넣고, 세부 내용은 `add_info`에서 생성합니다.
- 각 박스 사이는 `\n`으로 구분합니다.
- `flags.text == ""`이어도 한 줄로 취급하며 줄 구분은 유지합니다.
- 라벨이 하나도 없는 페이지, 즉 shape가 없는 페이지는 `contents` 객체를 만들지 않습니다.

### 8. marker 치환

- 부모 `flags.text` 안의 marker와 direct child tag 라벨을 type별로 비교합니다.
- 같은 type 기준으로 marker 개수와 child 수가 같을 때만 치환합니다.
- 치환 순서는 child shape 순서입니다.
- type별 기본 marker는 config에서 관리합니다.
  - `IMAGE` -> `{im}`
  - `FORMULA` -> `{fr}`
  - `TABLE` -> `{tb}`
  - `ITEM` -> `{em}`
  - `CHART` -> `{ch}`
  - `FOOTNOTE` -> `{fn}`
- marker 수와 child 수가 다르면 치환하지 않습니다.
- 치환에 사용되지 않은 child는 부모-자식 관계가 있어도 독립 박스로 계속 처리합니다.

### 9. `add_info`

- `use_in_contents == "tag"` 라벨만 `add_info`를 만듭니다.
- `add_info` 정렬은 페이지 전체 shape 순서를 유지합니다.
- 각 항목은 아래 값을 가집니다.
  - `tag`
  - `type`
  - `description.value`
  - `caption`
  - `file_path`

#### `description_mode == "flags_text"`

- 기본적으로 해당 박스의 `flags.text`를 사용합니다.
- marker 치환 조건이 맞으면 `flags.text` 내부 marker가 `{tag}`로 치환된 결과를 사용합니다.

#### `description_mode == "children_rendered"`

- 내부 descendant를 본문과 같은 규칙으로 다시 전개한 결과를 사용합니다.
- 현재는 `ITEM`에 사용합니다.

### 10. caption

- `CAPTION`은 `use_in_contents == "text"` 라벨입니다.
- 부모가 없는 caption은 본문에 텍스트로 들어갑니다.
- 부모가 있고, 그 부모가 `use_in_contents == "tag"` 라벨이면 해당 부모의 `add_info.caption`으로 흡수됩니다.
- 같은 부모 아래 caption이 여러 개면 `\n`으로 연결해 모두 `add_info.caption`에 저장합니다.
- 부모 caption으로 흡수된 caption은 본문에 다시 쓰지 않습니다.

### 11. item

- `ITEM`은 자체 `flags.text` 대신 내부 내용으로 description을 만듭니다.
- `item.description.value`는 item 내부에서 아직 흡수되지 않은 모든 descendant를 대상으로 본문과 같은 방식으로 렌더링합니다.
- text 라벨은 텍스트로, tag 라벨은 `{tag}`로 들어갑니다.
- item 내부 박스는 본문에 다시 사용하지 않습니다.
- item의 caption child는 description이 아니라 `caption`에만 들어갑니다.

### 12. chapter 계산

- `chapter`는 `TITLE` 라벨 기준으로 계산합니다.
- 현재 페이지에 `TITLE`이 여러 개 있으면 가장 먼저 등장한 값을 사용합니다.
- 현재 페이지에 `TITLE`이 없으면 이전 페이지에서 가장 최근에 등장한 `TITLE`을 이어받습니다.
- 이전 페이지에도 `TITLE`이 없으면 `""`를 사용합니다.

### 13. 누락 검증

페이지 렌더링이 끝나면 각 shape가 아래 경로 중 하나에는 반드시 반영되었는지 확인합니다.

- `page_contents`
- `add_info` 본체
- 부모 text의 marker 치환 결과
- 부모 `caption`
- `item.description`

또한 부모가 있는 tag 라벨은 `add_info`에만 존재하고 실제 `contents` 또는 `description` 어디에도 참조되지 않는 상태가 없는지 별도로 확인합니다.

현재는 검증 실패 시 경고를 남기고 해당 페이지를 건너뜁니다.

## 개발 중 추가 로직과 구현 메모

### 실제 사용하는 입력 필드

- `label`
- `points`
- `flags.text`

그 외 `result`, `failedReason` 같은 필드는 파싱에 사용하지 않습니다.

### 라벨 표준화

- 입력 라벨은 config의 표준 라벨 값을 기준으로 해석합니다.
- 현재 기본 라벨은 아래와 같습니다.
  - `TEXT`
  - `TITLE`
  - `CAPTION`
  - `IMAGE`
  - `FORMULA`
  - `TABLE`
  - `CHART`
  - `ITEM`
  - `FOOTNOTE`

### 차트 특수 입력

- 차트 라벨 등에서 `flags`의 key 값으로 `text`가 사용되지 않는 경우, description은 빈 문자열로 처리됩니다.
- `flags` 내부의 다른 key들은 현재 파싱 로직에서 사용하지 않습니다.

### 성능 최적화

#### ancestor chain 사전 계산

- 페이지 JSON을 읽어 shape를 구성할 때 direct parent 계산 직후 ancestor chain을 한 번만 만듭니다.
- 이후 descendant 여부, item 내부 포함 여부, 중간 ancestor 검사에 이 chain을 재사용합니다.
- 동작 의미는 기존 `parent_index` 반복 추적과 동일하므로 로직 변화 위험은 낮고, 반복 순회를 줄여 성능 개선 효과가 큽니다.

#### descendant index 재사용

- renderer는 페이지 시작 시 ancestor chain 기반 descendants index를 한 번 구성합니다.
- item description 생성 시 전체 shape를 매번 다시 순회하지 않고, 미리 만든 descendants index를 사용합니다.

#### crop I/O 최소화

- crop 대상 shape가 없는 페이지는 이미지 파일을 열지 않습니다.
- `crop/{LABEL}` 디렉터리는 label별 1회만 생성합니다.
- 이미지 파일도 페이지당 1회만 열어 모든 crop을 처리합니다.

#### 문서 단위 병렬 처리

- 병렬 처리는 페이지가 아니라 문서 단위로 수행합니다.
- 병렬 제어 코드는 `document_parser/execution/`에 분리되어 있습니다.
- `config.execution.parallel_enabled`와 `config.execution.max_workers`로 제어합니다.

## 입출력 규칙

### page PNG 저장 규칙

- `config.parser.export_pages == true`일 때만 동작합니다.
- 저장 경로는 `output_root/{document_id}/pages/{원본_png_파일명}`입니다.
- `contents`에 페이지 객체가 추가된 뒤에만 복사합니다.
- 원본 PNG가 없으면 건너뜁니다.

### crop 저장 규칙

- `config.labels.{LABEL}.crop == true`인 라벨만 저장합니다.
- 저장 경로는 `output_root/{document_id}/crop/{LABEL}/{tag}.png`입니다.
- `add_info.file_path`도 같은 규칙을 따릅니다.
- 파일명에는 중괄호 없는 tag 값을 사용합니다.

## 현재 주요 경고 메시지

| 오류 구분 | 처리 방법 | 실제 메시지 | 내용 |
| --- | --- | --- | --- |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] JSON 최상위는 객체여야 합니다.` | 페이지 JSON 최상위 구조가 객체가 아닌 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] 'shapes'가 없습니다.` | `shapes` 키가 없는 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] 'shapes'는 list여야 합니다.` | `shapes`가 list가 아닌 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index]는 객체여야 합니다.` | 개별 shape 구조가 객체가 아닌 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].label은 문자열이어야 합니다.` | `label` 타입이 잘못된 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].points는 길이 2의 list여야 합니다.` | `points` 구조가 잘못된 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].points[point_index]는 길이 2의 list여야 합니다.` | point 구조가 잘못된 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].points[point_index]는 숫자여야 합니다.` | point 좌표 타입이 잘못된 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].flags는 객체여야 합니다.` | `flags` 타입이 잘못된 경우 |
| JSON 경고 | 경고 후 현재 페이지 건너뜀 | `[파일명] shape[index].flags.text는 문자열이어야 합니다.` | `flags.text` 타입이 잘못된 경우 |
| JSON 경고 | 경고 후 계속 진행 | `[파일명] shape[index].flags.text가 없어 빈 문자열로 처리합니다.` | `flags.text` 키가 없는 경우 |
| 설정 경고 | 경고 후 현재 페이지 건너뜀 | `설정에 없는 라벨 'SAMPLE'입니다. config.labels에 먼저 추가해 주세요.` | 페이지 JSON에 `config.labels`에 등록되지 않은 라벨이 있는 경우 |
| 설정 오류 | 실행 중단 | `필수 설정 키가 없습니다: 'labels'` | `parser_config.json`에 필수 설정 블록이나 키가 누락된 경우 |
| 입력 경고 | 경고 후 처리 종료 | `[DOC] 처리할 문서 폴더가 없습니다.` | `input_root` 아래에 문서 단위 하위 폴더가 없는 경우 |
| 파일명 경고 | 경고 후 해당 페이지 제외 | `파일명 '파일명'에서 페이지 번호를 찾을 수 없습니다.` | 파일명 패턴이 설정과 맞지 않는 경우 |
| 렌더링 경고 | 경고 후 현재 페이지 건너뜀 | `일부 shape가 contents/add_info에 반영되지 않았습니다: ...` | shape가 어느 출력 경로에도 반영되지 않은 경우 |
| 렌더링 경고 | 경고 후 현재 페이지 건너뜀 | `일부 add_info tag가 contents/description에 참조되지 않았습니다: ...` | 부모가 있는 tag shape가 실제 문자열 어디에도 쓰이지 않은 경우 |
| 페이지 경고 | 경고 후 다음 페이지 진행 | `페이지 '파일명' 파싱 중 경고가 발생하여 건너뜁니다: ...` | 페이지 파싱 중 발생한 개별 오류를 감싸는 최종 경고 |
| 메타데이터 경고 | 경고 후 빈 메타데이터 진행 | `메타데이터 엑셀 파일이 설정되지 않아 빈 메타데이터로 진행합니다.` | 엑셀 파일 경로가 비어 있는 경우 |
| 메타데이터 경고 | 경고 후 빈 메타데이터 진행 | `work_id '...'에 해당하는 메타데이터 행이 없어 빈 메타데이터로 진행합니다.` | 해당 문서 ID와 일치하는 행이 없는 경우 |
| 메타데이터 경고 | 경고 후 빈 메타데이터 진행 | `메타데이터 로딩 중 오류가 발생하여 빈 메타데이터로 진행합니다: ...` | workbook 로딩이나 시트 접근 자체가 실패한 경우 |
| 메타데이터 경고 | 경고 후 해당 필드만 빈 문자열 사용 | `메타데이터 헤더가 없어 해당 값은 빈 문자열로 처리합니다: ...` | 일부 헤더가 없어 개별 필드만 채우지 못하는 경우 |
| 메타데이터 경고 | 경고 후 마지막 행 사용 | `메타데이터 ID '...'가 중복되어 마지막 행을 사용합니다.` | 같은 `work_id`가 여러 행에 있으면 마지막으로 읽은 행으로 덮어씁니다. |
| 메타데이터 경고 | 경고 후 빈 메타데이터 진행 | `메타데이터 ID 헤더 '...'가 없어 빈 메타데이터로 진행합니다.` | `work_id` 매칭용 헤더가 없어 전체 행 매칭이 불가능한 경우 |

## 샘플 자료

`sample/` 폴더에는 아래 자료가 있습니다.

- 단일 페이지 입력 JSON 예시
- 문서 단위 출력 JSON 예시
- 메타데이터 입력용 엑셀 예시

문서 구조를 확인하거나 설정 변경 결과를 비교할 때 먼저 이 샘플을 보는 편이 좋습니다.

## 유지보수 메모

- 파서 핵심 규칙을 바꾸면 `parser_config.json`, 실행 다이얼로그, 이 README를 함께 갱신합니다.
- 라벨 기준은 코드에 직접 박지 말고 설정과 루트 `label/` 기준을 함께 확인합니다.
- 샘플 데이터나 로컬 실험 파일에 민감 정보가 섞이지 않도록 주의합니다.
- 문서 파서 앱 하위에 다시 많은 README를 만들기보다, 반복해서 참고하는 핵심 규칙은 이 문서에 통합하는 편이 좋습니다.

## 관련 문서

- [misc_tools/apps/README.md](../README.md)
- [misc_tools/README.md](../../README.md)
- [docs/README.md](../../../../../docs/README.md)
