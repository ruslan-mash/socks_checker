from django.urls import path
from . import views

urlpatterns = [
    path('check/', views.StartCheckedProxyView(list), name='check_proxy')
    path('check/stop/', views.StopCheckedProxyView(list), name='stop_check')

]

