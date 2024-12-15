import requests
import re
import time
from fake_useragent import UserAgent
from datetime import datetime
import django
import os
import sys
import socks


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proxy_checker.settings')
django.setup()

from checker.models import CheckedProxy
from proxy_information import ProxyInformation

class ProxyValidator:
    def __init__(self, proxies_list, checked_socks, start_time, header, txt_sources, checked_count):
        self.proxies_list = proxies_list
        self.checked_socks = checked_socks
        self.start_time = start_time
        self.header = header
        self.txt_sources = txt_sources
        self.checked_count = checked_count

    def get_data_from_geonode(self):
        base_url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500"
        try:
            response = requests.get(f"{base_url}&page=1&sort_by=lastChecked&sort_type=desc", headers=self.header)
            response.raise_for_status()
            total = response.json().get('total', 0)
            print(f"Total proxies available: {total}")

            total_pages = (total // 500) + 1
            for number_page in range(1, total_pages + 1):
                page_url = f"{base_url}&page={number_page}&sort_by=lastChecked&sort_type=desc"
                try:
                    response = requests.get(page_url, headers=self.header)
                    response.raise_for_status()
                    data = response.json().get('data', [])
                    for entry in data:
                        ip = entry.get('ip')
                        port = entry.get('port')
                        if ip and port:
                            self.proxies_list.append(f"{ip}:{port}")
                    print(f"Page {number_page} processed. Total proxies collected: {len(self.proxies_list)}")
                except requests.exceptions.RequestException as e:
                    print(f"Error getting proxies from {page_url}: {e}")

        except requests.exceptions.RequestException as e:
            print(f"Error getting information from {base_url}: {e}")

    def get_data_from_socksus(self):
        url = "https://sockslist.us/Api?request=display&country=all&level=all&token=free"
        try:
            response = requests.get(url=url, headers=self.header)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        ip = entry.get('ip')
                        port = entry.get('port')
                        if ip and port:
                            self.proxies_list.append(f"{ip}:{port}")

        except requests.exceptions.RequestException as e:
            print(f"Error getting proxies from {url}: {e}")

    def get_data_from_txt(self):
        pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)'
        for url in self.txt_sources:
            try:
                response = requests.get(url=url, headers=self.header)
            except requests.exceptions.RequestException as e:
                print(f"Error getting proxies from {url}: {e}")
                continue
            if response.ok:
                proxy_list = response.text.splitlines()
                proxy_list_filtered = re.findall(pattern, "\n".join(proxy_list))
                self.proxies_list.extend(proxy_list_filtered)

    def timer(self, start):
        elapsed_time = time.time() - self.start_time
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        print(f'Total checked {start} out of {len(set(self.proxies_list))}, elapsed {hours} hours {minutes} minutes {seconds} seconds')

    def check_proxy_with_proxyinformation(self, proxy):
        checker = ProxyInformation()
        result = checker.check_proxy(proxy)
        if result.get("status") == True:
            result['date'] = datetime.today().date()
            result['time'] = datetime.today().time()
            self.checked_socks.append(result)

            # Save result to database
            CheckedProxy.objects.create(
                ip=proxy.split(':')[0],
                port=int(proxy.split(':')[1]),
                country=result.get('country', ''),
                anonymity=result.get('anonymity', ''),
                status=result.get('status', False),
                date_checked=result['date'],
                time_checked=result['time']
            )

    def check_proxy(self, url, timeout=5, max_retries=3):
        for count, proxy in enumerate(set(self.proxies_list), start=1):
            proxy_dict = {
                'http': f'socks5://{proxy}',
                'https': f'socks5://{proxy}'
            }
            retry_attempts = 0
            while retry_attempts < max_retries:
                try:
                    response = requests.get(url=url, headers=self.header, proxies=proxy_dict, timeout=timeout)
                    if response.ok:
                        self.check_proxy_with_proxyinformation(proxy)
                        print(f"Proxy {proxy} valid through SOCKS5, status: {response.status_code}")
                        break
                except requests.exceptions.RequestException as e:
                    retry_attempts += 1
                    if retry_attempts >= max_retries:
                        print(f"Error checking proxy {proxy} through SOCKS5: {e}")
            self.checked_count += 1
            self.timer(self.checked_count)

    def run(self):
        self.get_data_from_geonode()
        self.get_data_from_socksus()
        self.get_data_from_txt()
        print(f'Found {len(set(self.proxies_list))} proxies')

        self.check_proxy('https://cloudflare.com')
        self.timer(self.checked_count)

        total_elapsed_time = time.time() - self.start_time
        total_hours = int(total_elapsed_time // 3600)
        total_minutes = int((total_elapsed_time % 3600) // 60)
        total_seconds = int(total_elapsed_time % 60)
        print(f"--- Total time spent {total_hours} hours {total_minutes} minutes {total_seconds} seconds ---")


if __name__ == "__main__":
    proxies_list = []
    checked_socks = []
    start_time = time.time()
    header = {'User-Agent': UserAgent().random}
    checked_count = 0
    txt_sources = [
        # "https://spys.me/socks.txt",
        # "https://www.proxy-list.download/api/v1/get?type=socks5&anon=elite",
        # "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
        # "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
        # "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
        # "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
        # "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        # "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt",
        # "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
    ]

    # Create and run ProxyValidator instance
    proxy_validator = ProxyValidator(proxies_list, checked_socks, start_time, header, txt_sources, checked_count)
    proxy_validator.run()
