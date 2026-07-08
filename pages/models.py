from django.db import models

class DesktopDownload(models.Model):
    PLATFORM_CHOICES = [
        ('windows', 'Windows'),
        ('mac', 'macOS'),
    ]
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    downloaded_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.get_platform_display()} Download - {self.downloaded_at}"
