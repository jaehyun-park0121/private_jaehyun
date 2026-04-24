"""
Bright Data 프록시 관리
- ProxyManager: 환경변수에서 프록시 설정 로드, fallback 순서 관리
"""
import os
from dotenv import load_dotenv


class ProxyManager:
    """Bright Data 프록시 설정 및 fallback 관리"""

    def __init__(self):
        load_dotenv()
        self._load_proxies()

    def _load_proxies(self):
        """환경변수에서 모든 프록시 설정 로드"""
        # 1️⃣ Datacenter Proxy (포트 33335 또는 22223)
        dc_username = os.environ.get("BRIGHTDATA_DC_USERNAME")
        dc_apikey = os.environ.get("BRIGHTDATA_DC_APIKEY")
        dc_port = 33335 if dc_username and ('ip-' in dc_username or 'unlocker' in dc_username) else 22223
        self.proxy_datacenter = (
            f"http://{dc_username}:{dc_apikey}@brd.superproxy.io:{dc_port}"
            if dc_username and dc_apikey else None
        )
        self._dc_port = dc_port

        # 2️⃣ ISP Proxy (포트 33335 또는 22224)
        isp_username = os.environ.get("BRIGHTDATA_ISP_USERNAME")
        isp_apikey = os.environ.get("BRIGHTDATA_ISP_APIKEY")
        isp_port = 33335 if isp_username and ('ip-' in isp_username or 'unlocker' in isp_username) else 22224
        self.proxy_isp = (
            f"http://{isp_username}:{isp_apikey}@brd.superproxy.io:{isp_port}"
            if isp_username and isp_apikey else None
        )
        self._isp_port = isp_port

        # 3️⃣ Residential Proxy (포트 22225)
        res_username = os.environ.get("BRIGHTDATA_RES_USERNAME")
        res_apikey = os.environ.get("BRIGHTDATA_RES_APIKEY")
        self.proxy_residential = (
            f"http://{res_username}:{res_apikey}@brd.superproxy.io:22225"
            if res_username and res_apikey else None
        )

        # 기존 설정 (하위 호환성)
        self.proxy = os.environ.get("BRIGHTDATA_PROXY")
        self.proxy_wu = os.environ.get("BRIGHTDATA_PROXY_WU")
        wu_username = os.environ.get("BRIGHTDATA_WU_USERNAME")
        wu_apikey = os.environ.get("BRIGHTDATA_WU_APIKEY")
        if not self.proxy_wu and wu_username and wu_apikey:
            self.proxy_wu = f"http://{wu_username}:{wu_apikey}@brd.superproxy.io:22225"

        # Fallback: 기존 설정이 있고 신규 설정이 없으면 자동 할당
        if not self.proxy_residential and self.proxy_wu:
            self.proxy_residential = self.proxy_wu

        # 4️⃣ Scraping Browser (자동 Residential)
        self.sb_token = os.environ.get("BRIGHTDATA_SB_TOKEN")
        self.sb_url = os.environ.get("BRIGHTDATA_SB_URL")
        self.sb_auth = self.sb_url or self.sb_token

        # 5️⃣ Web Unlocker 2 (포트 33335)
        unlocker_username = os.environ.get("BRIGHTDATA_UNLOCKER_USERNAME")
        unlocker_apikey = os.environ.get("BRIGHTDATA_UNLOCKER_APIKEY")
        self.proxy_unlocker = (
            f"http://{unlocker_username}:{unlocker_apikey}@brd.superproxy.io:33335"
            if unlocker_username and unlocker_apikey else None
        )

    @property
    def brightdata_available(self):
        """Bright Data 사용 가능 여부"""
        return bool(self.sb_auth)

    def get_phase2_proxy_config(self, proxy_type="auto"):
        """
        Phase 2 (게시글 크롤링)용 프록시 설정 반환

        Args:
            proxy_type: 'auto', 'datacenter', 'isp', 'residential', 'unlocker', 'scraping_browser'

        Returns:
            dict: {'proxy_url': str, 'proxy_name': str, 'browser_mode': str}
        """
        if proxy_type == "auto":
            # 우선순위: Datacenter > ISP > Unlocker > Residential > Scraping Browser
            if self.proxy_datacenter:
                return {
                    'proxy_url': self.proxy_datacenter,
                    'proxy_name': 'Datacenter',
                    'browser_mode': 'unlocker'
                }
            elif self.proxy_isp:
                return {
                    'proxy_url': self.proxy_isp,
                    'proxy_name': 'ISP',
                    'browser_mode': 'unlocker'
                }
            elif self.proxy_unlocker:
                return {
                    'proxy_url': self.proxy_unlocker,
                    'proxy_name': 'Unlocker',
                    'browser_mode': 'unlocker'
                }
            elif self.proxy_residential:
                return {
                    'proxy_url': self.proxy_residential,
                    'proxy_name': 'Residential',
                    'browser_mode': 'unlocker'
                }
            elif self.sb_auth:
                return {
                    'proxy_url': None,
                    'proxy_name': 'Scraping Browser',
                    'browser_mode': 'scraping_browser'
                }
            else:
                return {
                    'proxy_url': None,
                    'proxy_name': 'None (Stealth)',
                    'browser_mode': 'stealth'
                }

        proxy_map = {
            'datacenter': (self.proxy_datacenter, 'Datacenter', 'unlocker'),
            'isp': (self.proxy_isp, 'ISP', 'unlocker'),
            'residential': (self.proxy_residential, 'Residential', 'unlocker'),
            'unlocker': (self.proxy_unlocker, 'Unlocker', 'unlocker'),
            'scraping_browser': (None, 'Scraping Browser', 'scraping_browser'),
        }

        if proxy_type in proxy_map:
            proxy_url, name, mode = proxy_map[proxy_type]
            return {'proxy_url': proxy_url, 'proxy_name': name, 'browser_mode': mode}

        return {'proxy_url': None, 'proxy_name': 'None', 'browser_mode': 'stealth'}

    def get_fallback_order(self, browser_mode):
        """
        Phase 2에서 실패 시 다른 프록시로 fallback하는 순서 반환

        Returns:
            list of dict: [{'proxy_url': ..., 'proxy_name': ..., 'browser_mode': ...}, ...]
        """
        fallback_list = []

        if browser_mode in ['stealth', 'auto']:
            fallback_list.append({
                'proxy_url': None, 'proxy_name': 'Stealth', 'browser_mode': 'stealth'
            })

        if self.proxy_datacenter:
            fallback_list.append({
                'proxy_url': self.proxy_datacenter, 'proxy_name': 'Datacenter', 'browser_mode': 'unlocker'
            })
        if self.proxy_isp:
            fallback_list.append({
                'proxy_url': self.proxy_isp, 'proxy_name': 'ISP', 'browser_mode': 'unlocker'
            })
        if self.proxy_unlocker:
            fallback_list.append({
                'proxy_url': self.proxy_unlocker, 'proxy_name': 'Unlocker', 'browser_mode': 'unlocker'
            })
        if self.sb_auth:
            fallback_list.append({
                'proxy_url': None, 'proxy_name': 'Scraping Browser', 'browser_mode': 'scraping_browser'
            })

        return fallback_list

    def print_status(self):
        """로드된 프록시 설정 출력"""
        print("\n[Bright Data 설정 확인]")

        if self.sb_auth and self.sb_auth.startswith("wss://"):
            try:
                username_part = self.sb_auth.split("@")[0].replace("wss://", "").split(":")[0]
                if "hl_" in username_part:
                    customer_id = username_part.split("-zone-")[0].replace("brd-customer-", "")
                    print(f"  🔑 Customer ID: {customer_id}")
                if "-zone-" in username_part:
                    zone_name = username_part.split("-zone-")[-1]
                    print(f"  🎯 Zone Name: {zone_name}")
            except Exception:
                pass

        dc_type = f"Static IP ({self._dc_port})" if self._dc_port == 33335 else f"Regular ({self._dc_port})"
        print(f"  💰 Datacenter Proxy: {'✅ 설정됨 (' + dc_type + ')' if self.proxy_datacenter else '❌ 없음'}")

        isp_type = f"Static IP ({self._isp_port})" if self._isp_port == 33335 else f"Regular ({self._isp_port})"
        print(f"  ⚡ ISP Proxy: {'✅ 설정됨 (' + isp_type + ')' if self.proxy_isp else '❌ 없음'}")

        print(f"  🏠 Residential Proxy (22225): {'✅ 설정됨' if self.proxy_residential else '❌ 없음'}")
        print(f"  🔓 Web Unlocker (33335): {'✅ 설정됨' if self.proxy_unlocker else '❌ 없음'}")
        print(f"  🦾 Scraping Browser (9222): {'✅ 설정됨' if self.sb_auth else '❌ 없음'}")
        print()
