from django.shortcuts import render

# Create your views here.

from django.shortcuts import render
from .models import CheckedProxy  # Если нужно загрузить данные

def proxy_list(request):
    proxies = CheckedProxy.objects.all()  # Пример, как получить данные
    return render(request, 'checker/proxy_list.html', {'proxies': proxies})


