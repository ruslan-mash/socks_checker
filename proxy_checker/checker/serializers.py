from rest_framework import serializers
from .models import CheckedProxy

# class CheckedProxySerializer(serializers.ModelSerializer):
#     ip = serializers.IPAddressField(label="ip", max_length=16)
#     port = serializers.IntegerField(label="Порт")
#     protocol = serializers.CharField(label="Протокол", max_length=8)
#     response_time = serializers.FloatField(label="Время ответа")
#     anonymity = serializers.CharField(label="Анонимность", max_length=16)
#     country = serializers.CharField(label="Страна", max_length=60)
#     country_code = serializers.CharField(label="Код страны", max_length=2)
#     date_checked = serializers.DateField(label="Дата проверки", input_formats=['%d-%m-%Y'])
#     time_checked = serializers.TimeField(label="Время проверки")

class CheckedProxySerializer(serializers.ModelSerializer):
    # Overriding the to_representation method to customize the output format
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Format the 'date_checked' field to 'DD-MM-YYYY' in the serialized response
        if 'date_checked' in representation:
            representation['date_checked'] = instance.date_checked.strftime('%d-%m-%Y')
        return representation



    class Meta:
        model = CheckedProxy
        fields = ("ip", "port", "protocol", "response_time", "anonymity", "country",  "country_code", "date_checked", "time_checked")


