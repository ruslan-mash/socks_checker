from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProxyViewSet, CleanOldRecordsView, ProxyListView, AboutView, FaqView

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'proxies', ProxyViewSet, basename='proxy')

urlpatterns = [
    path('', include(router.urls)),
    path('start-proxy-check/', ProxyViewSet.as_view({'post': 'start_proxy_check'}), name='start_proxy_check'),
    path('stop-proxy-check/', ProxyViewSet.as_view({'post': 'stop_proxy_check'}), name='stop_proxy_check'),
    path('generate-txt-list/', ProxyViewSet.as_view({'get': 'generate_txt_list'}), name='generate_txt_list'),
    path('generate-json-list/', ProxyViewSet.as_view({'get': 'generate_json_list'}), name='generate_json_list'),
    path('generate_elite_json/', ProxyViewSet.as_view({'get': 'generate_elite_json'}), name='generate_elite_json'),
    path('timer/', ProxyViewSet.as_view({'get': 'get_timer'}), name='get_timer'),
    path('clean-old-records/', CleanOldRecordsView.as_view(), name='clean_old_records'),
    path('home/', ProxyListView.as_view(), name='home'),
    path('about/', AboutView.as_view(), name='about'),
    path('faq/', FaqView.as_view(), name='faq'),
]
