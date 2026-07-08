from django.contrib import admin

from .models import DesktopDownload

@admin.register(DesktopDownload)
class DesktopDownloadAdmin(admin.ModelAdmin):
    list_display = ('platform', 'downloaded_at', 'ip_address')
    list_filter = ('platform', 'downloaded_at')
    date_hierarchy = 'downloaded_at'
    readonly_fields = ('platform', 'downloaded_at', 'ip_address')
