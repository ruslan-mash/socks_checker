from django.http import HttpResponse
from rest_framework import viewsets
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
from rest_framework.pagination import PageNumberPagination
from itertools import islice
from bs4 import BeautifulSoup
import base64
from concurrent.futures import ThreadPoolExecutor
from colorlog import ColoredFormatter
import json
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from g4f import Client
from django.db.models import F, IntegerField
from django.db.models.functions import Cast
from django.http import JsonResponse
from rest_framework.decorators import action
from .models import CheckedProxy
import logging

# Настройка логирования
formatter = ColoredFormatter(
    "%(log_color)s%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    reset=True,
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    },
    secondary_log_colors={},
    style='%'
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


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
        self.txt_sources = [
            "https://spys.me/socks.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
            "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt",
            "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
            "https://www.proxy-list.download/api/v1/get?type=socks5&anon=elite",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5.txt",
            "https://vakhov.github.io/fresh-proxy-list/socks5.txt",
            "https://raw.githubusercontent.com/fyvri/fresh-proxy-list/archive/storage/classic/socks5.txt",
        ]
        self.lock = Lock()  # Блокировка для обеспечения безопасности потока при изменении proxy_list
        self.checked_proxies_count_key = "checked_proxies_count"
        self.start_time_key = "start_time"

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
                    logger.error(f"Попытка {attempt + 1} для {page_url} завершилась с ошибкой: {e}")
                    if attempt == retries - 1:
                        logger.error(f"Не удалось получить данные с {page_url} после {retries} попыток.")
                        return {}

        try:
            first_page_url = f"{base_url}&page=1&sort_by=lastChecked&sort_type=desc"
            first_page_data = fetch_page(first_page_url)

            if not first_page_data:
                return

            data = first_page_data.get('data', [])
            total_count = first_page_data.get('total', len(data))
            logger.info(f"Всего {total_count} прокси на geonode.com")
            total_pages = (total_count // 500) + (1 if total_count % 500 > 0 else 0)
            logger.info(f"Всего страниц {total_pages}")

            logger.info(f"Всего прокси с первой страницы: {len(data)}")

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
                logger.info(f"Страница {number_page} забрана. Всего забрано прокси: {len(self.proxies_list)}")
                cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения информации из {base_url}: {e}")

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
                            cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
            logger.info(f"Всего прокси из socks.us: {len(data)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения прокси из  {url}: {e}")

    # Функция забора прокси из proxyfreeonly.com

    def get_data_from_proxyfreeonly(self):
        url = "https://proxyfreeonly.com/download/FreeProxyList.json"
        filtered_proxies = 0  # Счетчик добавленных прокси

        try:
            response = requests.get(url=url, headers=self.header, timeout=10)
            response.raise_for_status()  # Проверка, нет ли ошибки HTTP
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения прокси из {url}: {e}")
            return

        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    ip = entry.get('ip')
                    port = entry.get('port')
                    anonymity = entry.get('anonymityLevel', '').lower()
                    protocols = entry.get('protocols', [])

                    # Фильтрация: только socks5 + elite
                    if ip and port and anonymity == "elite" and "socks5" in protocols:
                        self.proxies_list.append(f"{ip}:{port}")
                        filtered_proxies += 1

            # Обновляем кэш с количеством прокси
            cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
            logger.info(f"Всего подходящих прокси (socks5 + elite) из proxyfreeonly.com: {filtered_proxies}")

    # Функция забора прокси из advanced.name
    def get_data_from_advanced_name(self):
        url = "https://advanced.name/freeproxy?type=socks5"
        an_proxies = 0  # Счетчик добавленных прокси

        try:
            response = requests.get(url, headers=self.header, timeout=10)
            response.raise_for_status()  # Проверка, нет ли ошибки HTTP
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения прокси из {url}: {e}")
            return

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Поиск всех строк с прокси
            rows = soup.find_all("tr")
            for row in rows:
                ip_td = row.find("td", attrs={"data-ip": True})
                port_td = row.find("td", attrs={"data-port": True})

                if ip_td and port_td:
                    # Извлекаем текстовые данные
                    ip = ip_td.get_text(strip=True)
                    port = port_td.get_text(strip=True)

                    # Если IP и порт закодированы в Base64 — декодируем
                    if ip_td.has_attr("data-ip"):
                        ip = base64.b64decode(ip_td["data-ip"]).decode("utf-8")
                    if port_td.has_attr("data-port"):
                        port = base64.b64decode(port_td["data-port"]).decode("utf-8")

                    proxy = f"{ip}:{port}"
                    self.proxies_list.append(proxy)
                    an_proxies += 1

            # Обновляем кэш с количеством прокси
            cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
            logger.info(f"Всего прокси из advanced.name: {an_proxies}")

    # Функция забора прокси из списков с github
    def get_data_from_txt(self):
        pattern = r'(\d+\.\d+\.\d+\.\d+:\d+)'  # паттерн забора информации из текстового файла ip:port
        total_proxies = 0
        for url in self.txt_sources:
            try:
                response = requests.get(url=url, headers=self.header)
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка получения прокси из {url}: {e}")
                continue
            if response.ok:
                proxy_list = response.text.splitlines()
                proxy_list_filtered = re.findall(pattern, "\n".join(proxy_list))
                self.proxies_list.extend(proxy_list_filtered)
                cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)
                total_proxies += len(proxy_list_filtered)
        logger.info(f"Всего прокси из txt_sources : {total_proxies}")

    # Добавленная функция для разделения списка на батчи
    def batcher(self, iterable, batch_size):
        iterator = iter(iterable)
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            yield batch

    def check_proxy_batch(self, url, timeout=5, max_retries=3, batch_size=20):
        logger.info("Запуск проверки прокси пакетами...")
        proxies_to_check = list(set(self.proxies_list))  # Убираем дубликаты

        if not proxies_to_check:
            logger.info("Список прокси пуст. Проверка завершена.")
            return

        # Разделение прокси на батчи
        for batch in self.batcher(proxies_to_check, batch_size):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self.check_single_proxy, proxy, url, timeout, max_retries) for proxy in
                           batch]
                for future in futures:
                    future.result()  # Ожидание завершения всех потоков в батче

    def check_single_proxy(self, proxy, url, timeout, max_retries):
        """Функция проверки одного прокси."""
        with self.lock:
            if not cache.get('proxy_check_running', True):
                logger.info("Остановка проверки прокси по флагу проверки")
                return

            checked_proxies_count = cache.get(self.checked_proxies_count_key, 0)
            cache.set(self.checked_proxies_count_key, checked_proxies_count + 1, timeout=None)
            logger.info(f"Проверяется прокси {proxy}...")

        proxy_dict = {
            'http': f'socks5://{proxy}',
            'https': f'socks5://{proxy}'
        }

        for _ in range(max_retries):
            try:
                response = requests.get(url=url, headers=self.header, proxies=proxy_dict, timeout=timeout,
                                        verify=certifi.where())
                logger.info(f"Прокси {proxy} проверено - Ответ: {response.status_code}")
                if response.ok:
                    self.check_proxy_with_proxyinformation(proxy)
                    break
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка проверки прокси {proxy}: {e}")
                continue

    def check_proxy_with_proxyinformation(self, proxy):
        """Детальная проверка прокси с помощью ProxyInformation."""
        checker = ProxyInformation()

        try:
            result = checker.check_proxy(proxy)
        except Exception as e:
            logger.error(f"Error checking proxy {proxy}: {e}")
            return

        if result.get("status") is not True:
            logger.error("Proxy status False")
            return

        info = result.get("info", {})
        if not info:
            logger.error("No proxy information found")
            return

        if info.get('protocol') != 'socks5':
            logger.error("Proxy is not socks5")
            return

        date = datetime.today().date()
        time = datetime.today().strftime('%H:%M:%S')
        response_time = round(info.get('responseTime', 0), 3)

        # Проверка репутации IP
        reputation, score = self.check_ip_reputation_scamalytics(info.get('ip'))

        # Данные для обновления или создания записи
        proxy_data = {
            'ip': info.get('ip'),
            'port': info.get('port'),
            'protocol': info.get('protocol'),
            'response_time': response_time,
            'anonymity': info.get('anonymity', ''),
            'country': info.get('country', ''),
            'country_code': info.get('country_code', ''),
            'date_checked': date,
            'time_checked': time,
            'reputation': reputation if reputation else None,
            'score': score if score else None
        }

        self.save_proxy_to_db(proxy_data)

    def check_ip_reputation_scamalytics(self, ip_address):
        """Проверка репутации IP с помощью scamalytics.com."""
        url = f"https://scamalytics.com/ip/{ip_address}"
        response = requests.get(url, headers=self.header)

        reputation = None
        score = None

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            risk_level = soup.find("div", class_="panel_title high_risk")
            risk_score = soup.find("div", class_="score")

            if risk_level:
                reputation = risk_level.text.strip()
                logger.info(f"Репутация IP {ip_address}: {reputation}")

            if risk_score:
                score_match = re.search(r"\d+", risk_score.text)  # Исправлено
                if score_match:
                    score = score_match.group()
                    logger.info(f"Оценка мошенничества {ip_address}: {score}")

        else:
            logger.error(f"Ошибка: {response.status_code}")

        return reputation, score  # Теперь возвращаем ДВА значения

    def save_proxy_to_db(self, proxy_data):
        """Сохранение или обновление прокси в базе данных."""
        existing_proxy, created = CheckedProxy.objects.update_or_create(
            ip=proxy_data['ip'], port=proxy_data['port'],
            defaults=proxy_data
        )

        serializer = CheckedProxySerializer(existing_proxy, data=proxy_data, partial=True)

        if serializer.is_valid():
            serializer.save()
            logger.info("Прокси сохранен/обновлен в БД")
        else:
            logger.error(f"Ошибка сериализатора: {serializer.errors}")
            logger.info(f"Данные для сериализатора: {proxy_data}")

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
        logger.info("Генерация txt листа...")
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
        logger.info("Генерация json листа...")
        # Запросить базу данных для всех допустимых прокси
        proxies = CheckedProxy.objects.all()

        # Создать список прокси
        proxy_list = [
            {"ip": proxy.ip, "port": proxy.port, "protocol": proxy.protocol, "anonymity": proxy.anonymity,
             "country": proxy.country, "country_code": proxy.country_code, "reputation": proxy.reputation}
            for proxy in proxies]

        # Вернуть список как ответ JSON
        return JsonResponse(proxy_list, safe=False)

    # урл для генерации JSON элитных прокси
    @action(detail=False, methods=['get'])
    def generate_elite_json(self, request):
        logger.info("Генерация элитного json листа...")
        try:
            # Приводим поле `score` к целому числу и фильтруем по нужным критериям
            proxies = CheckedProxy.objects.annotate(
                score_int=Cast('score', IntegerField())  # Приводим строковое поле 'score' к типу IntegerField
            ).filter(
                anonymity="Elite",
                score_int__gte=0,  # score >= 0
                score_int__lte=40  # score <= 40
            )

            # Если нет подходящих прокси
            if not proxies:
                return JsonResponse({"error": "Нет подходящих прокси"}, status=404)

            # Создаем список прокси
            proxy_list = [
                {"ip": proxy.ip, "port": proxy.port, "protocol": proxy.protocol,
                 "anonymity": proxy.anonymity, "country": proxy.country,
                 "country_code": proxy.country_code, "reputation": proxy.reputation, "score": proxy.score}
                for proxy in proxies
            ]

            # Возвращаем список как ответ JSON
            return JsonResponse(proxy_list, safe=False)

        except Exception as e:
            logger.error(f"Ошибка при генерации JSON: {e}")
            return JsonResponse({"error": "Ошибка при обработке запроса"}, status=500)

    # Вызов функции check_proxy_batch в потоке
    @action(detail=False, methods=['post'])
    def start_proxy_check(self, request):
        logger.info("Запуск проверки прокси пакетами...")

        self.get_data_from_proxyfreeonly()
        self.get_data_from_advanced_name()
        self.get_data_from_txt()
        self.get_data_from_geonode()
        self.get_data_from_socksus()

        cache.set('proxy_check_running', True, timeout=None)

        if not cache.get(self.start_time_key):
            cache.set(self.start_time_key, datetime.now(), timeout=None)

        cache.set('total_proxies', len(set(self.proxies_list)), timeout=None)

        # Запуск проверки в потоке
        self.check_proxy_thread = Thread(target=self.check_proxy_batch, args=("https://www.wikipedia.org/",))
        self.check_proxy_thread.start()

        if self.check_proxy_thread.is_alive():
            logger.info("Поток проверки работает.")
        else:
            logger.error("Поток проверки не работает.")

        return JsonResponse({'status': 'Proxy check started'})

    # урл досрочной остановки проверки прокси
    @action(detail=False, methods=['post'])
    def stop_proxy_check(self, request):
        logger.info("Остановка проверки прокси...")
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
            '-id')  # Убедиться, что сортировка выполнена по «id» или другому полю

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


# удаление из БД записей старше 48 часов (старые бесполезны)
class CleanOldRecordsView(APIView):

    def delete(self, request, *args, **kwargs):
        try:
            threshold_date = datetime.today() - timedelta(days=2)  # Данные старше 2 дня
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


# Представление для страницы AI
class ArtificialIntelligence(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'checker/ai.html')


class AIChat:
    """Класс чат-бота, использующего g4f.client для генерации ответов"""

    def __init__(self, provider="DDG", model="gpt-4o-mini", temperature=0.7):
        self.client = Client()
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.web_search = True

    def generate_answer(self, question: str) -> str:
        """Генерирует ответ на заданный вопрос"""
        if not question.strip():
            return "Пожалуйста, введите корректный вопрос."

        try:
            response = self.client.chat.completions.create(
                provider=self.provider,
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": "Ты бот, отвечающий на вопросы про сетевые технологии,прокси,парсинг и скрапинг сайтов,обход блокировок,анонимность в сети Интенет. Не отвечаешь на политические темы"},
                    {"role": "user", "content": question}
                ],
                temperature=self.temperature,
                web_search=self.web_search

            )
            answer = response.choices[0].message.content
            logging.info("Ответ успешно сгенерирован.")
            return answer
        except Exception as e:
            logging.error(f"Ошибка при генерации ответа: {e}")
            return "Ошибка при генерации ответа."


@method_decorator(csrf_exempt, name="dispatch")
class ChatBotView(View):
    """Класс представления для обработки запросов к боту"""

    def post(self, request, *args, **kwargs):
        """Обрабатывает POST-запрос, отправляет сообщение в AIChat и возвращает ответ"""
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "").strip()

            if not user_message:
                return JsonResponse({"response": "Пожалуйста, введите вопрос."}, status=400)

            bot = AIChat()
            bot_response = bot.generate_answer(user_message)

            return JsonResponse({"response": bot_response})
        except Exception as e:
            logging.error(f"Ошибка в обработке запроса: {e}")
            return JsonResponse({"response": "Ошибка при обработке запроса"}, status=500)

    def get(self, request, *args, **kwargs):
        """Возвращает сообщение, если кто-то пытается обратиться GET-запросом"""
        return JsonResponse({"response": "Метод GET не поддерживается"}, status=405)
