# Crawling Code Refactoring Context (Harness Engineering)

## 1. 프로젝트 개요 및 현재 상태
어제 진행되었던 작업은 거대한 크롤링 스크립트를 기능별로 모듈화하고 유지보수성을 극대화하기 위한 **코드 리팩토링** 작업이었습니다. 
현재 `Crawling Code_refactor` 폴더 내에 코드가 성공적으로 분리 및 이관되었으며, **구조적 리팩토링은 거의 100% 완료된 상태**입니다.

### 📁 디렉토리별 역할 분담 완료 상태
- **`core/`**: 핵심 비즈니스 로직 (크롤러 단독 실행 모듈)
  - `stealth_crawler.py` / `unlocker_crawler.py` / `browser_api_crawler.py`: 접속 우회 및 각 방식별 크롤링 로직 분리
  - `parallel_crawler.py`: 다중 게시글 병렬 수집 로직 (세마포어 적용 완료)
  - `category_crawler.py`: 범주형/카테고리별 사이트 수집
  - `pagination_handler.py`: 다양한 타입의 페이지네이션(클릭/스크롤/URL) 통합 핸들러
  - `search_handler.py`: YAML `search` 설정 기반 사이트 내 검색 자동화 (form/url_template/post 모드)
  - `media_extractor.py`: Playwright 페이지에서 이미지/비디오/오디오 미디어 요소 추출 (stealth·unlocker 공통 로직 통합)
  - `pdf_analyzer.py`: PyMuPDF 기반 과학기술 문서(특허·논문) 심층 필터링 및 라이선스 검사
  - `result_saver.py`: 수집 결과 저장 (JSON/Excel/링크 파일 출력)
  - `recrawler.py`: 실패한 JSONL 기반의 에러 복구 및 재수집
- **`shared/`**: 전역 상태 및 환경 설정
  - `config.py` / `constants.py`: 경로, 타임아웃, 설정 클래스 모음
  - `proxy_manager.py`: 프록시, BrightData 인증 및 자동 풀백 로직
  - `url_utils.py`: 리다이렉트 URL 디코딩(Facebook/LinkedIn 등) 및 URL→수집처 코드 매핑
- **`utils/`**: 공용 유틸리티
  - `cloudflare_handler.py`: Cloudflare 챌린지 자동 우회
  - `cookie_handler.py`: 쿠키 동의 팝업 자동 처리
  - `svg_capture.py`: 페이지 SVG/스크린샷 캡처
  - `html_helpers.py`: BeautifulSoup 기반 HTML 파싱 헬퍼 (제목 추출 등)
  - `language.py`: URL 기반 언어 설정 및 다국어 URL 변환 유틸
  - `windows_hwp_converter.py`: 한컴오피스 COM 연동 HWP→DOCX 일괄 변환 (Windows 전용)
- **`widgets/` (GUI)**
  - `pagination_gui.py`: Tkinter 기반 프론트엔드 코드만 남기고, 크롤링 처리는 모두 `core/`에 위임(Event Driven 구조 완료)
- **`main.py`**: GUI(Tkinter) 기반 진입점
- **`cli.py`**: argparse 기반 CLI 진입점 (Harness 파이프라인 자동화용, 구현 완료)

---

## 2. 다음 작업 및 Harness Engineering을 위한 가이드

하네스 엔지니어링(테스트 자동화 인프라 혹은 향후 유지보수 작업)을 이어나가기 위해 알고 있어야 할 핵심 컨텍스트입니다.

### 📌 CI/CD 및 자동화 고려사항
- 기존 스크립트에서는 GUI와 크롤링 로직이 엉켜있어 CLI(Command Line Interface) 기반 테스트 자동화가 어려웠으나, 이제는 `core/` 내부 함수 단위(예: `crawl_articles_parallel`, `crawl_single_article`)로 쪼개져 있어 **단위 테스트(Unit Test) 및 파이프라인 연동이 용이**합니다.
- 설정 파일(`site_configs/*.yaml`)과 `.env`만 교환하면 코드를 수정하지 않고 타겟 사이트를 변경하여 Harness Pipeline 등에서 병렬 실행 검증이 가능합니다.

### 📌 향후 이어갈 수 있는 개발 포인트
1. **안정성 테스트**: `Crawling Code_refactor/main.py`를 실행시켜, GUI에서 기존 로직과 동일하게 사이트 목록을 불러오고 병렬 크롤링이 정상 작동하는지 "기능 통합 테스트(Integration Test)"를 진행해야 할 단계입니다.
2. **에러 핸들링 고도화**: `parallel_crawler.py` 등에서 발생한 실패 내역을 저장하고 `recrawler.py`를 통해 복구하는 로직이 구현되었으나, 이 재크롤링 파이프라인의 실효성을 검증하는 작업이 필요합니다.
3. **CLI 파이프라인 검증**: `cli.py`가 이미 구현되어 있으므로, `python cli.py --url <URL> --max-pages 5` 등의 명령으로 Harness Pipeline에서 GUI 없이 자동화 실행이 가능합니다. 이 CLI 경로의 E2E 테스트를 진행해야 합니다.

---

## 3. 요약 (Where we left off)
> 어제 작업은 **"단일 파일의 비대함 해소 및 모듈 분리(Decoupling)"**를 목표로 삼았고, 그 결과물로 `Crawling Code_refactor` 디렉토리에 **모든 코드가 이상적으로 배치 완료**되었습니다. 
> 오늘부터는 이 모듈화된 폴더를 기반으로 **1) 결합 테스트 수행 2) 추가적인 명령줄 기반(CLI) 파이프라인 연동**을 진행하시면 됩니다.
