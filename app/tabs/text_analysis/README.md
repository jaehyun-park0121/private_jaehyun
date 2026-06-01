# 텍스트 분석 탭

선택한 라벨 범위의 `flags.text`를 기준으로 검색, 치환, NFKC 정규화, 특수문자 검사를 수행하는 탭입니다.

이 탭은 크게 세 단계로 동작합니다.

1. 조회 시점 JSON을 스냅샷으로 확보
2. 라벨 단위 텍스트를 읽어 검색/특수문자 분석 수행
3. 필요하면 현재 화면에 보이는 검색/필터 결과만 골라 실제 S3 JSON의 `flags.text`를 치환하거나 NFKC 정규화

## 폴더 구조

- `page.py`: 3분할 레이아웃 조립과 상위 상태 연결
- `features/snapshot_flow.py`: 조회, JSON 스냅샷 준비, 조회 중지 처리
- `features/run_flow.py`: 검색/특수문자 분석/치환 실행 흐름
- `features/row_builders.py`: 라벨 행 조립, KWIC 표시행 확장, issue 변환
- `features/preview.py`: 오른쪽 미리보기 로직
- `features/problem_sync_strict.py`: `확인 필요` 체크/초기화와 S3 반영
- `features/page_support.py`: S3 재조회, 상태 초기화, 대시보드 갱신
- `features/workers/scan_worker.py`: 검색/특수문자 분석 worker
- `features/workers/replace_worker.py`: 치환 저장 worker
- `tools/`: 실제 검사/치환 도구 정의와 실행 레지스트리
- `panels/`: 좌/중/우 패널 UI
- `widgets/`: 이미지 미리보기와 툴팁 같은 보조 위젯

## 검수 도구 설명

### 특수문자 분석

- 관련 파일:
  - `tools/special_char.py`
  - `panels/left_panel.py`
- 입력:
  - `허용 패턴`
  - `대상 라벨`
- 동작:
  - `flags.text`에서 허용 패턴 밖의 문자를 정규식으로 찾습니다.
  - 대상 라벨이 지정되어 있으면 해당 라벨에만 검사합니다.
- 결과 반영:
  - `tool_id = special_char_analysis`
  - `tool_error_type = 특수문자 분석`
  - `tool_error_detail = 허용 외 문자: ...`
  - `detail_filter_values = 검출된 문자 목록`
- 화면 표시:
  - 중앙 패널은 매치 단위로 펼쳐져 KWIC 형식으로 보여줍니다.
  - detail 필터에는 실제 검출 문자값이 들어가고, 개행/탭/공백은 `\n`, `\t`, `<space>` 형태로 렌더링합니다.

### 검색

- 관련 파일:
  - `tools/search.py`
  - `panels/left_panel.py`
- 입력:
  - `검색어`
  - `정규식 모드`
  - `대소문자 구분`
- 동작:
  - 각 라벨의 `flags.text`에서 패턴이 매치되는 부분을 찾습니다.
  - 문자열 검색일 때는 `re.escape(keyword)` 기반, 정규식 모드일 때는 입력 패턴을 그대로 씁니다.
- 결과 반영:
  - `tool_id = search_tool`
  - `tool_error_type = 검색어`
  - `tool_error_detail = 검색 결과: ...`
  - `match_spans = [start, end, matched_text]`
  - `detail_filter_values = 실제 매치된 문자열`
- 화면 표시:
  - 한 라벨에서 여러 번 매치되면 중앙 패널에 매치 수만큼 여러 행으로 확장됩니다.
  - 각 행은 KWIC 형식으로 전후 문맥 20자를 함께 보여줍니다.

### 치환

- 관련 파일:
  - `tools/replace.py`
  - `features/workers/replace_worker.py`
  - `features/run_flow.py`
- 입력:
  - `치환 값`
  - `정규식 모드`
- 중요한 동작 원칙:
  - 치환은 독립 도구처럼 보이지만, 실제 찾을 값과 검색 옵션은 마지막으로 실행한 `검색` 도구의 컨텍스트를 그대로 사용합니다.
  - 즉 치환 전에 검색을 먼저 실행해야 합니다.
  - 치환 카드의 `정규식 모드`는 검색 패턴을 다시 정규식으로 바꾸는 옵션이 아니라, 치환 문자열에서 캡처 그룹 치환(`match.expand`)을 허용할지 여부입니다.
- 대상 범위:
  - 현재 중앙 패널에 보이는 행 중
  - `search_tool` 결과가 살아 있고
  - 아직 `replace_applied=False`인 라벨만 대상입니다.
- 결과 반영:
  - 실제 S3 JSON의 `flags.text`를 수정하고 검증까지 통과하면
  - `tool_id = replace_tool`
  - `tool_error_type = 원본검색어 -> 치환값`
  - `tool_error_detail = 치환 완료: ...`
  - `replace_applied = True`
  - `flags_text`, `value`도 치환 후 값으로 갱신됩니다.

### NFKC 정규화

- 관련 파일:
  - `panels/left_panel.py`
  - `features/run_flow.py`
  - `features/workers/replace_worker.py`
- 입력:
  - 별도 입력값 없음
- UI 문구:
  - 카드 제목: `NFKC 정규화`
  - 설명: `검색/필터된 데이터를 NFKC 정규화합니다.`
- 중요한 동작 원칙:
  - 검색 또는 특수문자 분석으로 만들어진 현재 중앙 결과 테이블과 필터 상태를 기준으로 합니다.
  - 라벨 전체가 아니라 현재 표시된 매칭 구간만 `unicodedata.normalize("NFKC", value)`로 정규화합니다.
  - 카드 선택 시 미리보기를 자동 표시하고, 실행 버튼을 눌렀을 때 실제 S3 JSON에 반영하는 흐름을 치환과 동일하게 유지합니다.
  - NFKC 결과가 원문과 같은 구간은 저장 대상에서 제외합니다.
- 대상 범위:
  - 현재 중앙 패널에 보이는 매치 표시행 중
  - `search_tool` 또는 `special_char_analysis` 결과가 살아 있고
  - 아직 정규화 적용 완료 상태가 아닌 구간만 대상입니다.
- 길이 변경 처리:
  - `㎜ -> mm`, `① -> 1`처럼 정규화 후 길이가 달라질 수 있으므로, 원문 기준 `match_spans`를 직접 수정하지 않습니다.
  - 같은 `flags.text` 안의 대상 구간을 `row_key` 기준으로 모은 뒤, 원문 기준 start/end 좌표로 텍스트를 한 번에 재조립합니다.
  - span 겹침, 범위 오류, 조회 당시 매치값 불일치가 있으면 해당 라벨은 실패 처리합니다.
- 적용 후 상태:
  - 적용 성공 행은 치환 성공 행과 같은 연한 파란 배경으로 표시합니다.
  - 적용 완료된 구간은 추가 NFKC 대상에서 제외합니다.
  - 다시 검색/특수문자 분석을 실행하면 새 결과 기준으로 다시 대상화할 수 있습니다.

### 치환 시 S3 변동이 있는 경우 처리 방식

치환은 저장 직전 최신 S3 JSON을 다시 읽어, 조회 시점 스냅샷과 비교합니다.

- 비교 기준:
  - `is_problem`, `problem_reason`는 제외하고 비교
- 불일치가 있으면:
  - 해당 페이지는 치환 준비 단계에서 `snapshot_mismatch_pages`로 분류
  - 하나라도 있으면 이번 치환 전체를 중단
  - 경고 메시지:
    - `치환 시점에 S3 데이터가 스냅샷과 달라 치환을 진행하지 않았습니다.`

즉, 다른 사람이 JSON을 바꿨거나 조회 이후 최신본이 달라진 경우에는 부분 적용하지 않고 전체를 멈추는 쪽을 택하고 있습니다.

### 치환 시 자주 나오는 오류/실패 유형

행 단위 실패:

- `shape 인덱스를 찾을 수 없습니다.`
- `shape 구조가 올바르지 않습니다.`
- `flags.text가 비어 있어 치환할 수 없습니다.`
- `현재 S3 flags.text에서 검색 패턴이 일치하지 않습니다.`

치명적 중단(`fatal_error`) 유형:

- `치환 중 S3 JSON shapes 구조를 읽을 수 없습니다.`
- `치환 후 S3 검증에 실패했습니다. shapes 구조를 읽을 수 없습니다.`
- `치환 후 S3 검증에 실패했습니다. shape 인덱스를 찾을 수 없습니다.`
- `치환 후 S3 검증에 실패했습니다. flags.text 값이 반영되지 않았습니다.`

README를 수정할 때는 이 오류 메시지와 실제 코드 메시지가 어긋나지 않는지 같이 보는 편이 좋습니다.

## 실행 흐름

1. S3에서 도서/페이지 목록을 읽어옵니다.
2. 사용자가 도서를 선택하고 `조회`를 누르면 페이지 placeholder를 먼저 표시합니다.
3. JSON 스냅샷을 병렬로 내려받아 `.cache`에 저장합니다.
4. 스냅샷 JSON에서 내부용 라벨 데이터(`current_label_rows`)를 준비하되, 중앙 패널은 계속 페이지 placeholder를 유지합니다.
5. 첫 실행 시 placeholder 상태라면 전체 라벨 데이터를 한 번 풀로 읽어 현재 작업 대상을 확정합니다.
6. 선택한 도구를 실행하면 각 라벨 행에 분석 결과 patch를 덧붙입니다.
7. 중앙 패널은 결과가 있는 라벨만 보여주고, 필요하면 매치 단위로 다시 펼칩니다.
8. 치환은 현재 필터 결과 안에서 검색 결과가 있는 행만 골라 S3 최신본에 반영합니다.
9. `확인 필요` 체크/초기화는 현재 필터 결과 기준으로 수행합니다.

## 병렬화 적용 지점 및 방식

### 1. 조회 시 JSON 스냅샷 준비

- 적용 파일: `features/json_snapshot_worker.py`
- 방식: `ProcessPoolExecutor`
- 단위: 페이지 JSON 1개
- 목적:
  - 조회 시점 JSON을 캐시에 고정
  - 미리보기/검색/치환/확인 필요 저장 기준 통일

### 2. 검색 / 특수문자 분석

- 적용 파일: `features/workers/scan_worker.py`
- 방식: `ProcessPoolExecutor`
- 단위:
  - 기본적으로 라벨 행 200개씩 chunk 분할
  - chunk 하나를 프로세스 하나가 처리
- 목적:
  - shape 수가 많은 문서에서도 텍스트 규칙 실행 시간을 줄이기 위함

즉 검색과 특수문자 분석은 “라벨 단위 검사”를 chunk로 묶어 병렬 처리합니다.

### 3. 치환

- 적용 파일: `features/workers/replace_worker.py`
- 방식: 전용 `QThread` 안에서 페이지별 순차 처리
- 병렬 미적용 이유:
  - 최신 S3 로드
  - 치환 적용
  - 저장
  - 저장 후 재조회 검증
  를 같은 페이지 단위로 안전하게 묶어야 하기 때문입니다.

즉 치환은 속도보다 최신본 검증과 저장 안정성을 우선한 흐름입니다.

### 4. 확인 필요 저장/초기화

- 적용 파일: `features/problem_sync_strict.py`
- 방식:
  - 최신 JSON 사전 조회: `ThreadPoolExecutor`
  - 실제 저장: `ThreadPoolExecutor`
- 단위: 페이지 1개

## 결과 행 구성 방식

### 조회 직후

조회 직후에는 아직 라벨 텍스트를 모두 읽기 전이므로, 페이지 placeholder 행부터 보입니다.

- `shape_index = -1`
- `label`, `value`, `flags_text`는 비어 있음
- `base_state = normal`

이 단계에서 중앙 패널은 페이지 단위 목록처럼 보입니다. JSON 스냅샷이 끝나도 화면은 그대로 유지되고, 첫 실행 직전에 전체 라벨 데이터를 읽어 실제 작업 대상을 확정합니다.

### 첫 실행 직전 전체 라벨 로딩

검색/특수문자 분석/치환을 처음 실행할 때 아직 placeholder 상태라면 `_load_full_label_data()`가 호출됩니다.

- 대상:
  - 현재 조회 대상으로 선택된 도서의 JSON 페이지
- 동작:
  - 각 JSON에서 `shapes`를 다시 읽어 shape당 1개 라벨 행을 만듭니다.
  - 이 시점부터 `current_label_rows`가 실제 실행 기준 데이터가 됩니다.

### 라벨 단위 원본 행

스냅샷 JSON을 다 읽으면 `_build_label_row()`가 shape당 1개 행을 만듭니다.

주요 필드:

- `row_key = book_id:page_name:shape_index+1`
- `book_id`
- `page_no`
- `page_name`
- `page`
- `label_id`
- `shape_index`
- `label`
- `value`
- `flags_text`
- `bbox`
- `is_problem`
- `problem_reason`
- `tool_id`
- `tool_error_type`
- `tool_error_detail`
- `tool_error_matches`
- `match_spans`
- `replace_preview_value`
- `replace_applied`

### 검색/특수문자 실행 후

검색과 특수문자 분석은 원본 라벨 행 자체를 지우지 않고 patch를 덧붙이는 방식입니다.

- `tool_error_detail`이 있으면 `base_state = error`
- `detail_filter_values`에는 필터용 매치값을 따로 저장
- 실행 후 중앙 패널은 `results_only=True` 상태로 전환되어 매치가 있는 라벨만 보여줍니다.

### 매치 단위 표시행(KWIC)

검색/특수문자 분석 결과가 있는 행은 `expand_label_rows_to_display_rows()`에서 표시 전용 행으로 다시 펼칩니다.

- 한 라벨에 매치가 여러 개면 여러 행으로 증가
- 각 행은
  - `parent_row_key`
  - `match_index`
  - `_kwic_prefix`
  - `_kwic_match`
  - `_kwic_suffix`
  를 가집니다.

즉 중앙 패널은 “라벨 원본 행”을 직접 보여주는 게 아니라, 필요하면 “매치 단위 표시행”으로 확장해서 보여줍니다.

### 치환 후

치환 성공 행은 다음 필드가 갱신됩니다.

- `flags_text`
- `value`
- `replace_applied`
- `replace_original_value`
- `tool_id = replace_tool`
- `tool_error_type`
- `tool_error_detail`

다만 `visible_source_rows()`는 확장된 표시행을 다시 parent 라벨 행 기준으로 deduplicate 해서 반환합니다.  
그래서 미리보기, 확인 필요 체크, 치환 대상 추출은 “표시는 매치 단위, 실제 처리 대상은 라벨 단위”로 동작합니다.

## 필터 및 상단 검색바 작동 방식

중앙 패널 상단에는 `도서`, `라벨`, `검색어`, `확인 필요 체크`, `확인 필요 초기화`, `검색`이 있습니다.

### 검색바

- 대상: 현재 테이블에 보이는 모든 표시 텍스트
- 방식:
  - `도서명`, `페이지`, `라벨 ID`, `라벨`, `값`, `비고`를 이어 붙여
  - 소문자 기준 부분 문자열 검색
- 특징:
  - 정규식 검색이 아니라 단순 포함 검색
  - 필드 필터와 함께 적용

### 필드 필터

- `도서`
  - 현재 조건을 만족하는 행의 도서값
- `라벨`
  - 현재 조건을 만족하는 행의 라벨값
- `검색어`
  - 현재 조건을 만족하는 행의 detail filter 값

주의할 점:

- 버튼 이름은 `검색어`로 고정돼 있지만,
- 실제 값 목록은 현재 결과에 들어 있는 매치 문자열 또는 검출 문자값입니다.
- 특수문자 분석일 때는 개행/탭/공백을 `\n`, `\t`, `<space>`로 변환해 보여줍니다.

필터 목록은 다른 필터를 이미 통과한 행들에서 다시 계산됩니다.  
즉 하나를 고르면 나머지 필터 후보도 함께 줄어듭니다.

## 확인 필요 체크 및 초기화

### 공통 원칙

- 대상 범위: `현재 필터 결과`
- 실제 저장 대상:
  - `shape_index >= 0`인 실제 라벨 행만 대상
  - `base_state`가 오류인 행만 `확인 필요 체크` 대상
- 사유 형식:
  - `[YYYY-MM-DD HH:MM:SS] 사유`

확장된 KWIC 표시행이 여러 개 보이더라도, 내부적으로는 parent 라벨 행으로 deduplicate 한 뒤 저장합니다.

### 확인 필요 체크

- 현재 필터 결과 중 오류 라벨을 골라 `is_problem`, `problem_reason`을 최신 S3 JSON에 저장합니다.
- 완료 로그 예시:
  - `확인 필요 체크 완료: 범위=현재 필터 결과 / 수정 페이지 N건 / 대상 행 M건`

### 초기화

- `현재 필터 결과 초기화`
- `검수 도서 전체 초기화`
- `특정 problem_reason 항목 초기화`

각 흐름은 `problem_reason` 줄 단위 제거 또는 전체 제거로 동작합니다.

### S3 최신본과 스냅샷 비교

`확인 필요 체크`, `현재 필터 결과 초기화`, `특정 reason 초기화`는 저장 전 최신 S3 JSON을 다시 읽고, 조회 시점 스냅샷과 비교합니다.

- 비교 시 제외 필드:
  - `is_problem`
  - `problem_reason`
- 불일치가 있으면:
  - 해당 페이지는 `mismatch_pages`로 분류
  - 현재 작업을 중단
  - 경고 메시지:
    - `스냅샷과 다른 JSON이 N건 감지되어 작업을 진행하지 않습니다.`

`검수 도서 전체 초기화`는 전체 정리 성격이라 스냅샷 일치를 강제하지 않고 진행합니다.

### 저장 제외/중단 사유

운영 중 자주 보게 되는 사유는 아래와 같습니다.

- `최신 S3 JSON 로드 실패`
- `JSON 정보 없음`
- `최신 JSON 정보 이상`
- `스냅샷 JSON 없음`
- `JSON shapes 구조 이상`
- `스냅샷 불일치`
- `확인 필요 저장 실패`

## 미리보기 영역

오른쪽 미리보기는 현재 선택한 라벨 행의 페이지를 기준으로 동작합니다.

- 이미지
  - 현재 페이지와 매칭되는 이미지 파일을 캐시에서 로드
- 박스
  - 같은 페이지에 속한 모든 라벨 행의 bbox를 그립니다.
- 강조 방식
  - 현재 선택한 `row_key`와 같은 행의 bbox만 강조
  - 나머지는 tone-down
- 값 툴팁
  - 중앙 패널 `값` 컬럼은 화면에는 KWIC를 보여주지만
  - hover 시에는 원문 전체 `flags_text`를 보여줍니다.

즉 사용자는 짧은 문맥으로 테이블을 보고, 필요하면 hover와 미리보기로 원문과 위치를 확인하는 구조입니다.

## 통계 영역

오른쪽 `통계` 탭은 현재 활성 도구 기준으로 다시 계산됩니다.

### 개요

- 전체 도서 수
- 검출율(페이지)
- 검출율(라벨)

### 검출문자 통계

- 현재 도구가 검출한 문자열/문자별 개수
- 비중
- 관련 페이지 수

### 도서별 검출문자 통계

- 도서별 검출 페이지 비율 분포
- 도서별 검출 페이지 수 / 검출 수 표

특이점:

- 현재 활성 도구가 `replace_tool`이면, 통계는 치환 자체가 아니라 마지막 검색 컨텍스트를 기준으로 다시 계산합니다.
- 즉 치환 후에도 오른쪽 통계는 “무엇을 찾았는가”를 기준으로 보는 쪽에 가깝습니다.

## 유지보수 포인트

- 새로운 텍스트 규칙은 가능하면 `tools/` 아래 도구 단위로 추가합니다.
- 검색/특수문자 분석 성능은 `scan_worker.py`의 chunk 크기와 `resolve_parallel_workers()` 영향을 많이 받습니다.
- 치환은 병렬화보다 안전성이 우선이므로, 저장 로직을 바꿀 때는 최신본 비교와 사후 검증을 먼저 유지해야 합니다.
- 중앙 패널이 확장 행(KWIC 표시행)을 쓰고 있다는 점을 놓치면, 필터/미리보기/확인 필요 저장이 왜 parent row 기준으로 동작하는지 이해하기 어렵습니다.
- detail 필터 값은 단순 `tool_error_detail` 문자열이 아니라, 도구별로 별도 가공된 `detail_filter_values`를 우선 사용합니다.
