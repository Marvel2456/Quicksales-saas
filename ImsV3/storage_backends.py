from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class CloudflareR2MediaStorage(S3Boto3Storage):
    """
    Cloudflare R2 S3-compatible media storage backend.
    """
    location = 'media'
    file_overwrite = False
    default_acl = None  # Cloudflare R2 does not use S3 ACLs
    querystring_auth = False
    signature_version = 's3v4'

    def __init__(self, *args, **kwargs):
        kwargs['bucket_name'] = getattr(settings, 'R2_BUCKET_NAME', '')
        kwargs['endpoint_url'] = getattr(settings, 'R2_ENDPOINT_URL', '')
        kwargs['access_key'] = getattr(settings, 'R2_ACCESS_KEY_ID', '')
        kwargs['secret_key'] = getattr(settings, 'R2_SECRET_ACCESS_KEY', '')
        
        custom_domain = getattr(settings, 'R2_CUSTOM_DOMAIN', '').strip()
        if custom_domain:
            # Strip protocol if present as S3Boto3Storage expects bare host or adds scheme
            domain = custom_domain.replace('https://', '').replace('http://', '').rstrip('/')
            kwargs['custom_domain'] = domain
            
        super().__init__(*args, **kwargs)
