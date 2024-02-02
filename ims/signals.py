# from ims.models import Sale
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Event, Sale

# @receiver(post_save, sender=Sale)
# def create_event(sender, instance, created, *args, **kwargs):

#     if created:
#         Event.objects.create(sale=instance)

# @receiver(post_save, sender=Sale)
# def save_event(sender, instance, created, *args, **kwargs):

#     if created == False:
#         instance.event.save()
