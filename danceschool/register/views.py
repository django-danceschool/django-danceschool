from django.utils.translation import gettext_lazy as _
from django.http import Http404
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
from django.views.generic import TemplateView

from braces.views import PermissionRequiredMixin
from datetime import datetime

from danceschool.core.constants import getConstant, REG_VALIDATION_STR
from danceschool.core.utils.timezone import ensure_localtime
from danceschool.core.models import Event, Series, PublicEvent
from danceschool.core.mixins import (
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin, ReferralInfoMixin,
)
from danceschool.core.registries import extras_templates_registry

from .forms import CustomerGuestAutocompleteForm
from .models import Register


class PointOfSaleRegisterView(
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
    PermissionRequiredMixin, TemplateView
):
    permission_required = 'core.accept_door_payments'
    template_name = 'register/register.html'

    # For Restricting to this day's register only.
    today = False

    def get_allEvents(self):
        '''
        Exclude hidden and link-only events by default, as well as private
        events, etc.  Additional restrictions are made on a per-plugin basis.
        '''

        if not hasattr(self, 'allEvents'):
            self.allEvents = Event.objects.filter(
                Q(instance_of=PublicEvent) |
                Q(instance_of=Series)
            ).annotate(
                **self.get_annotations()
            ).exclude(
                Q(status=Event.RegStatus.hidden) |
                Q(status=Event.RegStatus.regHidden) |
                Q(status=Event.RegStatus.linkOnly)
            ).order_by(*self.get_ordering()).distinct()

        return self.allEvents

    def get_context_data(self, **kwargs):
        '''
        Add the event and series listing data.  If If "today" is specified,
        then use today instead of passed arguments.
        '''

        if self.today:
            today = ensure_localtime(
                datetime.now()
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            year, month, day = (today.year, today.month, today.day,)
        else:
            try:
                year = int(self.kwargs.get('year'))
                month = int(self.kwargs.get('month'))
                day = int(self.kwargs.get('day'))
                today = datetime(year, month, day)
            except (TypeError, ValueError):
                raise Http404(_('Invalid date.'))

        try:
            register = Register.objects.get(slug=self.kwargs.get('slug'), enabled=True)
        except ObjectDoesNotExist:
            raise Http404(_('Invalid register.'))

        context = {
            'customerSearchForm': CustomerGuestAutocompleteForm(date=today),
            'showDescriptionRule': getConstant('registration__showDescriptionRule') or 'all',
            'year': year,
            'month': month,
            'day': day,
            'today': today,
            'register': register,
            'allEvents': self.get_allEvents(),
            'extras_templates_registry': extras_templates_registry,
        }
        context.update(kwargs)

        # Update the site session data so that registration processes know to send
        # return links to the registration page.  set_return_page() is in SiteHistoryMixin.
        self.set_return_page('registerView', pageName=_('Registration'), **self.kwargs)

        return super().get_context_data(**context)


class PublicRegisterView(
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
    ReferralInfoMixin, TemplateView
):
    '''
    Public-facing registration page backed by a CMS alias placeholder
    ('public_register_content').  Unlike PointOfSaleRegisterView, this requires no
    special permissions and respects the registration__registrationEnabled
    site setting.  Staff with core.accept_door_payments can still access
    the page when registration is disabled, and may toggle a door-registration
    checkbox (ephemeral, client-side only) to enable payAtDoor mode.

    Referral/voucher codes are supported via the ?referral= query parameter
    (handled by ReferralInfoMixin) without a separate redirect view.
    '''
    template_name = 'register/public_register.html'

    def get_allEvents(self):
        if not hasattr(self, 'allEvents'):
            self.allEvents = Event.objects.filter(
                Q(instance_of=PublicEvent) |
                Q(instance_of=Series)
            ).annotate(
                **self.get_annotations()
            ).exclude(
                Q(status=Event.RegStatus.hidden) |
                Q(status=Event.RegStatus.regHidden) |
                Q(status=Event.RegStatus.linkOnly)
            ).order_by(*self.get_ordering()).distinct()
        return self.allEvents

    def dispatch(self, request, *args, **kwargs):
        if (
            not getConstant('registration__registrationEnabled') and
            not request.user.has_perm('core.accept_door_payments')
        ):
            return redirect('registrationOffline')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            'allEvents': self.get_allEvents(),
            'showDescriptionRule': getConstant('registration__showDescriptionRule') or 'all',
            'registrationEnabled': getConstant('registration__registrationEnabled'),
        }
        context.update(kwargs)
        self.set_return_page('publicRegistration', pageName=_('Registration'))
        return super().get_context_data(**context)
