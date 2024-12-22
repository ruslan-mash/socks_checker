from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'proxy', views.ProxyViewSet, basename='proxy')

urlpatterns = [
    path('proxy-list/', views.proxy_list, name='proxy_list'),  # Proxy list page (this should be a regular view)
    path('start/', views.ProxyViewSet.as_view({'get': 'start_proxy_check'}), name='start_proxy_check'),
    path('stop/', views.ProxyViewSet.as_view({'get': 'stop_proxy_check'}), name='stop_proxy_check'),
    path('generate_proxy_list/', views.ProxyViewSet.as_view({'get': 'generate_proxy_list'}),
         name='generate_proxy_list'),
    path('about/', views.about, name='about'),
    path('faq/', views.faq, name='faq'),
    ]
