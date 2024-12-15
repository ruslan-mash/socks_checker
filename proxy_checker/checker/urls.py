from django.urls import path
from .views import proxy_list

urlpatterns = [
    path('proxies/', proxy_list, name='proxy_list'),
]
