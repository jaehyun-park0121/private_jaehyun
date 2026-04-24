"""
공유 상수 정의
- URL_TO_SOURCE_INFO: URL → (수집처 코드, URL 구분자) 매핑
- USER_AGENTS: 브라우저 User-Agent 목록
"""

# ========== URL → 수집처 코드 매핑 (전체 프로젝트 통합) ==========
URL_TO_SOURCE_INFO = {
    # META
    'research.facebook.com': ('META', 'research'),
    'tech.facebook.com': ('META', 'tech'),
    'engineering.fb.com': ('META', 'engineering'),
    'ai.meta.com': ('META', 'ai'),
    'developers.facebook.com': ('META', 'dev-fb'),
    'developers.meta.com': ('META', 'dev-mt'),

    # LKT (LinkedIn)
    'linkedin.com/blog/member': ('LKT', 'blog-member'),
    'linkedin.com/blog/engineering': ('LKT', 'blog-engineering'),

    # AMZ (Amazon)
    'developer.amazon.com': ('AMZ', 'dev'),
    'aws.amazon.com': ('AMZ', 'aws'),
    'amazon.science': ('AMZ', 'science'),

    # GGL (Google)
    'developers.googleblog.com': ('GGL', 'dev'),
    'blog.google/technology': ('GGL', 'tech'),
    'research.google/blog': ('GGL', 'research'),
    'cloud.google.com': ('GGL', 'cloud'),

    # MS (Microsoft)
    'techcommunity.microsoft.com': ('MS', 'tech'),
    'devblogs.microsoft.com': ('MS', 'dev'),
    'blogs.microsoft.com': ('MS', 'blog'),

    # SLK (Slack)
    'slack.engineering': ('SLK', 'engineering'),
    'slack.com/blog': ('SLK', 'blog'),
    'slack.dev': ('SLK', 'dev'),

    # OAI (OpenAI)
    'developers.openai.com/blog': ('OAI', 'dev'),
    'developers.openai.com': ('OAI', 'dev'),
    'openai.com': ('OAI', 'news'),

    # DMD (DeepMind)
    'deepmind.google/research': ('DMD', 'research'),
    'deepmind.google/blog': ('DMD', 'blog'),

    # ETC
    'alibabacloud.com': ('ABB', 'blog'),
    'technology.riotgames.com': ('RG', 'tech'),
    'github.blog': ('GH', 'blog'),
    'databricks.com': ('DB', 'blog'),
    'discord.com': ('DC', 'blog'),
    'stackoverflow.blog': ('SOF', 'blog'),
    'uber.com': ('UB', 'blog'),
}

# ========== User Agent 목록 ==========
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
