from django.http import JsonResponse, HttpResponse
from django.views import View
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import cloudscraper
import requests
import re
import certifi
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from proxy_information import ProxyInformation
from django.shortcuts import render
from django.core.cache import cache
from threading import Thread, Lock
from .serializers import CheckedProxySerializer
from .models import CheckedProxy
from rest_framework.pagination import PageNumberPagination
from itertools import islice



# класс разбиения на страницы
class CheckedProxyPagination(PageNumberPagination):
    page_size = 8  # на 8 страниц
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProxyViewSet(viewsets.ModelViewSet):
    queryset = CheckedProxy.objects.all()
    serializer_class = CheckedProxySerializer
    pagination_class = CheckedProxyPagination

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxies_list = []
        self.header = {'User-Agent': UserAgent().random}  # разный UserAgent для каждого запроса
        # self.header = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36'}
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
        self.start_time_key = "start_time"
        # self.stop_event = Event() # событие остановки проверки

        # Инициализируем кэш для количества проверенных прокси и времени старта
        if not cache.get(self.checked_proxies_count_key):
            cache.set(self.checked_proxies_count_key, 0, timeout=None)
        if not cache.get(self.start_time_key):
            cache.set(self.start_time_key, datetime.now(), timeout=None)

    # Функция забора данных с geonode.com
    def get_data_from_geonode(self):
        base_url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500"
        scraper = cloudscraper.create_scraper()
        max_retries = 3

        def fetch_page(page_url, retries=max_retries):
            for attempt in range(retries):
                try:
                    response = scraper.get(page_url, timeout=10)
                    response.raise_for_status()
                    return response.json()
                except requests.exceptions.RequestException as e:
                    print(f"Попытка {attempt + 1} для {page_url} завершилась с ошибкой: {e}")
                    if attempt == retries - 1:
                        print(f"Не удалось получить данные с {page_url} после {retries} попыток.")
                        return {}

        try:
            first_page_url = f"{base_url}&page=1&sort_by=lastChecked&sort_type=desc"
            first_page_data = fetch_page(first_page_url)

            if not first_page_data:
                return

            data = first_page_data.get('data', [])
            total_count = first_page_data.get('total', len(data))
            print(f"Всего {total_count} прокси на geonode.com")
            total_pages = (total_count // 500) + (1 if total_count % 500 > 0 else 0)
            print(f"Всего страниц {total_pages}")

            print(f"Всего прокси с первой страницы: {len(data)}")

            if data:
                self.proxies_list.extend([f"{entry.get('ip')}:{entry.get('port')}" for entry in data if
                                          entry.get('ip') and entry.get('port')])

            for number_page in range(2, total_pages + 1):
                page_url = f"{base_url}&page={number_page}&sort_by=lastChecked&sort_type=desc"
                page_data = fetch_page(page_url)
                data = page_data.get('data', [])
                for entry in data:
                    ip = entry.get('ip')
                    port = entry.get('port')
                    if ip and port:
                        self.proxies_list.append(f"{ip}:{port}")
                print(f"Страница {number_page} забрана. Всего забрано прокси: {len(self.proxies_list)}")
                cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
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
                            # обновление кэш с общим количеством прокси после загрузки.
                            cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
            print(f"Всего прокси из socks.us: {len(data)}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения прокси из  {url}: {e}")

    # Функция забора прокси из списков с github
    def get_data_from_txt(self):
        pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)'  # паттерн забора информации из текстового файла ip:port
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
                # обновление кэш с общим количеством прокси после загрузки.
                cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
                total_proxies += len(proxy_list_filtered)
        print(f"Всего прокси из txt_sources : {total_proxies}")

    # Добавленная функция для разделения списка на батчи
    def batcher(self, iterable, batch_size):
        iterator = iter(iterable)
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            yield batch

    def check_proxy_batch(self, url, timeout=5, max_retries=3, batch_size=20):
        print("Запуск проверки прокси пакетами...")
        proxies_to_check = set(self.proxies_list)
        if not proxies_to_check:
            print("Список прокси пуст. Проверка завершена.")
            return


        for batch_number, proxy_batch in enumerate(self.batcher(proxies_to_check, batch_size), start=1):
            print(f"Проверяется пакет {batch_number}, количество прокси в пакете: {len(proxy_batch)}")
            threads = []

            for proxy in proxy_batch:
                thread = Thread(target=self.check_single_proxy, args=(proxy, url, timeout, max_retries))
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

    def check_single_proxy(self, proxy, url, timeout, max_retries):
        """Функция проверки одного прокси."""
        with self.lock:
            if not cache.get('proxy_check_running', True):
                print("Остановка проверки прокси по флагу проверки")
                return

            checked_proxies_count = cache.get(self.checked_proxies_count_key, 0)
            cache.set(self.checked_proxies_count_key, checked_proxies_count + 1, timeout=None)
            print(f"Проверяется прокси {proxy}...")

        proxy_dict = {
            'http': f'socks5://{proxy}',
            'https': f'socks5://{proxy}'
        }

        for _ in range(max_retries):
            try:
                response = requests.get(url=url, headers=self.header, proxies=proxy_dict, timeout=timeout, verify=certifi.where())
                print(f"Прокси {proxy} проверено - Ответ: {response.status_code}")
                if response.ok:
                    self.check_proxy_with_proxyinformation(proxy)
                    break
            except requests.exceptions.RequestException as e:
                print(f"Ошибка проверки прокси {proxy}: {e}")
                continue

    # Функция детальной проверки прокси с помощью ProxyInformation и записи результата в БД
    def check_proxy_with_proxyinformation(self, proxy):
        checker = ProxyInformation()

        try:
            result = checker.check_proxy(proxy)
        except Exception as e:
            print(f"Error checking proxy {proxy}: {e}")
            return

        # Ensure 'status' exists and is True
        if result.get("status") is not True:
            print("Proxy status False")
            return

        # Get 'info' dictionary, and ensure it's not None
        info = result.get("info", {})
        if not info:
            print("No proxy information found")
            return

        # Check if the protocol is 'socks5'
        if info.get('protocol') != 'socks5':
            print("Proxy is not socks5")
            return


        date = datetime.today().date()
        time = datetime.today().strftime('%H:%M:%S')
        # форматирование response_time до 3 знаков после запятой
        response_time = round(info.get('responseTime', 0), 3)

        # Сохраняем результат в базу данных через сериализатор
        proxy_data = {
            'ip': info.get('ip'),
            'port': info.get('port'),
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
            print("Прокси сохранен в БД")
        else:
            print(f"Ошибка сериализатора: {serializer.errors}")
            # Дополнительная информация для отладки
            print(f"Данные для сериализатора: {proxy_data}")

    # Подсчет количества прокси и времени выполнения
    def timer(self):
        checked_proxies_count = cache.get(self.checked_proxies_count_key, 0)
        total_proxies = cache.get('total_proxies', 0)
        start_time = cache.get(self.start_time_key)
        if not start_time:
            start_time = datetime.now()
            cache.set(self.start_time_key, start_time, timeout=None)

        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        if checked_proxies_count > 0:
            average_time_per_proxy = elapsed_seconds / checked_proxies_count
            remaining_proxies = total_proxies - checked_proxies_count
            remaining_time_seconds = average_time_per_proxy * remaining_proxies

            remaining_time = timedelta(seconds=remaining_time_seconds)
            hours, remainder = divmod(remaining_time.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
        else:
            hours = minutes = seconds = 0

        return {
            "total_checked": checked_proxies_count,
            "total_proxies": total_proxies,
            "remaining_hours": int(hours),
            "remaining_minutes": int(minutes),
            "remaining_seconds": int(seconds)
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
        proxy_list = [
            {"ip": proxy.ip, "port": proxy.port, "protocol": proxy.protocol, "anonymity": proxy.anonymity,
             "country": proxy.country, "country_code": proxy.country_code}
            for proxy in proxies]

        # Вернуть список как ответ JSON
        return JsonResponse(proxy_list, safe=False)

    # Вызов функции check_proxy_batch в потоке
    @action(detail=False, methods=['post'])
    def start_proxy_check(self, request):
        print("Запуск проверки прокси пакетами...")

        self.get_data_from_geonode()
        self.get_data_from_socksus()
        self.get_data_from_txt()
        cache.set('proxy_check_running', True, timeout=None)

        if not cache.get(self.start_time_key):
            cache.set(self.start_time_key, datetime.now(), timeout=None)

        cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)

        # Запуск проверки в потоке
        self.check_proxy_thread = Thread(target=self.check_proxy_batch, args=("https://httpbin.org/ip",))
        self.check_proxy_thread.start()

        if self.check_proxy_thread.is_alive():
            print("Поток проверки работает.")
        else:
            print("Поток проверки не работает.")

        return JsonResponse({'status': 'Proxy check started'})

    # урл досрочной остановки проверки прокси
    @action(detail=False, methods=['post'])
    def stop_proxy_check(self, request):
        print("Остановка проверки прокси...")
        cache.set('proxy_check_running', False)

        cache.set(self.checked_proxies_count_key, 0)
        cache.set('total_proxies', 0)
        cache.delete(self.start_time_key)

        return JsonResponse({'status': 'Proxy check stopped'})

    # вызов таблицы прокси постранично
    def list(self, request, *args, **kwargs):
        # Безопасное получение параметра «draw», значение по умолчанию 1, если он недействителен или не определен
        # «draw», recordsTotal, recordsFiltered , раньше нужен был для TableData фронта, потом переделал, но
        try:
            draw = int(request.GET.get("draw", 1))
        except ValueError:
            draw = 1  # По умолчанию 1, если значение «не определено» или недействительно.

        # Фильтрация и разбиение на страницы набора запросов с явным упорядочиванием
        queryset = self.filter_queryset(self.get_queryset()).order_by(
            'id')  # Убедиться, что сортировка выполнена по «id» или другому полю

        # логика пагинации
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "draw": draw,
                "recordsTotal": self.queryset.count(),  # Всего записей в базе данных
                "recordsFiltered": self.queryset.count(),  # отрегулировать, если применяется фильтрация
                "data": serializer.data,
            })

        # Если пагинация не применяется, вернуть все записи (не разбитые на страницы)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "draw": draw,
            "recordsTotal": self.queryset.count(),
            "recordsFiltered": self.queryset.count(),  # отрегулировать, если применяется фильтрация
            "data": serializer.data,

        })


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
        return render(request, 'checker/home.html')


# Представление для страницы "О нас"
class AboutView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/about.html')


# Представление для страницы FAQ
class FaqView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/faq.html')
