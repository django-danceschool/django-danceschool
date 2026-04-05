from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.generic import DetailView, View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.models import User
from braces.views import PermissionRequiredMixin, LoginRequiredMixin

from ..models import Event, EventRegistration
from ..signals import get_person_data

import logging

logger = logging.getLogger(__name__)


############################################
# Customer and Instructor Stats Views


class AccountProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'core/account_profile.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = {}
        user = self.get_object()

        context.update({
            'primary_email': user.emailaddress_set.filter(primary=True).first(),
            'verified_emails': user.emailaddress_set.filter(verified=True),
            'unverified_emails': user.emailaddress_set.filter(verified=False),
        })

        if hasattr(user, 'customer'):
            context.update({
                'customer': user.customer,
                'customer_verified': user.emailaddress_set.filter(email=user.customer.email, verified=True).exists(),
            })
            context['customer_eventregs'] = EventRegistration.objects.filter(customer=user.customer)

        context['verified_eventregs'] = EventRegistration.objects.filter(
            customer__email__in=[x.email for x in context['verified_emails']]
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs', [])]
        )
        context['submitted_eventregs'] = EventRegistration.objects.filter(
            registration__invoice__submissionUser=self.request.user, registration__payAtDoor=False
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs', [])]
        ).exclude(
            id__in=[x.id for x in context.get('verified_eventregs', [])]
        )

        if hasattr(user, 'staffmember'):
            upcoming_events = Event.objects.filter(
                endTime__gt=timezone.now(),
                eventstaffmember__staffMember=user.staffmember).distinct().order_by('-startTime')
            context.update({
                'staffmember': user.staffmember,
                'upcoming_events': upcoming_events,
            })

        # Get any extra context data passed by other apps.  These data require unique keys, so when writing
        # a handler for this signal, be sure to provide unique context keys.
        if hasattr(user, 'customer'):
            extra_customer_data = get_person_data.send(
                sender=AccountProfileView,
                customer=user.customer,
            )
            for item in extra_customer_data:
                if len(item) > 1 and isinstance(item[1], dict):
                    # Ensure that 'customer' is not overwritten and add everything else
                    item[1].pop('customer', None)
                    context.update(item[1])

        return super().get_context_data(**context)


class OtherAccountProfileView(PermissionRequiredMixin, AccountProfileView):
    permission_required = 'core.view_other_user_profiles'

    def get_object(self, queryset=None):
        if 'user_id' in self.kwargs:
            return get_object_or_404(User.objects.filter(id=self.kwargs.get('user_id')))
        else:
            return self.request.user


class UserAccountInfo(View):
    ''' This view just returns the name and email address information for the currently logged in user '''

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        context = {}

        if not request.user.is_authenticated:
            return JsonResponse(context)

        customer = getattr(request.user, 'customer', None)

        if customer:
            context.update({
                'customer': True,
                'first_name': customer.first_name or request.user.first_name,
                'last_name': customer.last_name or request.user.last_name,
                'email': customer.email or request.user.email,
                'phone': customer.phone,
            })
        else:
            context.update({
                'customer': False,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            })

        # Also add any outstanding messages (e.g. login successful message) to be
        # relayed to the user when this information is used.
        context['messages'] = []

        for message in messages.get_messages(request):
            context['messages'].append({
                "level": message.level,
                "message": message.message,
                "extra_tags": message.tags,
            })

        return JsonResponse(context)
