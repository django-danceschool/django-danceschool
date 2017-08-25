from django.views.generic import ListView
from django.utils import timezone

from braces.views import PermissionRequiredMixin

from .models import BannedPerson


class BanListView(PermissionRequiredMixin, ListView):
    template_name = 'banlist/banlist.html'
    permission_required = 'banlist.view_banlist'
    queryset = BannedPerson.objects.exclude(expirationDate__lte=timezone.now()).filter(disabled=False)
