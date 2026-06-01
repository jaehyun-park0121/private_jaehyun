# data-team2-base

data-team2-base (중앙화 코드)는 정제 과정에서 반복적으로 수행되는 검수 로직을 재사용 가능한 코드 형태로 중앙 관리하기 위한 레포지토리입니다.

이 레포지토리는 다음 목적을 가지고 운영합니다.

- 정제 과정에서 반복적으로 수행되는 검수 로직을 재사용 가능한 코드 형태로 도구화해 중앙 관리함으로써,
- 구성원의 코드 작성 부담을 낮추고,
- 기본적인 품질 관리를 일관되고 안정적으로 수행할 수 있도록 하는 것을 목표로 합니다.

## 빠른 시작

권장 Python 버전: `3.14.3`

1. 가장 간단한 방법: 루트의 `run_app.bat`를 실행합니다.
   필요 시 `.venv`를 만들고 `requirements.txt`를 자동 설치/동기화한 뒤 `main.py`를 실행합니다.
2. 수동 실행이 필요하면 아래 순서로 진행합니다.
   `pip install -r requirements.txt`
   `python main.py`

## 폴더 구조 개요

| 경로 | 설명 |
| --- | --- |
| `app/` | 메인 UI, 공통 코드, 탭별 기능 코드 |
| `config/` | 실행 설정 템플릿과 로컬 설정 파일 위치 |
| `docs/` | 유지보수 시 참고할 통일성 정보와 샘플 자료 |
| `label/` | 프로그램에서 참조하는 라벨 기준표(`*.xlsx`) 위치 |
| `.cache/` | 캐시 파일 위치, Git 제외 |
| `outputs/` | 산출물 위치, Git 제외 |
| `main.py` | 앱 실행 진입점 |
| `requirements.txt` | Python 의존성 목록 |

## README 구조

```text
data-team2-base/
├─ README.md
├─ app/
│  ├─ README.md
│  ├─ common/
│  │  └─ README.md
│  └─ tabs/
│     ├─ README.md
│     ├─ misc_tools/
│     │  ├─ README.md
│     │  └─ apps/
│     │     ├─ README.md
│     │     ├─ parse/README.md
│     ├─ pre_parse/
│     │  ├─ README.md
│     │  ├─ plugin_system/README.md
│     │  └─ plugins/README.md
│     ├─ raw_data_analysis/
│     │  └─ README.md
│     └─ text_analysis/
│        └─ README.md
├─ config/
│  └─ README.md
├─ docs/
│  └─ README.md
└─ label/
   └─ README.md
```

## 주요 문서 개요

### `app/` 개요

- [app/README.md](./app/README.md): 앱 폴더 전체 역할과 `common/`, `tabs/`의 구분 기준

### `app/common/`

- [app/common/README.md](./app/common/README.md): 여러 탭에서 재사용하는 공통 코드의 역할 설명

### `app/tabs/` 공통

- [app/tabs/README.md](./app/tabs/README.md): 현재 탭 목록과 새 탭 구성 원칙

#### `misc_tools`

- [app/tabs/misc_tools/README.md](./app/tabs/misc_tools/README.md): 기타 도구 탭 구조와 새 앱 추가 방법
- [app/tabs/misc_tools/apps/README.md](./app/tabs/misc_tools/apps/README.md): 현재 앱 목록과 앱별 대표 README 링크
- [app/tabs/misc_tools/apps/parse/README.md](./app/tabs/misc_tools/apps/parse/README.md): 문서 파서 앱의 실행 흐름, 설정 구조, 핵심 파싱 규칙

#### `pre_parse`

- [app/tabs/pre_parse/README.md](./app/tabs/pre_parse/README.md): 파싱 전 검사 탭 구조와 실행 흐름
- [app/tabs/pre_parse/plugin_system/README.md](./app/tabs/pre_parse/plugin_system/README.md): 플러그인 작성 방법과 실행 계약
- [app/tabs/pre_parse/plugins/README.md](./app/tabs/pre_parse/plugins/README.md): 현재 플러그인 목록과 기능 설명

#### `raw_data_analysis`

- [app/tabs/raw_data_analysis/README.md](./app/tabs/raw_data_analysis/README.md): 원시 데이터 분석 탭 구조와 결과표 컬럼 기준

#### `text_analysis`

- [app/tabs/text_analysis/README.md](./app/tabs/text_analysis/README.md): 텍스트 분석 탭 구조와 도구 운영 방식

### `config/`

- [config/README.md](./config/README.md): `default.yaml.example` 기준 설정 구조와 로컬 설정 원칙

### `docs/`

- [docs/README.md](./docs/README.md): 유지보수 시 따라갈 공통 스타일, 문서 작성 방식, `.gitignore` 관리 방식, 샘플 자료 안내

### `label/`

- [label/README.md](./label/README.md): `label/*.xlsx` 기준표 형식과 사용 원칙

## 현재 메인 탭

- 기타 도구(misc_tools)
- 파싱 전 검사(pre_parse)
- 원시 데이터 분석(raw_data_analysis)
- 텍스트 분석(text_analysis)

## Git 산출물 정리 원칙

- `config/default.yaml` 같은 로컬 설정 파일은 커밋하지 않습니다.
- OAuth client secret, credential, 사용자 인증 토큰 등 민감 정보는 로컬 파일로만 관리합니다.
- 실행 중 생성되는 캐시와 산출물은 `.cache/`, `outputs/` 아래에서 관리합니다.
