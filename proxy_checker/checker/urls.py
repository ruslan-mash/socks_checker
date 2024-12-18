from django.urls import path
from . import views

urlpatterns = [
    path('', views.proxy_list, name='proxy_list'),  # Главная страница с таблицей прокси
    path('start/', views.start_proxy_check, name='start_proxy_check'),
    path('stop/', views.stop_proxy_check, name='stop_proxy_check'),
    path('generate_proxy_list/', views.generate_proxy_list, name='generate_proxy_list'),
]



