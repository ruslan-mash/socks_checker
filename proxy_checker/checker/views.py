from django.http import JsonResponse, HttpResponse
import threading
from threading import Lock
from rest_framework import viewsets, status
from .serializers import CheckedProxySerializer
import requests
import re
import time
from datetime import datetime
from fake_useragent import UserAgent
from proxy_information import ProxyInformation
from django.shortcuts import render
from .models import CheckedProxy


class ProxyViewSet(viewsets.ViewSet):
    def __init__(self):
        self.lock = threading.Lock()  # Create a lock to ensure thread safety
        self.proxies_list = []
        self.checked_socks = []
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
        self.checked_count = 0
        self.running = False

    def generate_proxy_list(self, request):
        # Query the database for all valid proxies
        proxies = CheckedProxy.objects.all()

        # Create a response with the content of ip:port format
        response = HttpResponse(content_type="text/plain")
        response['Content-Disposition'] = 'attachment; filename=proxy_list.txt'

        # Write the proxies to the response in ip:port format
        for proxy in proxies:
            response.write(f"{proxy.ip}:{proxy.port}\n")

        return response

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

    def check_proxy(self, url, timeout=5, max_retries=3):
        for count, proxy in enumerate(set(self.proxies_list), start=1):
            with self.lock:
                if not self.running:
                    break
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

    def start_proxy_check(self, request):
        with self.lock:  # Acquire the lock to safely modify self.running
            if self.running:
                return JsonResponse({'status': 'error', 'message': 'Proxy check is already running'})

            self.running = True  # Set running to True when the check starts

        print("Starting proxy check...")  # Add debug log

        # Start the background thread
        thread = threading.Thread(target=self.run)  # Updated to self.run
        thread.start()
        return JsonResponse({'status': 'success', 'message': 'Proxy check started'})

    def stop_proxy_check(self, request):
        with self.lock:  # Acquire the lock to safely modify self.running
            if not self.running:
                return JsonResponse({'status': 'error', 'message': 'No proxy check is running'})

            self.running = False  # Set running to False to stop the check

        print("Stopping proxy check...")  # Add debug log

        return JsonResponse({'status': 'success', 'message': 'Proxy check stopped'})

    # def proxy_status(self, request):
    #     print("Checking proxy status...")  # Add debug log
    #     if self.running:
    #         elapsed_time = time.time() - self.start_time
    #         remaining_time = self.timer(self.checked_count)['remaining_seconds']
    #         total_checked = len(self.checked_socks)
    #         return JsonResponse({
    #             'status': 'running',
    #             'elapsed_time': round(elapsed_time, 2),
    #             'remaining_time': round(remaining_time, 2),
    #             'total_checked': total_checked,
    #         })
    #     else:
    #         return JsonResponse({'status': 'idle'})

    def run(self):
        with self.lock:
            self.get_data_from_geonode()
            self.get_data_from_socksus()
            self.get_data_from_txt()
            self.check_proxy("https://www.cloudflare.com/")


def proxy_list(request):
    proxies = CheckedProxy.objects.all()

    proxy_view_set = ProxyViewSet()
    total_proxies = len(set(proxy_view_set.proxies_list))
    start_time = proxy_view_set.start_time

    context = {
        'proxies': proxies,
        'total_proxies': total_proxies,
        'start_time': start_time,
    }

    return render(request, 'checker/proxy_list.html', context)
