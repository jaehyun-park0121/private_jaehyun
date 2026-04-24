# Crawling Pipeline Harness Engineering Context

이 문서는 `Crawling Code_refactor` 디렉토리에 구축된 크롤링 파이프라인을 외부 시스템(Harness, CI/CD, 데이터 파이프라인 스케줄러 등)과 연동하고 자동화하기 위한 공식 가이드 및 컨텍스트입니다.

## 1. 개요 (Architecture & Entrypoint)
기존의 GUI 중심 거대 스크립트가 기능별 단위 모듈(`core/`, `shared/`, `utils/`)로 완전 분리되었습니다. 
Harness 엔지니어링 및 파이프라인 자동화의 핵심 진입점(Entrypoint)은 **`cli.py`** 입니다. 외부 시스템은 `main.py`(GUI)를 우회하여 `cli.py`를 호출함으로써 크롤링을 헤드리스(Headless) 및 자동화 방식으로 구동할 수 있습니다.

### 실행 커맨드 예시
```bash
python cli.py --url "https://target-site.com" --max-pages 5 --concurrent 10 --mode stealth
```

## 2. CLI 인터페이스 규격 (`cli.py`)
하네스 스크립트 트리거 시 사용할 수 있는 매개변수(Arguments) 목록입니다.

| Argument | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `--url` | `str` | **Required** | 타겟 사이트 URL. `site_configs/` 내 YAML 설정과 자동 매핑됩니다. |
| `--max-pages` | `int` | `3` | 페이지네이션, 스크롤, 또는 더보기 클릭 반복 제한 횟수입니다. |
| `--concurrent` | `int` | `5` | Phase 2 (본문 수집) 시 동시 실행할 브라우저 파티션/워커의 최대 개수입니다. |
| `--mode` | `str` | `'stealth'` | 브라우저 모드. `stealth`(일반 우회), `unlocker`(BrightData 등 유료 프록시 사용) |
| `--phase1-only` | `flag` | `False` | 이 플래그를 추가하면 게시글 메타데이터(URL)만 수집하고 본문 수집은 스킵합니다. |

## 3. 파이프라인 실행 라이프사이클

전체 파이프라인은 크게 두 가지 Phase로 나뉘어 비동기(`asyncio`) 환경에서 순차 실행됩니다.

1. **Phase 1: 목록/링크 수집 (Link Collection)**
   - **모듈:** `core.stealth_crawler.test_with_stealth`
   - 타겟 URL로 접속해 설정된 페이지네이션 규칙(`core/pagination_handler.py`)을 따라 목록을 순회하며 게시글 URL과 메타데이터(Title 등)를 수집합니다.
   - `phase1_only` 플래그 활성화 시 여기서 종료됩니다.

2. **Phase 2: 병렬 본문 수집 (Parallel Body Crawling)**
   - **모듈:** `core.parallel_crawler.crawl_articles_parallel`
   - Phase 1에서 획득한 List 형식을 입력받아 지정된 `concurrent` 세마포어(Semaphore) 크기만큼 동시 다발적으로 본문 페이지에 접근하여 세부 데이터를 추출합니다.
   
3. **Phase 3: 결과 저장 및 에러 로깅 (Result Saving)**
   - **모듈:** `core.result_saver.save_phase2_result`
   - 성공한 항목은 `crawled_articles`로, 실패한 항목은 `failed_articles`로 식별하여 타임스탬프 기반 JSON/JSONL 형식으로 자동 저장됩니다.

4. **Phase 4: Scientific PDF 심사 및 필터링 (Post-processing)**
   - **모듈:** `core.pdf_analyzer.ScientificPDFAnalyzer`
   - 파이프라인을 통해 수집된 PDF 문서들을 대상으로 본문 데이터(PyMuPDF)를 분석하여 품질 심사를 진행합니다.
   - **심사 기준**: 디지털 본(Digital-born) 여부, 한국어 텍스트 비중(10% 이상), 멀티 모달리티(페이지 내 표/이미지/도형 동시 존재), 과학 기술 핵심 키워드 출현 빈도, 공공누리 기반의 라이선스 적합성.
   - 통과(Pass)한 고품질 데이터만 최종 추출하여 저장소에 이관하므로, Harness 데이터 파이프라인에서 수집 후 **품질 검증(QC) 노드**로 체인 연동이 가능합니다.

## 4. 입출력(I/O) 컨트랙트 및 환경 설정

### 입력 (Input / Config)
- **Environment (`.env`):** `shared/config.py`가 로드하며, 프로젝트 루트 혹은 한 단계 상위의 `.env`를 자동으로 탐색해 API 키 및 프록시 자격증명(BrightData 등)을 주입합니다. 자동화 서버 구성 시 `.env` 세팅이 필수입니다.
- **YAML Configs (`site_configs/*.yaml`):** 사이트별 DOM 셀렉터, 페이지네이션 사이클, Pre-Action 로직이 정의된 설정 파일입니다. 새로운 사이트를 추가하려면 코드 수정 없이 YAML 파일만 추가하면 됩니다.

### 출력 (Output / Artifacts)
- 파이프라인 실행이 완료되면 수집 데이터는 지정된 디렉토리(보통 `downloads/<site_name>/` 내부)에 기록됩니다.
- Data Integration Harness는 저장 완료가 콘솔에 찍히는 `"✅ 전체 파이프라인(CLI) 실행 완료!"` 로그를 워크플로우의 Success 상태 판단 기준으로 삼을 수 있습니다.

## 5. 에러 핸들링 및 재수집 전략 (Recrawl Strategy)
- 네트워크 타임아웃, Cloudflare 캡챠 블록 등으로 인해 실패한 Article들은 `failed_articles` 배열로 별도 분류되어 저장됩니다.
- 차후 하네스에서 장애 복구(Fallback) 로직을 돌릴 때, `core/recrawler.py` 모듈을 타겟하여 이 실패한 리스트만 주입해주면 전체 재동작 없이 누락분 보강이 가능한 구조로 설계되어 있습니다.

## 6. 하네스 연동 시 권장 사항 (Best Practices)
- **Rate Limiting:** `--concurrent` 수치를 타겟 서버의 Rate Limit 스펙 혹은 프록시 계정 비용(Bandwidth)에 맞춰 조절해야 합니다.
- **Logging Parsing:** `print()`를 통해 stdout으로 뱉어지는 로그는 `[헤더(🏁), 에러(❌), 성공(✅), 정보(ℹ️)]` 이모지 포맷을 준수하고 있으므로, Log Metric 수집기(Datadog, ELK 등)에서 필터링 정규식 처리가 용이합니다.
- **단위 테스트 (Unit Testing):** 파이프라인 수정이나 확장을 진행할 경우, 가장 하위 단위인 `core/` 내부의 단위 로직별로 pytest 통합이 가능합니다.
