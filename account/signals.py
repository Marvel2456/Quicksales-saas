from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Branch, Organization


@receiver(post_save, sender=Branch)
def auto_set_default_branch(sender, instance, created, **kwargs):
    """
    When a new branch is created, if the organization has no default_branch
    yet (e.g. this is their first branch), set it automatically.
    """
    if created:
        org = instance.organization
        if org and org.default_branch is None:
            Organization.objects.filter(pk=org.pk).update(default_branch=instance)


@receiver(post_delete, sender=Branch)
def reassign_default_branch_on_delete(sender, instance, **kwargs):
    """
    After a branch is deleted, if the org's default_branch is now None
    and only one branch remains, auto-assign it.
    """
    org = instance.organization
    if org:
        org.refresh_from_db()
        if org.default_branch is None:
            remaining = Branch.objects.filter(organization=org)
            if remaining.count() == 1:
                Organization.objects.filter(pk=org.pk).update(default_branch=remaining.first())
