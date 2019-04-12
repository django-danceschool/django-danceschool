from django.utils.translation import ugettext_lazy as _
from django.http import HttpResponseRedirect, Http404
from django.urls import reverse
from django.db.models import Q

from braces.views import PermissionRequiredMixin
from datetime import datetime, timedelta

from danceschool.core.constants import getConstant
from danceschool.core.utils.timezone import ensure_localtime
from danceschool.core.models import Event, Series, PublicEvent
from danceschool.core.classreg import ClassRegistrationView
from danceschool.core.signals import post_student_info


class NightlyRegisterView(PermissionRequiredMixin, ClassRegistrationView):
    permission_required = 'core.accept_door_payments'
    template_name = 'nightlydoor/register.html'

    def get_allEvents(self):
        '''
        This method is overridden from base ClassRegistrationView to include
        only events that occur on the day in question.
        '''

        # These are passed via the URL and should all be numbers.
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        try:
            intervalStart = ensure_localtime(datetime(int(year),int(month),int(day)))
            self.interval = (intervalStart,intervalStart + timedelta(days=1))
        except ValueError:
            raise Http404(_('Invalid date passed'))

        if not hasattr(self,'allEvents'):
            self.allEvents = Event.objects.filter(
                eventoccurrence__startTime__lt=self.interval[1],
                eventoccurrence__endTime__gt=self.interval[0]
            ).filter(
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

    def get_form_kwargs(self, **kwargs):
        '''
        Tell the form not to include counts in field labels.  Also, if the apppropriate
        preference is set, then tell the form to include the voucher field.        
        '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs.update({
            'includeCounts': False,
            'pluralName': False,
            'interval': self.interval,
            'voucherField': getConstant('nightlydoor__enableVoucherEntry'),
        })
        return kwargs

    def get_context_data(self,**kwargs):
        ''' Add the event and series listing data '''
        year = int(self.kwargs.get('year'))
        month = int(self.kwargs.get('month'))
        day = int(self.kwargs.get('day'))

        context = self.get_listing()
        context.update({
            'voucherField': getConstant('nightlydoor__enableVoucherEntry'),
            'showDescriptionRule': getConstant('registration__showDescriptionRule') or 'all',
            'year': year,
            'month': month,
            'day': day,
            'today': datetime(year, month, day)
        })
        context.update(kwargs)

        # Update the site session data so that registration processes know to send return links to
        # the registration page.  set_return_page() is in SiteHistoryMixin.
        self.set_return_page('nightlyRegister',_('Registration'))

        return super().get_context_data(**context)

    def get_success_url(self):
        '''
        Determine whether to proceed to get name and email or proceed to the
        summary page based on the contents of the registration.
        '''

        requireFullRule = getConstant('nightlydoor__requireFullRegistration')

        events = Event.objects.filter(temporaryeventregistration__in=self.event_registrations).distinct()

        if requireFullRule == 'Never' or (
                (
                    requireFullRule == 'SeriesOnly' and not events.filter(
                        series__isnull=False
                    ).exists()
                ) or (
                    requireFullRule == 'EventsOnly' and not events.filter(
                        publicevent__isnull=False
                    ).exists()
                )
        ):
            # This signal (formerly the post_temporary_registration signal) allows
            # vouchers to be applied temporarily, and it can be used for other tasks
            post_student_info.send(
                sender=NightlyRegisterView, 
                registration=self.temporaryRegistration,
            )
            return reverse('showRegSummary')
        return reverse('getStudentInfo')
