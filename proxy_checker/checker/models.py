from django.db import models


class CheckedProxy(models.Model):
    ip = models.CharField(max_length=45)
    port = models.IntegerField()
    protocol = models.CharField(max_length=10, default='socks5')
    response_time = models.FloatField(default=0.0)
    anonymity = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    country_code = models.CharField(max_length=10, default='N/A')
    date_checked = models.DateField()
    time_checked = models.TimeField()

    def __str__(self):
        return f"{self.ip}:{self.port}"

    class Meta:
        verbose_name = "Прокси"
        verbose_name_plural = "Прокси"
