from rest_framework import serializers
from .models import CheckedProxy



class CheckedProxySerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if 'date_checked' in representation:
            representation['date_checked'] = instance.date_checked.strftime('%d-%m-%Y')
        return representation

    class Meta:
        model = CheckedProxy
        fields = (
        "ip", "port", "protocol", "response_time", "anonymity", "country", "country_code", "reputation", "score", "date_checked",
        "time_checked")
