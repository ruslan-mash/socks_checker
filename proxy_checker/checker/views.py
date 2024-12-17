from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from .models import CheckedProxy
from .serializers import CheckedProxySerializer

class CheckedProxyView(viewsets.ModelViewSet):
    queryset = CheckedProxy.objects.all()
    permission_classes = [AllowAny]
    serializer_class = CheckedProxySerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return render(request, 'checker/proxy_list.html', {'proxies': serializer.data})

class StartCheckedProxyView:
    pass

class StopCheckedProxyView:
    pass


