from django.shortcuts import render
from .models import CheckedProxy
from django.http import JsonResponse
from .proxy_validator import ProxyValidator
import time
import threading

# Хранилище для текущего процесса проверки
proxy_validator = None

def proxy_list(request):
    # Получаем все проверенные прокси из базы данных
    proxies = CheckedProxy.objects.all()
    context = {
        'proxies': proxies
    }
    return render(request, 'checker/proxy_list.html', context)

def start_proxy_check(request):
    global proxy_validator
    if proxy_validator and proxy_validator.running:
        return JsonResponse({'status': 'error', 'message': 'Proxy check is already running'})

    proxies_list = [
        "38.55.195.177:48006", "138.68.81.7:13983", "68.178.174.208:34236",
        "51.75.126.150:19578"
    ]
    checked_socks = []
    start_time = time.time()
    header = {'User-Agent': 'Mozilla/5.0'}
    txt_sources = [
        "https://spys.me/socks.txt", "https://www.proxy-list.download/api/v1/get?type=socks5&anon=elite"
    ]

    proxy_validator = ProxyValidator(proxies_list, checked_socks, start_time, header, txt_sources)
    thread = threading.Thread(target=proxy_validator.run)
    thread.start()

    return JsonResponse({'status': 'success', 'message': 'Proxy check started'})

def stop_proxy_check(request):
    global proxy_validator
    if not proxy_validator or not proxy_validator.running:
        return JsonResponse({'status': 'error', 'message': 'No proxy check is running'})

    proxy_validator.stop()
    return JsonResponse({'status': 'success', 'message': 'Proxy check stopped'})

def proxy_status(request):
    if proxy_validator and proxy_validator.running:
        elapsed_time = time.time() - proxy_validator.start_time
        remaining_time = proxy_validator.estimated_time_left()
        total_checked = len(proxy_validator.checked_socks)
        return JsonResponse({
            'status': 'running',
            'elapsed_time': round(elapsed_time, 2),
            'remaining_time': round(remaining_time, 2),
            'total_checked': total_checked,
        })
    else:
        return JsonResponse({'status': 'idle'})

def generate_proxy_list(request):
    proxies = CheckedProxy.objects.all()
    proxy_list = "\n".join([f"{proxy.ip}:{proxy.port}" for proxy in proxies])
    response = HttpResponse(proxy_list, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="proxies.txt"'
    return response

#это для таймера
