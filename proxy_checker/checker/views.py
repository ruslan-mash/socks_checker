from django.http import JsonResponse, HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from .serializers import CheckedProxySerializer
import requests
import re
import time
from datetime import datetime
from fake_useragent import UserAgent
from proxy_information import ProxyInformation
from django.shortcuts import render
from .models import CheckedProxy
from django.core.cache import cache


class ProxyViewSet(viewsets.ModelViewSet):
    queryset = CheckedProxy.objects.all()
    serializer_class = CheckedProxySerializer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = False  # Initialize running state
        self.proxies_list = []
        self.start_time = time.time()
        self.header = {'User-Agent': UserAgent().random}
        self.txt_sources = [
            "https://spys.me/socks.txt",
            "https://www.proxy-list.download/api/v1/get?type=socks5&anon=elite",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
            "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt",
            "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
        ]

    def get_data_from_geonode(self):
        base_url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500"
        try:
            response = requests.get(f"{base_url}&page=1&sort_by=lastChecked&sort_type=desc", headers=self.header)
            response.raise_for_status()
            total = response.json().get('total', 0)
            print(f"Total proxies from geonode.com available: {total}")

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
            print(f"Total proxies from socks.us available: {len(data)}")
        except requests.exceptions.RequestException as e:
            print(f"Error getting proxies from {url}: {e}")

    def get_data_from_txt(self):
        pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)'
        total_proxies = 0
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
                total_proxies += len(proxy_list_filtered)
        print(f"Total proxies from txt_sources available: {total_proxies}")

    def check_proxy(self, url, timeout=5, max_retries=3):
        print("Starting proxy check loop...")
        for count, proxy in enumerate(set(self.proxies_list), start=1):
            print(f"Checking proxy {proxy}...")

            # Check if stop flag is set, if yes, break out of the loop
            if not cache.get('proxy_check_running', False):
                print("Stopping proxy check due to stop signal.")
                break

            proxy_dict = {
                'http': f'socks5://{proxy}',
                'https': f'socks5://{proxy}'
            }

            retry_attempts = 0
            while retry_attempts < max_retries:
                if not cache.get('proxy_check_running', False):
                    print("Stopping proxy check due to stop signal.")
                    break

                try:
                    response = requests.get(url=url, headers=self.header, proxies=proxy_dict, timeout=timeout)
                    print(f"Checking proxy {proxy} - Response status: {response.status_code}")
                    if response.ok:
                        self.check_proxy_with_proxyinformation(proxy)
                        break
                except requests.exceptions.RequestException as e:
                    retry_attempts += 1
                    print(f"Error checking proxy {proxy}: {e}")
                    if retry_attempts >= max_retries:
                        print(f"Failed to check proxy {proxy} after {max_retries} attempts.")
                        break

    def check_proxy_with_proxyinformation(self, proxy):
        checker = ProxyInformation()
        result = checker.check_proxy(proxy)
        if result.get("status") == True:
            info = result.get("info", {})
            date = datetime.today().date()
            time = datetime.today().time()

            # Save result to database using serializer
            proxy_data = {
                'ip': info.get('ip'),
                'port': int(info.get('port')),
                'protocol': info.get('protocol'),
                'response_time': info.get('responseTime', 0),
                'anonymity': info.get('anonymity', ''),
                'country': info.get('country', ''),
                'country_code': info.get('country_code', ''),
                'date_checked': date,
                'time_checked': time
            }
            serializer = CheckedProxySerializer(data=proxy_data)
            if serializer.is_valid():
                serializer.save()
            else:
                print(f"Serializer errors: {serializer.errors}")

    def timer(self, start):
        total_proxies = len(set(self.proxies_list))
        elapsed_time = time.time() - self.start_time
        avg_time_per_proxy = elapsed_time / start if start != 0 else 0
        remaining_proxies = total_proxies - start
        remaining_time = avg_time_per_proxy * remaining_proxies

        remaining_hours = int(remaining_time // 3600)
        remaining_minutes = int((remaining_time % 3600) // 60)
        remaining_seconds = int(remaining_time % 60)

        return {
            'total_checked': start,
            'total_proxies': total_proxies,
            'remaining_hours': remaining_hours,
            'remaining_minutes': remaining_minutes,
            'remaining_seconds': remaining_seconds
        }

    @action(detail=False, methods=['get'])
    def generate_proxy_list(self, request):
        print("Generating proxy list...")
        # Query the database for all valid proxies
        proxies = CheckedProxy.objects.all()

        # Create a response with the content of ip:port format
        response = HttpResponse(content_type="text/plain")
        response['Content-Disposition'] = 'attachment; filename=proxy_list.txt'

        # Write the proxies to the response in ip:port format
        for proxy in proxies:
            response.write(f"{proxy.ip}:{proxy.port}\n")

        return response

    @action(detail=False, methods=['post'])
    def start_proxy_check(self, request):
        print("Starting proxy check...")
        cache.set('proxy_check_running', True)  # Store the running state in cache
        self.get_data_from_geonode()
        self.get_data_from_socksus()
        self.get_data_from_txt()
        self.check_proxy("https://www.cloudflare.com/")
        return JsonResponse({"message": "Проверка прокси начата"})

    @action(detail=False, methods=['post'])
    def stop_proxy_check(self, request):
        cache.set('proxy_check_running', False)  # Stop the proxy check by setting running state to False
        print("Stopping proxy check...")


def proxy_list(request):
    return render(request, 'checker/proxy_list.html')


def about(request):
    return render(request, 'checker/about.html')


def faq(request):
    return render(request, 'checker/faq.html')
