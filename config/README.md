# config

실행 설정 템플릿과 로컬 설정 파일을 두는 폴더입니다.

## 파일 구성

- `default.yaml.example`: Git에 추적되는 기준 설정 템플릿
- `default.yaml`: 로컬 전용 실행 설정 파일, Git 제외
- `.gitignore`: 로컬 설정 파일 제외 규칙

## 설정 로딩 원칙

- 기준 파일은 항상 `default.yaml.example`입니다.
- 로컬 설정은 `default.yaml`에만 둡니다.
- 코드에서는 `ConfigManager`를 통해 설정을 읽습니다.
- `default.yaml`이 없으면 현재 로더가 `default.yaml.example`을 복사해서 사용합니다.

## 현재 기준 설정 구조

### `project`

- `id`: 프로젝트 식별자
- `s3_path`: 기본 S3 경로
- `output_path`: 산출물 저장 경로
- `cache_path`: 캐시 저장 경로

### `aws`

- `access_key`
- `secret_key`
- `session_token`
- `region`
- `default_bucket`
- `default_prefix`

민감한 값은 `default.yaml`에만 두고 커밋하지 않습니다.

### `checks`

현재 예시 템플릿에는 `noise_char_check.banned_chars`처럼 공통 검사 옵션이 들어 있습니다. 새 공통 설정을 추가할 때는 example 파일과 이 README를 함께 갱신하는 편이 좋습니다.

## 관련 코드

- `app/common/config/config_manager.py`
- `app/common/config/parallel_settings.py`
- `config/default.yaml.example`