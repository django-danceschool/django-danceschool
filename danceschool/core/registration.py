import re

from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import TemplateView

from .constants import getConstant, REG_VALIDATION_STR
from .models import Event, Series, PublicEvent
from .mixins import FinancialContextMixin, EventOrderMixin, SiteHistoryMixin
from .signals import check_voucher


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
    the registration/referral/<voucher_id>/ URL pattern.  Valid codes are stored
    directly in the cart session data as discount_code; invalid codes produce a
    warning message.  Marketing IDs (?id= or registration/id/<marketing_id>/) are
    stored in session data for later use.
    '''
    template_name = 'core/public_register.html'

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
