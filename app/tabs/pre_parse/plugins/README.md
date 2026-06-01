# pre_parse/plugins

파싱 전 검사 탭에서 실제로 로드되는 페이지 단위 검사 플러그인 모음입니다.

## 실제 로딩/실행 규칙

- 로더는 `app/tabs/pre_parse/plugins/*.py` 중 파일명이 `_`로 시작하지 않는 파일만 등록합니다.
- 런타임 `check_id`는 로더가 파일 stem으로 덮어씁니다. 파일명을 바꾸면 옵션 저장 키와 결과 식별자도 함께 바뀝니다.
- `TAG` 값은 현재 UI의 배지와 정렬 순서에만 사용됩니다. `필수`/`선택` 모두 사용자가 직접 선택해서 실행합니다.
- 현재 좌측 패널 구현상 검사 플러그인은 한 번에 1개만 선택할 수 있습니다.
- 플러그인 실행 중 예외가 발생하면 런너가 `PLUGIN_RUNTIME_ERROR` 이슈를 `shape_index = -1`로 생성합니다.

## 플러그인 작성 공통 규칙

- shape 순회는 `app/tabs/pre_parse/plugin_system/shape_utils.py`의 `iter_shape_dicts()` 기준으로 통일합니다. 즉, `json_data["shapes"]`가 리스트일 때만 검사하고, 각 원소 중 `dict`인 shape만 실제 검사 대상으로 사용합니다.
- bbox 기반 검사는 `get_shape_bbox()` 기준으로 통일합니다. `points`에서 숫자로 해석되는 좌표쌍만 수집하고, 유효 좌표가 2개 이상이며 min/max bbox의 너비와 높이가 모두 0보다 큰 경우에만 bbox를 생성합니다.
- 텍스트 기반 검사는 `flags.text`를 기준으로 통일합니다. 원본 텍스트가 필요할 때는 공용 helper `get_shape_flags_text()`를 우선 사용합니다.
- 라벨 기반 선택 옵션은 값을 직접 하드코딩하지 않고, 저장소 루트 `label/` 폴더의 정의 파일을 참조해 구성합니다.
- 플러그인을 수정할 때는 카드의 `i` 툴팁에 표시되는 `DESCRIPTION`과 이 README의 해당 항목을 같은 커밋에서 함께 갱신합니다.
- 새 bbox 기반 플러그인을 만들 때는 파일별로 별도 shape 유효성 함수를 다시 만들기보다 공용 helper를 우선 사용합니다.

## 현재 로드되는 플러그인 목록

### 필수 태그

<table width="1280">
  <thead>
    <tr>
      <th width="320">파일명</th>
      <th width="460">검사 요약</th>
      <th width="170">옵션</th>
      <th width="330">주요 issue_code</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td width="320"><nobr><code>[BBOX] 캡션 검사.py</code></nobr></td>
      <td width="460"><code>CAPTION</code> 부모 존재 여부와 부모별 <code>CAPTION</code> 개수 검사</td>
      <td width="170">없음</td>
      <td width="330"><code>CAPTION_PARENT_MISSING</code>, <code>MULTIPLE_CAPTIONS_IN_PARENT</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[BBOX] 타이틀 중복 검사.py</code></nobr></td>
      <td width="460">같은 페이지 안의 <code>TITLE</code> 개수 검사</td>
      <td width="170">없음</td>
      <td width="330"><code>DUPLICATE_TITLE_IN_PAGE</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[BBOX] 포함 관계 검사.py</code></nobr></td>
      <td width="460">직접 부모-자식 bbox 포함 관계 검사</td>
      <td width="170">없음</td>
      <td width="330"><code>SUSPECT_INCLUDED_RELATION_*</code>, <code>UNDEFINED_INCLUDED_RELATION_*</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[OCR] 노이즈 문자 검사.py</code></nobr></td>
      <td width="460"><code>flags.text</code>의 노이즈 유니코드 그룹 검사</td>
      <td width="170"><code>enable_extended_groups</code></td>
      <td width="330"><code>NOISE_*</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[OCR] 빈 라벨 값 검사.py</code></nobr></td>
      <td width="460">선택 라벨의 <code>flags.text</code> 공백 여부 검사</td>
      <td width="170"><code>target_labels</code></td>
      <td width="330"><code>EMPTY_LABEL</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[OCR] 태그 수 일치 검사.py</code></nobr></td>
      <td width="460">부모 텍스트 태그와 포함된 인라인 박스 수 비교</td>
      <td width="170">없음</td>
      <td width="330"><code>INLINE_BOX_TAG_COUNT_MISMATCH</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[수식표] 수식 환경 매칭 검사.py</code></nobr></td>
      <td width="460"><code>FORMULA</code> 내부 LaTeX 수식 환경 짝 검사</td>
      <td width="170">없음</td>
      <td width="330"><code>LATEX_ENV_NOT_ALLOWED</code>, <code>LATEX_EQUATION_*</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[수식표] 표 환경 매칭 검사.py</code></nobr></td>
      <td width="460"><code>TABLE</code> 내부 <code>tabular</code> 또는 HTML table 구조 검사</td>
      <td width="170"><code>matching_check_type</code></td>
      <td width="330"><code>TABLE_ENV_*</code>, <code>TABLE_HTML_*</code></td>
    </tr>
  </tbody>
</table>

### 선택 태그

<table width="1280">
  <thead>
    <tr>
      <th width="320">파일명</th>
      <th width="460">검사 요약</th>
      <th width="170">옵션</th>
      <th width="330">주요 issue_code</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td width="320"><nobr><code>[BBOX] 겹침 검사.py</code></nobr></td>
      <td width="460">bbox 교집합 비율 기반 겹침 검사</td>
      <td width="170"><code>overlap_min_threshold</code>, <code>overlap_max_threshold</code></td>
      <td width="330"><code>BBOX_OVERLAP_RATIO</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[BBOX] 빈 페이지 검사.py</code></nobr></td>
      <td width="460"><code>shapes == []</code> 인 페이지 검사</td>
      <td width="170">없음</td>
      <td width="330"><code>PAGESHAPE_EMPTY</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[BBOX] 오생성 박스 검사.py</code></nobr></td>
      <td width="460">작은 박스와 페이지 밖 박스 검사</td>
      <td width="170"><code>min_box_area_px2</code>, <code>outside_mode</code></td>
      <td width="330"><code>SMALL_BOX</code>, <code>BOX_OUT_OF_PAGE</code>, <code>IMAGE_SIZE_MISSING</code></td>
    </tr>
    <tr>
      <td width="320"><nobr><code>[편의성] 확인 필요 라벨 검사.py</code></nobr></td>
      <td width="460"><code>is_problem</code> 이 true인 shape 재검출</td>
      <td width="170">없음</td>
      <td width="330"><code>IS_PROBLEM_LABEL</code></td>
    </tr>
  </tbody>
</table>

### 런타임 제외 참고 파일

| 파일명 | 설명 |
| --- | --- |
| `_template_check.py` | 새 플러그인 작성용 참고 템플릿입니다. 파일명이 `_`로 시작하므로 현재 로더는 등록하지 않습니다. |

## 플러그인 상세 명세

### `[BBOX] 캡션 검사.py`

- 옵션: 없음.
- 검사 대상: `label == CAPTION`인 shape와, 같은 페이지의 비-`CAPTION` bbox 기반 shape 전체를 부모 후보로 사용합니다.
- FAIL 반환: 아래 issue가 1건 이상 생성되면 `FAIL`, 없으면 `PASS`를 반환합니다.
- FAIL 조건: `CAPTION`을 완전히 포함하는 부모 후보가 하나도 없으면 해당 캡션 shape에 `CAPTION_PARENT_MISSING` / `CAPTION 부모 박스 누락` / `CAPTION을 포함하는 부모 박스 누락`을 추가합니다.
- FAIL 조건: 같은 부모 shape 안에 들어가는 `CAPTION` 수가 `MAX_CAPTION_PER_PARENT = 1`을 초과하면 부모 shape에 `MULTIPLE_CAPTIONS_IN_PARENT` / `부모 박스 내 CAPTION 중복` / `"{PARENT_LABEL} 박스 내부 CAPTION {N}개 존재"`를 추가합니다.

### `[BBOX] 타이틀 중복 검사.py`

- 옵션: 없음.
- 검사 대상: 페이지의 모든 shape 중 `label.upper() == "TITLE"`인 shape입니다.
- FAIL 반환: 같은 페이지의 `TITLE`이 2개 이상이면 `FAIL`, 아니면 `PASS`를 반환합니다.
- FAIL 조건: `TITLE`이 2개 이상이면 모든 `TITLE` shape에 `DUPLICATE_TITLE_IN_PAGE` / `"페이지 내 TITLE {COUNT}개"` / `"페이지 내 TITLE {COUNT}개 존재"`를 추가합니다.

### `[BBOX] 포함 관계 검사.py`

- 옵션: 없음.
- 검사 대상: bbox를 만들 수 있는 모든 shape입니다. 부모-자식 판정은 "자식을 포함하는 부모 후보 중 면적이 가장 작은 bbox"를 직접 부모로 선택하는 방식입니다.
- 부모-자식 허용 규칙은 아래 표를 사용합니다.

| 부모 라벨 | 정상 허용 자식 | 의심 자식 |
| --- | --- | --- |
| `TEXT` | `IMAGE`, `FORMULA`, `TABLE`, `CHART` | `ITEM` |
| `TITLE` | `IMAGE`, `FORMULA`, `TABLE`, `CHART` | `ITEM` |
| `CAPTION` | `IMAGE`, `FORMULA` | `TABLE`, `CHART`, `ITEM` |
| `IMAGE` | `CAPTION` | 없음 |
| `FORMULA` | 없음 | 없음 |
| `TABLE` | `CAPTION`, `IMAGE`, `CHART`, `ITEM` | 없음 |
| `CHART` | `CAPTION` | 없음 |
| `ITEM` | `TEXT`, `CAPTION`, `IMAGE`, `FORMULA`, `TABLE`, `CHART` | 없음 |
| `FOOTNOTE` | `IMAGE`, `FORMULA`, `TABLE`, `CHART`, `ITEM` | 없음 |

- FAIL 반환: 직접 부모-자식 쌍에서 허용되지 않은 관계가 1건 이상 나오면 `FAIL`, 아니면 `PASS`를 반환합니다.
- 상세 로직: 박스 간의 부모자식 관계는 포함 관계를 기준으로, 다단계 포함 관계는 재귀적으로 검사합니다. 각 단계의 부모-자식은 해당 자식을 포함하는 후보 부모 중 면적이 가장 작은 박스를 직접 부모로 선택합니다.
- FAIL 조건: 자식 라벨이 `의심 자식`에 있으면 부모 shape에 `SUSPECT_INCLUDED_RELATION_<PARENT_LABEL>` / `오류 의심 포함관계` / `"{PARENT_LABEL} 박스 안에 {CHILD_LABEL} 라벨이 포함 (오류 의심 포함관계이므로 확인 필요)"`를 추가합니다.
- FAIL 조건: 자식 라벨이 `정상 허용 자식`과 `의심 자식` 어디에도 없으면 부모 shape에 `UNDEFINED_INCLUDED_RELATION_<PARENT_LABEL>` / `"허용되지 않은 포함관계 부모 라벨: {PARENT_LABEL}"` / `"{PARENT_LABEL} 내부 {CHILD_LABEL} 포함 불가"`를 추가합니다.
### `[BBOX] 겹침 검사.py`

- 옵션: `overlap_min_threshold`, `overlap_max_threshold`는 겹침 비율 구간의 하한/상한값이며 기본값은 각각 `0.80`, `1.00`입니다. 숫자 파싱 실패 시 기본값을 사용하고, 최종값은 `0.0 ~ 1.0` 범위로 보정합니다.
- 옵션: 판정 구간은 기본적으로 `하한값 이상, 상한값 미만`입니다. 단, `overlap_max_threshold`에 `1 초과` 값을 입력한 경우에는 `하한값 이상, 1.00 이하`로 검사합니다. 상한값이 하한값보다 작거나, 상한값과 하한값이 같으면서 상한 포함 조건이 성립하지 않으면 기본 구간 `0.80 이상 1.00 미만`으로 되돌립니다.
- 검사 대상: `TEXT`, `FORMULA`, `TABLE`, `FOOTNOTE`, `IMAGE`, `CHART`, `TITLE` 라벨의 bbox 기반 shape입니다.
- FAIL 반환: shape 쌍 중 하나라도 겹침 조건을 만족하는 쌍이 있으면 `FAIL`, 없으면 `PASS`를 반환합니다.
- 상세 로직: 두 bbox의 교집합 면적이 0보다 크면 `inter / area1`, `inter / area2` 두 비율을 계산합니다.
- 상세 로직: 오류 유형 그룹화에는 판정 구간을 만족한 비율 중 큰 값을 사용하고, 0.01 단위 반올림 값으로 묶습니다.
- FAIL 조건: 두 비율 중 하나라도 판정 구간에 들어오면 두 shape 모두에 `BBOX_OVERLAP_RATIO` / `겹침 수치 {score:.2f}` / `"({LABEL1}/{LABEL2}) 겹침 수치 {score:.2f}"`를 추가합니다.

### `[BBOX] 빈 페이지 검사.py`

- 옵션: 없음.
- 검사 대상: 개별 shape가 아니라 페이지 전체의 `json_data["shapes"]` 값입니다.
- FAIL 반환: `json_data["shapes"]` 값이 정확히 `[]`이면 `FAIL`, 그 외에는 `PASS`를 반환합니다.
- FAIL 조건: 페이지 단위 오류로 `shape_index = -1`에 `PAGESHAPE_EMPTY` / `빈 페이지` / `페이지의 shapes 비어 있음`을 추가합니다.

### `[BBOX] 오생성 박스 검사.py`

- 옵션: `min_box_area_px2`는 면적 기준이며 기본값은 `150`입니다. 빈 값이거나 숫자 변환에 실패하면 기본값을 사용하고, 음수는 `0`으로 보정합니다.
- 옵션: `outside_mode`는 판정 방식입니다. 기본값은 `일부 면적이라도 페이지 외부에 존재`이며, `전체 면적이 페이지 외부에 존재`로 바꿀 수 있습니다.
- 검사 대상: 모든 shape의 `points`와 페이지 메타데이터 `imageWidth`, `imageHeight`입니다.
- FAIL 반환: `SMALL_BOX`, `BOX_OUT_OF_PAGE`, `IMAGE_SIZE_MISSING` 중 하나라도 1건 이상 생성되면 `FAIL`, 없으면 `PASS`를 반환합니다.
- 상세 로직: 각 shape의 좌표들로 bbox를 만들고 면적을 계산합니다. 작은 박스로 먼저 판정된 shape는 페이지 밖 검사로 넘기지 않습니다.
- 상세 로직: 페이지 밖 면적은 `bbox 전체 면적 - 페이지 내부 교집합 면적`으로 계산합니다.
- FAIL 조건: `imageWidth <= 0` 또는 `imageHeight <= 0`이면 페이지 단위 오류로 `shape_index = -1`에 `IMAGE_SIZE_MISSING` / `페이지 크기 정보 누락` / `"imageWidth, imageHeight 정보 존재하지 않음"`을 추가합니다.
- FAIL 조건: bbox 면적이 `min_box_area_px2` 이하이면 해당 shape에 `SMALL_BOX` / `작은 박스 오류` / `"{LABEL} 박스 면적 기준 이하 ({AREA:.2f}px²)"`를 추가합니다.
- FAIL 조건: `imageWidth > 0`이고 `imageHeight > 0`일 때, `outside_mode = 일부 면적이라도 페이지 외부에 존재`이면 페이지 밖 면적이 0보다 크면 `BOX_OUT_OF_PAGE` / `페이지 밖 박스 오류` / `"{LABEL} 박스 페이지 범위 벗어남 ({OUTSIDE_AREA:.2f}px²/{AREA:.2f}px²)"`를 추가합니다.
- FAIL 조건: `outside_mode = 전체 면적이 페이지 외부에 존재`이면 페이지 내부 교집합 면적이 0일 때만 `BOX_OUT_OF_PAGE` / `페이지 밖 박스 오류` / `"{LABEL} 박스 페이지 범위 벗어남 ({OUTSIDE_AREA:.2f}px²/{AREA:.2f}px²)"`를 추가합니다.

### `[OCR] 노이즈 문자 검사.py`

- 옵션: `enable_extended_groups`는 확장 검사 여부입니다. 기본값은 `false`이며, 이때는 삭제 권장 대상인 `제어 및 비가시`, `품질 이상`만 검사합니다. `true`로 체크하면 나머지 노이즈 그룹도 함께 검사합니다.
- 검사 대상: `TEXT`, `FOOTNOTE`, `TITLE`, `CAPTION` 라벨입니다. 텍스트 소스는 `flags.text`입니다.
- 기본 검사 그룹: `제어 및 비가시`, `품질 이상`
- 확장 검사 추가 그룹: `공백 및 줄바꿈`, `사적 영역`, `구두점 및 인용 부호`, `전각`, `단위 및 기호`, `한글 자모`, `괄호 및 원문자`, `스타일 문자`
- 노이즈 그룹은 아래 표를 따릅니다.

| **그룹** | **검출 범위** | **권장 처리 방법** |
| --- | --- | --- |
| 공백 및 줄바꿈 | • 공백: <code>[\u0009\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]</code><br>• 줄바꿈: <code>[\u000B-\u000D\u001C-\u001E\u0085\u2028\u2029]</code> | 치환 |
| 제어 및 비가시 | <code>[\u0000-\u0008\u000E-\u001B\u001F\u007F\u0080-\u0084\u0086-\u009F\u00AD\u034F\u061C\u115F-\u1160\u180B-\u180F\u200B-\u200F\u202A-\u202E\u2060-\u206F\u3164\uFEFF]</code> | 삭제 |
| 품질 이상 | <code>\uFFFD</code> | 삭제 |
| 사적 영역 | <code>[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]</code> | 검색 후 수기 검수 진행 |
| 구두점 및 인용 부호 | • <code>“</code> : <code>[\u201C-\u201F]</code><br>• <code>’</code> : <code>[\u2018-\u201B]</code><br>• <code>-</code> : <code>[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]</code><br>• <code>·</code> : <code>[\u00B7\u2022\u2027\u2219\u22C5]</code><br>• <code>~</code> : <code>[\u007E\u02DC\u2053\u223C\u301C\uFF5E]</code> | 치환 |
| 전각 | <code>[\uFF01-\uFF5E]</code> | 정규화(NFKC) |
| 단위 및 기호 | <code>[\u2100-\u214F\u3300-\u33FF]</code> | 정규화(NFKC) |
| 한글 자모 | <code>[\u1100-\u11FF]</code> | 정규화(NFKC) |
| 괄호 및 원문자 | • 괄호 문자: <code>[\u2474-\u2487\u3200-\u321B]</code><br>• 원 문자: <code>[\u2460-\u2473\u24B6-\u24CF\u24D0-\u24E9\u3260-\u326D]</code><br>• 점 문자: <code>[\u2488-\u249B]</code> | 괄호문자, 점문자: 정규화(NFKC)<br>원문자: 검색 후 수기 검수 진행 |
| 스타일 문자 | <code>[\U0001D400-\U0001D7FF]</code><br>• 볼드체, 이탤릭체, 고딕체, 고정폭 문자(모노스페이스) 포함<br>• 이외 <code>ℤ</code>, <code>ℝ</code>, <code>ℂ</code>, <code>ℕ</code>, <code>ℚ</code> 와 같은 수학 분야 의미 변화 존재할 수 있는 스타일 문자 범위는 제외 | 정규화(NFKC) |
| URL, 이메일 등 그 외 문자열 패턴 | - | 현재 노이즈 문자 검사 플러그인에서 직접 검출하지 않음. 특수문자 분석 기능 등 활용해 검출, 고객사 요청에 맞춰 개별 처리 |

- FAIL 반환: 현재 활성화된 노이즈 그룹 중 매칭이 1건 이상 발생하면 `FAIL`, 없으면 `PASS`를 반환합니다.
- 그룹별 issue_code 매핑: `공백 및 줄바꿈 -> NOISE_WHITESPACE_LINEBREAK`, `제어 및 비가시 -> NOISE_CONTROL_INVISIBLE`, `품질 이상 -> NOISE_REPLACEMENT_CHARACTER`, `사적 영역 -> NOISE_PRIVATE_USE_AREA`, `구두점 및 인용 부호 -> NOISE_PUNCTUATION_QUOTES`, `전각 -> NOISE_FULLWIDTH`, `단위 및 기호 -> NOISE_UNITS_SYMBOLS`, `한글 자모 -> NOISE_HANGUL_JAMO`, `괄호 및 원문자 -> NOISE_ENCLOSED_ALPHANUMERICS`, `스타일 문자 -> NOISE_STYLED_TEXT`
- 상세 로직: 한 shape 안에서 같은 그룹의 문자가 여러 개 매칭되어도 issue는 그룹당 1건만 생성합니다.
- FAIL 조건: 현재 활성화된 특정 그룹에서 매치가 1건 이상 나오면 해당 shape에 `issue_code = 위 매핑의 값`, `error_type = 그룹명`, `error_message = "매칭 패턴: {문맥1} | ... (ACTION 필요)"` 형식의 issue를 추가합니다.
- 상세 로직: 오류 메시지는 최대 5개의 문맥 스니펫만 표시하고, 6건 이상이면 `외 N건`을 덧붙입니다.

### `[OCR] 빈 라벨 값 검사.py`

- 옵션: `target_labels`는 `label/` 목록에서 선택한 라벨 값이며, 기본값은 빈 목록 `[]`입니다.
- 검사 대상: `target_labels`에 입력된 라벨의 shape입니다. 텍스트 값은 `flags.text`를 기준으로 검사합니다.
- FAIL 반환: 선택 라벨 중 빈 값이 1건 이상 있으면 `FAIL`, 없으면 `PASS`를 반환합니다.
- 상세 로직: 선택한 라벨이 하나도 없으면 검사 자체를 생략하고 `PASS`를 반환합니다.
- 상세 로직: `flags`가 dict가 아닌 shape는 건너뛰고, dict인 경우에만 `flags.text`를 검사합니다.
- FAIL 조건: `flags.text`가 빈 문자열이거나 공백뿐이면 해당 shape에 `EMPTY_LABEL` / `{LABEL}` / `"{LABEL} 라벨 flags.text 비어 있음"`을 추가합니다.

### `[OCR] 태그 수 일치 검사.py`

- 옵션: 없음.
- 검사 대상: 부모 박스는 `ITEM`을 제외한 bbox 기반 shape입니다. 자식 박스는 bbox 기반 shape를 사용합니다.
- 현재 유효 태그는 아래 표를 사용합니다.

| 자식 라벨 | 유효 태그 |
| --- | --- |
| `FORMULA` | `{fr}` |
| `IMAGE` | `{im}` |
| `TABLE` | `{tb}` |
| `CHART` | `{ch}` |
| `ITEM` | `{em}` |

- FAIL 반환: 아래 issue가 1건 이상 생성되면 `FAIL`, 없으면 `PASS`를 반환합니다.
- FAIL 조건: 각 라벨별 direct 자식 박스 수와 `flags.text` 내부 태그 수가 다르면 부모 shape에 `INLINE_BOX_TAG_COUNT_MISMATCH`를 추가합니다. `error_type`은 일치하지 않는 라벨의 type(`FORMULA`, `IMAGE`, `TABLE`, `CHART`, `ITEM`)입니다.
- FAIL 조건: `error_message`는 `"자식 아이템 박스: 2개, {em} 태그: 1개"` 형식으로 기록합니다.
- 상세 로직: 박스 간의 부모자식 관계는 포함 관계를 기준으로, 다단계 포함 관계는 재귀적으로 검사합니다. 각 단계의 부모-자식은 해당 자식을 포함하는 후보 부모 중 면적이 가장 작은 박스를 직접 부모로 선택합니다.
- 상세 로직: `ITEM` 라벨은 부모 검사 대상에서 제외합니다. 따라서 `ITEM > TABLE > CHART` 구조에서는 `ITEM`에 대해 `{tb}`를 검사하지 않고, `TABLE` 내부의 `{ch}`만 검사합니다.
- 상세 로직: 태그 수는 `flags.text`를 소문자로 변환한 뒤 `{fr}`, `{im}`, `{tb}`, `{ch}`, `{em}` 문자열 개수만 직접 셉니다. 다른 문자열 패턴은 별도 오류로 만들지 않습니다.

### `[수식표] 수식 환경 매칭 검사.py`

- 옵션: 없음.
- 검사 대상: `label == FORMULA`인 shape입니다. 텍스트 소스는 `flags.text`입니다.
- 상세 로직: 정규식 `(?<!\\)\\(begin|end)\{...\}`로 이스케이프되지 않은 LaTeX 환경 토큰만 읽습니다.
- 환경 판정 기준은 아래 표를 따릅니다.

| 구분 | 환경명 | 판정 |
| --- | --- | --- |
| 허용 환경 | `equation`, `align`, `align*`, `multline`, `gather` | stack 기반 짝 검사 진행 |
| 허용되지 않은 환경 | 위 5개 외 모든 `\begin{...}` / `\end{...}` 환경명 | `LATEX_ENV_NOT_ALLOWED` |

- FAIL 반환: 아래 issue가 1건 이상 생성되면 `FAIL`, 없으면 `PASS`를 반환합니다.
- FAIL 조건: 허용되지 않은 환경이 나오면 환경명마다 `LATEX_ENV_NOT_ALLOWED` / `허용되지 않은 수식 환경` / `"{ENV} 환경 허용 목록에 없음"`을 추가합니다.
- FAIL 조건: `\end{...}`가 먼저 나오면 `LATEX_EQUATION_START_MISSING` / `수식 환경 시작 누락` / `"{ENV} 환경 시작 없이 종료"`를 추가합니다.
- FAIL 조건: 스택 top의 시작 환경과 종료 환경 이름이 다르면 `LATEX_EQUATION_END_MISMATCH` / `수식 환경 종료 불일치` / `"{EXPECTED_ENV} 대신 {ENV} 먼저 종료"`를 추가합니다.
- FAIL 조건: begin만 있고 end가 없으면 남아 있는 환경마다 `LATEX_EQUATION_END_MISSING` / `수식 환경 종료 누락` / `"{ENV} 환경 종료 누락"`을 추가합니다.

### `[수식표] 표 환경 매칭 검사.py`

- 옵션: `matching_check_type`은 검사 기준 포맷을 선택하는 값이며 `TABLE HTML`, `TABLE LATEX` 중 하나를 받습니다. 기본값은 `TABLE HTML`이고, 잘못된 값은 `TABLE HTML`로 보정합니다.
- 검사 대상: `label == TABLE`인 shape입니다. 실제 검사 문자열은 `flags.text`만 사용합니다.
- FAIL 반환: 선택한 모드에서 issue가 1건 이상 생성되면 `FAIL`, 없으면 `PASS`를 반환합니다.
- 상세 로직: `flags`가 빈 dict면 선택한 모드에 따라 즉시 누락 오류를 만듭니다. `flags`가 dict가 아닌 경우는 현재 구현에서 건너뜁니다.
- `TABLE LATEX` 모드 FAIL 조건:
- `TABLE_ENV_ESCAPED`: `\\begin{tabular}` 또는 `\\end{tabular}` 이스케이프 형태가 있으면 `tabular 환경 이스케이프 오류` / `tabular 환경 이스케이프 형태 포함`
- `TABLE_ENV_MISSING`: 유효한 `\begin{tabular}` / `\end{tabular}` 토큰이 전혀 없고 HTML `<table>`도 없으면 `TABLE 환경 누락` / `tabular 환경 누락`
- `TABLE_ENV_START_INVALID`: `\begin{tabular}`가 문자열 맨 앞이 아니거나, end가 먼저 나와 시작이 없으면 `tabular 시작 환경 오류`
- `TABLE_ENV_END_INVALID`: `\end{tabular}`가 문자열 맨 끝이 아니거나, stack에 남은 환경이 있으면 `tabular 종료 환경 오류`
- `TABLE_ENV_SYNTAX_ERROR`: stack top의 시작 환경과 종료 환경 이름이 다르면 `tabular 환경 문법 오류`
- `TABLE HTML` 모드 FAIL 조건:
- `TABLE_HTML_ENV_MISSING`: HTML 토큰도 없고 `tabular` 토큰도 없으면 `HTML TABLE 환경 누락` / `HTML table 태그 누락`
- `TABLE_HTML_START_INVALID`: `<table`이 문자열 맨 앞이 아니거나, end 태그가 먼저 나와 시작 태그가 없으면 `HTML table 시작 태그 오류`
- `TABLE_HTML_END_INVALID`: `</table>`이 문자열 맨 끝이 아니거나, stack에 남은 태그가 있으면 `HTML table 종료 태그 오류`
- `TABLE_HTML_SYNTAX_ERROR`: stack top의 시작 태그와 종료 태그 이름이 다르면 `HTML 태그 문법 오류`
- 상세 로직: `TABLE LATEX` 모드에서는 `env_stack`으로 `\begin{...}` / `\end{...}` 짝을 검사합니다.
- 상세 로직: `TABLE HTML` 모드에서는 `html_stack`으로 `table`, `tr`, `td`, `th`, `caption`, `tfoot` 시작/종료 태그 짝을 검사합니다.
- 상세 로직: 현재 구현은 선택한 모드의 구조를 우선 검사하되, 반대 포맷 토큰이 있으면 "환경 자체 누락" 오류는 내지 않습니다.

### `[편의성] 확인 필요 라벨 검사.py`

- 옵션: 없음.
- 검사 대상: 모든 shape의 `is_problem`과 `problem_reason` 값입니다.
- 상세 로직: `is_problem`은 bool이면 그대로, 문자열이면 `true`, 숫자면 `0`이 아닌 값을 참으로 해석합니다.
- FAIL 반환: `is_problem`이 참인 shape가 1건 이상 있으면 `FAIL`, 없으면 `PASS`를 반환합니다.
- FAIL 조건: `is_problem`이 참이면 해당 shape에 `IS_PROBLEM_LABEL` / `{problem_reason 또는 \u200b}` / `{problem_reason 또는 \u200b}`를 추가합니다.
- 상세 로직: `problem_reason`이 비어 있으면 빈 문자열 대신 zero-width space(`\u200b`)를 오류 메시지로 사용합니다.

## 관련 문서

- [pre_parse/README.md](../README.md)
- [plugin_system/README.md](../plugin_system/README.md)
