"""
설정 관리
- ConfigLoader: site_configs/*.yaml 로드
- load_rules / get_rule: rules.yaml 기반 크롤링 규칙
- ParallelCrawlConfig: 병렬 크롤링 설정
"""
import yaml
from pathlib import Path
from urllib.parse import urlparse

# 현재 프로젝트(Crawling Code_refactor) 디렉토리 기준으로 설정
PROJECT_ROOT = Path(__file__).parent.parent
SITE_CONFIGS_DIR = PROJECT_ROOT / "site_configs"
RULES_PATH = PROJECT_ROOT / "rules.yaml"


class ParallelCrawlConfig:
    """병렬 크롤링 설정 클래스"""

    def __init__(self, enabled=True, max_concurrent=5, delay_min=1.0, delay_max=2.0, batch_size=100):
        self.enabled = enabled
        self.max_concurrent = max_concurrent
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.batch_size = batch_size


class ConfigLoader:
    """site_configs/*.yaml 파일들을 로드하고 URL에 맞는 설정을 찾아줍니다."""

    def __init__(self, config_dir=None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = SITE_CONFIGS_DIR

        self.configs = {}
        self.load_all()

    def load_all(self):
        """모든 YAML 파일 로드"""
        if not self.config_dir.exists():
            print(f"[ConfigLoader] Warning: {self.config_dir} directory not found")
            return

        loaded_count = 0
        for yaml_file in sorted(self.config_dir.glob("*.yaml")):
            # 템플릿 파일(_로 시작)은 스킵
            if yaml_file.name.startswith("_"):
                continue

            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                if config and 'site' in config:
                    url = config['site'].get('url', '')
                    if url:
                        self.configs[url] = config
                        loaded_count += 1
            except Exception as e:
                print(f"[ConfigLoader] Warning: Failed to load {yaml_file.name}: {e}")

        print(f"[ConfigLoader] Loaded {loaded_count} site configurations from {self.config_dir}")

    def get_config_by_url(self, url):
        """URL에 맞는 설정 반환"""
        if not url:
            return None

        parsed = urlparse(url)

        # 1. 정확한 매칭 시도 (URL이 config URL로 시작하는 경우)
        for config_url, config in self.configs.items():
            if url.startswith(config_url):
                return config

        # 2. 도메인 + 경로 부분 매칭
        for config_url, config in self.configs.items():
            config_parsed = urlparse(config_url)
            if parsed.netloc == config_parsed.netloc:
                config_path = config_parsed.path.rstrip('/')
                url_path = parsed.path.rstrip('/')
                if url_path.startswith(config_path):
                    return config

        # 3. 도메인만 매칭 (경로가 없는 경우)
        for config_url, config in self.configs.items():
            config_parsed = urlparse(config_url)
            if parsed.netloc == config_parsed.netloc:
                return config

        return None

    def get_all_configs(self):
        """모든 설정 반환"""
        return self.configs

    def reload(self):
        """설정 다시 로드"""
        self.configs = {}
        self.load_all()


# 전역 인스턴스 (싱글톤)
_loader = None


def get_config_loader():
    """ConfigLoader 인스턴스 가져오기 (싱글톤)"""
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader


def get_config_by_url(url):
    """URL에 맞는 설정 가져오기 (편의 함수)"""
    return get_config_loader().get_config_by_url(url)


# ========== rules.yaml 기반 크롤링 규칙 ==========
RULES = None


def load_rules(path=None):
    """rules.yaml 로드"""
    global RULES
    try:
        rules_path = path or str(RULES_PATH)
        with open(rules_path, "r", encoding="utf-8") as f:
            RULES = yaml.safe_load(f)
    except Exception:
        RULES = {"defaults": {}, "domains": {}}


def get_rule(url):
    """
    URL에 대한 크롤링 규칙 가져오기
    우선순위: site_configs/*.yaml > rules.yaml
    """
    # 1. site_configs에서 찾기 (우선순위)
    try:
        config = get_config_by_url(url)
        if config:
            converted_rule = {
                "render": config.get("crawling", {}).get("render", False),
                "detail": {}
            }

            content_detail = config.get("content", {}).get("detail", {})
            if content_detail:
                converted_rule["detail"] = {
                    "title_selector": content_detail.get("title_selector"),
                    "text_selectors": content_detail.get("text_selectors", []),
                    "image_selectors": content_detail.get("image_selectors", []),
                    "article_selector": content_detail.get("article_selector"),
                }

            pagination = config.get("pagination", {})
            if pagination.get("enabled"):
                converted_rule["pagination"] = pagination

            return converted_rule
    except Exception as e:
        print(f"[CONFIG] Warning: Error loading config for {url}: {e}")

    # 2. rules.yaml에서 찾기 (fallback)
    if RULES is None:
        load_rules()

    host = urlparse(url).netloc.lower()
    base = (RULES.get("defaults") or {})
    dom = (RULES.get("domains") or {}).get(host, {})
    rule = {**base, **dom}
    return rule
