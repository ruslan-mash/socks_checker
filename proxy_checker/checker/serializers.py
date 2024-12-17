from rest_framework import serializers
from .models import CheckedProxy

class CheckedProxySerializer(serializers.ModelSerializer):
    ip = serializers.CharField(label="ip", max_length=16)
    port = serializers.IntegerField(label="Порт")
    protocol = serializers.CharField(label="Протокол", max_length=16)
    response_time = serializers.FloatField(label="Время ответа")
    anonymity = serializers.CharField(label="Анонимность", max_length=16)
    country = serializers.CharField(label="Страна", max_length=60)
    country_code = serializers.CharField(label="Код страны", max_length=2)
    date_checked = serializers.DateField(label="Дата проверки")
    time_checked = serializers.TimeField(label="Время проверки")

    class Meta:
        model = CheckedProxy
        fields = ("ip", "port", "protocol", "response_time", "anonymity", "country",  "country_code", "date_checked", "time_checked")


