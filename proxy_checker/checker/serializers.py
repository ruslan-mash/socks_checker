from rest_framework import serializers
from .models import CheckedProxy




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
        fields = (
        "ip", "port", "protocol", "response_time", "anonymity", "country", "country_code", "reputation", "download", "date_checked",
        "time_checked")
