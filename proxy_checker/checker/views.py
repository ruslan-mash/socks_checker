from django.http import JsonResponse, HttpResponse
from django.views import View
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

import requests
import re
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from proxy_information import ProxyInformation
from django.shortcuts import render
from django.core.cache import cache
from threading import Thread, Lock, Event
from .serializers import CheckedProxySerializer
from .models import CheckedProxy


class ProxyViewSet(viewsets.ModelViewSet):
    queryset = CheckedProxy.objects.all()
    serializer_class = CheckedProxySerializer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxies_list = []
        self.start_time = datetime.now()
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
        self.lock = Lock()  # Блокировка для обеспечения безопасности потока при изменении proxy_list
        self.checked_proxies_count_key = "checked_proxies_count"
        self.stop_event = Event()

        # Инициализируем кэш для количества проверенных прокси
        if not cache.get(self.checked_proxies_count_key):
            cache.set(self.checked_proxies_count_key, 0)

    # Функция забора данных с geonode.com
    def get_data_from_geonode(self):
        base_url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500"
        try:
            response = requests.get(f"{base_url}&page=1&sort_by=lastChecked&sort_type=desc", headers=self.header)
            response.raise_for_status()
            total = response.json().get('total', 0)
            print(f"Всего прокси с geonode.com : {total}")

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
                    print(f"Страница {number_page} забрана. Всего забрано прокси: {len(self.proxies_list)}")
                    # Update the cache with the total proxies count after fetching
                    cache.set('total_proxies', len(self.proxies_list))
                except requests.exceptions.RequestException as e:
                    print(f"Ошибка получения прокси из {page_url}: {e}")

        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения информации из {base_url}: {e}")

    # Функция забора прокси из sockslist.us
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
                            # Update the cache with the total proxies count after fetching
                            cache.set('total_proxies', len(self.proxies_list))
            print(f"Всего прокси из socks.us: {len(data)}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения прокси из  {url}: {e}")

    # Функция забора прокси из списков с github
    def get_data_from_txt(self):
        pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)'
        total_proxies = 0
        for url in self.txt_sources:
            try:
                response = requests.get(url=url, headers=self.header)
            except requests.exceptions.RequestException as e:
                print(f"Ошибка получения прокси из {url}: {e}")
                continue
            if response.ok:
                proxy_list = response.text.splitlines()
                proxy_list_filtered = re.findall(pattern, "\n".join(proxy_list))
                self.proxies_list.extend(proxy_list_filtered)
                # Update the cache with the total proxies count after fetching
                cache.set('total_proxies', len(self.proxies_list))
                total_proxies += len(proxy_list_filtered)
        print(f"Всего прокси из txt_sources : {total_proxies}")

    # Функция предварительной проверки прокси на ответ с передачей на дентальную проверку
    def check_proxy(self, url, timeout=5, max_retries=3):
        print("Запуск цикла проверки прокси...")
        proxies_to_check = set(self.proxies_list)
        for count, proxy in enumerate(proxies_to_check, start=1):
            # Проверяем, если флаг остановки установлен, то выходим из цикла
            with self.lock:
                if not cache.get('proxy_check_running', True):
                    print("Остановка проверки прокси по флагу проверки")
                    break
            # if self.stop_event.is_set():
            #     print("Проверка прокси была остановлена.")
            #     break

            checked_proxies_count = cache.get(self.checked_proxies_count_key, 0)
            cache.set(self.checked_proxies_count_key, checked_proxies_count + 1)
            print(f"Проверено прокси {proxy}...")

            proxy_dict = {
                'http': f'socks5://{proxy}',
                'https': f'socks5://{proxy}'
            }

            for _ in range(max_retries):
                try:
                    response = requests.get(url=url, headers=self.header, proxies=proxy_dict, timeout=timeout)
                    print(f"Proxy {proxy} check - Response: {response.status_code}")
                    if response.ok:
                        self.check_proxy_with_proxyinformation(proxy)
                        break
                except requests.exceptions.RequestException as e:
                    print(f"Error checking proxy {proxy}: {e}")

    # Функция детальной проверки прокси с помощью ProxyInformation и записи результата в БД
    def check_proxy_with_proxyinformation(self, proxy):
        checker = ProxyInformation()
        result = checker.check_proxy(proxy)
        if result.get("status") == True:
            info = result.get("info", {})
            date = datetime.today().date()
            time = datetime.today().strftime('%H:%M:%S')
            # форматирование response_time до 2 знаков после запятой
            response_time = round(info.get('responseTime', 0), 2)
            # Сохраняем результат в базу данных через сериализатор
            proxy_data = {
                'ip': info.get('ip'),
                'port': int(info.get('port')),
                'protocol': info.get('protocol'),
                'response_time': response_time,
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
                print(f"Ошибка сериализатора: {serializer.errors}")

    # Подсчет количества прокси и времени выполнения
    def timer(self):
        total_proxies = cache.get('total_proxies', len(set(self.proxies_list)))
        checked_proxies_count = cache.get(self.checked_proxies_count_key, 0)
        remaining_proxies = total_proxies - checked_proxies_count

        # if total_proxies == 0 or checked_proxies_count == 0:
        #     return {
        #         'total_checked': 0,
        #         'total_proxies': total_proxies,
        #         'remaining_hours': 0,
        #         'remaining_minutes': 0,
        #         'remaining_seconds': 0
        #     }

        start_time = cache.get('start_time')
        if not start_time:
            start_time = datetime.now()
            cache.set('start_time', start_time)

        elapsed_time = (datetime.now() - start_time).total_seconds()
        avg_time_per_proxy = elapsed_time / checked_proxies_count
        remaining_time = avg_time_per_proxy * remaining_proxies

        remaining_hours = int(remaining_time // 3600)
        remaining_minutes = int((remaining_time % 3600) // 60)
        remaining_seconds = int(remaining_time % 60)

        return {
            'total_checked': checked_proxies_count,
            'total_proxies': total_proxies,
            'remaining_hours': remaining_hours,
            'remaining_minutes': remaining_minutes,
            'remaining_seconds': remaining_seconds
        }

    # урл для таймера
    @action(detail=False, methods=['get'])
    def get_timer(self, request):
        timer_data = self.timer()
        return Response(timer_data)

    # урл для генерации TXT
    @action(detail=False, methods=['get'])
    def generate_txt_list(self, request):
        print("Генерация txt листа...")
        # Запросить базу данных для всех допустимых прокси
        proxies = CheckedProxy.objects.all()

        # Создать ответ с содержимым формата ip:port
        response = HttpResponse(content_type="text/plain")
        response['Content-Disposition'] = 'attachment; filename=proxy_list.txt'

        # Записать прокси в ответ в формате ip:port
        for proxy in proxies:
            response.write(f"{proxy.ip}:{proxy.port}\n")

        return response

    # урл для генерации JSON
    @action(detail=False, methods=['get'])
    def generate_json_list(self, request):
        print("Генерация json листа...")
        # Запросить базу данных для всех допустимых прокси
        proxies = CheckedProxy.objects.all()

        # Создать список прокси в формате ip:port
        proxy_list = [{"ip": proxy.ip, "port": proxy.port} for proxy in proxies]

        # Вернуть список как ответ JSON
        return JsonResponse({'proxy_list': proxy_list})

    # урл для запуска проверки прокси
    @action(detail=False, methods=['post'])
    def start_proxy_check(self, request):
        print("Запуск проверки прокси...")

        self.get_data_from_geonode()
        self.get_data_from_socksus()
        self.get_data_from_txt()
        cache.set('proxy_check_running', True)

        cache.set('total_proxies', len(self.proxies_list))
        self.check_proxy_thread = Thread(target=self.check_proxy, args=("https://ipinfo.io/json",))
        self.check_proxy_thread.start()

        # Проверка, что поток действительно работает
        if self.check_proxy_thread.is_alive():
            print("Proxy check thread is running.")
        else:
            print("Proxy check thread is not running.")

        timer_data = self.timer()

        return JsonResponse({'status': 'Proxy check started', 'timer_data': timer_data})

    # урл досрочной остановки проверки прокси
    @action(detail=False, methods=['post'])
    def stop_proxy_check(self, request):
        print("Stopping proxy check...")
        cache.set('proxy_check_running', False)

        cache.set(self.checked_proxies_count_key, 0)
        cache.set('total_proxies', 0)

        return JsonResponse({'status': 'Proxy check stopped'})


# удаление из БД записей старше 24 часов (бесполезны)
class CleanOldRecordsView(APIView):

    def delete(self, request, *args, **kwargs):
        try:
            threshold_date = datetime.today() - timedelta(days=1)  # Данные старше 1 дня
            old_records = CheckedProxy.objects.filter(date_checked__lt=threshold_date)
            count, _ = old_records.delete()
            return Response({"message": f"Удалено {count} старых записей."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Представление для списка прокси
class ProxyListView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/proxy_list.html')


# Представление для страницы "О нас"
class AboutView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/about.html')


# Представление для страницы FAQ
class FaqView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/faq.html')
