
# Create your models here.

from django.db import models

class CheckedProxy(models.Model):
    ip = models.CharField(max_length=15)
    port = models.IntegerField()
    country = models.CharField(max_length=100, blank=True, null=True)
    anonymity = models.CharField(max_length=100, blank=True, null=True)
    status = models.BooleanField()
    date_checked = models.DateField()
    time_checked = models.TimeField()

    def __str__(self):
        return f"{self.ip}:{self.port}"

