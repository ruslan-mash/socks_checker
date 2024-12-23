from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProxyViewSet, proxy_list, about, faq

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'proxies', ProxyViewSet, basename='proxy')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),
    path('proxy-list/', proxy_list, name='proxy_list'),
    path('about/', about, name='about'),
    path('faq/', faq, name='faq'),
]

# Additional URL patterns for custom actions in ProxyViewSet
urlpatterns += [
    path('start-proxy-check/', ProxyViewSet.as_view({'post': 'start_proxy_check'}), name='start_proxy_check'),
    path('stop-proxy-check/', ProxyViewSet.as_view({'post': 'stop_proxy_check'}), name='stop_proxy_check'),
    path('generate-proxy-list/', ProxyViewSet.as_view({'get': 'generate_proxy_list'}), name='generate_proxy_list'),
    path('timer/', ProxyViewSet.as_view({'get': 'timer'}), name='timer'),
]
