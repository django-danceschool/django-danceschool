import re

from django.contrib import messages
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
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
)
from danceschool.core.registries import extras_templates_registry
from danceschool.core.signals import check_voucher
from danceschool.core.classreg import clear_reg_cart

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

    def dispatch(self, request, *args, **kwargs):
        # Always start with a clean registration session so that a previous
        # customer's cart/invoice data cannot bleed into the next transaction.
        if REG_VALIDATION_STR in request.session:
            del request.session[REG_VALIDATION_STR]
            request.session.modified = True
        return super().dispatch(request, *args, **kwargs)

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
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin, TemplateView
):
    '''
    Public-facing registration page backed by a CMS alias placeholder
    ('public_register_content').  Unlike PointOfSaleRegisterView, this requires no
    special permissions and respects the registration__registrationEnabled
    site setting.  Staff with core.accept_door_payments can still access
    the page when registration is disabled, and may toggle a door-registration
    checkbox (ephemeral, client-side only) to enable payAtDoor mode.

    Referral/voucher codes are supported via the ?referral= query parameter or
    the public/referral/<voucher_id>/ URL pattern.  Valid codes are stored
    directly in the cart session data as discount_code; invalid codes produce a
    warning message.  Marketing IDs (?id= or public/id/<marketing_id>/) are
    stored in session data for later use.
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

    def get(self, request, *args, **kwargs):
        voucher_id = kwargs.pop('voucher_id', None)
        marketing_id = kwargs.pop('marketing_id', None)

        # GET parameters are also usable, but URL kwargs take precedence.
        if not voucher_id:
            voucher_id = request.GET.get('referral', None)
        if not marketing_id:
            marketing_id = request.GET.get('id', None)

        # Ignore IDs that contain disallowed characters.
        pattern = re.compile(r'^[a-zA-Z\-_0-9]+$')
        if voucher_id and not pattern.match(voucher_id):
            voucher_id = None
        if marketing_id and not pattern.match(marketing_id):
            marketing_id = None

        if marketing_id:
            reg_session = request.session.setdefault(REG_VALIDATION_STR, {})
            reg_session['marketing_id'] = marketing_id
            request.session.modified = True

        if voucher_id:
            responses = check_voucher.send(
                sender=self.__class__,
                voucherId=voucher_id,
                cart_items=[],
                customer=None,
                validateCustomer=False,
                invoice=None,
                payAtDoor=False,
            )
            results = [r[1] for r in responses if len(r) > 1 and r[1]]
            result = results[0] if results else {}

            if result.get('status') == 'valid':
                reg_session = request.session.setdefault(REG_VALIDATION_STR, {})
                reg_session.setdefault('cart', {})['discount_code'] = voucher_id
                request.session.modified = True
            else:
                errors = result.get('errors', [])
                error_detail = errors[0].get('message', '') if errors else ''
                messages.warning(
                    request,
                    _(
                        'The voucher code "%(code)s" is not valid.%(detail)s'
                    ) % {
                        'code': voucher_id,
                        'detail': ' ' + str(error_detail) if error_detail else '',
                    }
                )

        return super().get(request, *args, **kwargs)

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
