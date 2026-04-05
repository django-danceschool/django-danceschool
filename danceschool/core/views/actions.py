from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.views.generic import FormView, TemplateView
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.views import SuccessMessageMixin
from urllib.parse import unquote
from braces.views import PermissionRequiredMixin
from dateutil.relativedelta import relativedelta
from datetime import datetime
from cms.models import Page

from ..forms import RepeatEventForm
from ..constants import getConstant
from ..mixins import AdminSuccessURLMixin, SiteHistoryMixin
from ..models import Event, EventOccurrence, EventRole
from ..utils.requests import getIntFromGet
from ..utils.timezone import ensure_timezone

import logging

logger = logging.getLogger(__name__)


#################################
# Used for various form submission redirects (called by the AdminSuccessURLMixin)


class SubmissionRedirectView(SiteHistoryMixin, TemplateView):
    template_name = 'cms/forms/submission_redirect.html'

    def get_context_data(self, **kwargs):
        '''
        The URL to redirect to can be explicitly specified, or it can come
        from the site session history, or it can be the default admin success page
        as specified in the site settings.
        '''

        context = super().get_context_data(**kwargs)

        redirect_url = unquote(self.request.GET.get('redirect_url', ''))
        if not redirect_url:
            redirect_url = self.get_return_page().get('url', '')
        if not redirect_url:
            try:
                redirect_url = Page.objects.get(
                    pk=getConstant('general__defaultAdminSuccessPage')
                ).get_absolute_url(settings.LANGUAGE_CODE)
            except ObjectDoesNotExist:
                redirect_url = '/'

        context.update({
            'redirect_url': redirect_url,
            'seconds': self.request.GET.get('seconds', 5),
        })

        return context


#####################################
# View for Repeating Events from admin
class RepeatEventsView(SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin, FormView):
    '''
    This view is for an admin action to repeat events.
    '''
    template_name = 'core/repeat_events.html'
    form_class = RepeatEventForm
    permission_required = 'core.add_event'
    success_message = _('Repeated events created successfully.')

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')
        ct = getIntFromGet(request, 'ct')

        try:
            contentType = ContentType.objects.get(id=ct)
            self.objectClass = contentType.model_class()
        except (ValueError, ObjectDoesNotExist):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        # This view only deals with subclasses of Events (Public Events, Series, etc.)
        if not isinstance(self.objectClass(), Event):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(', ')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'events': self.queryset,
        })

        return context

    def form_valid(self, form):
        ''' For each object in the queryset, create the duplicated objects '''

        startDate = form.cleaned_data.get('startDate')
        repeatEvery = form.cleaned_data.get('repeatEvery')
        periodicity = form.cleaned_data.get('periodicity')
        quantity = form.cleaned_data.get('quantity')
        endDate = form.cleaned_data.get('endDate')

        # Create a list of start dates, based on the passed  values of repeatEvery,
        # periodicity, quantity and endDate.  This list will be iterated through to
        # create the new instances for each event.
        if periodicity == 'D':
            delta = {'days': repeatEvery}
        elif periodicity == 'W':
            delta = {'weeks': repeatEvery}
        elif periodicity == 'M':
            delta = {'months': repeatEvery}

        repeat_list = []
        this_date = startDate

        if quantity:
            for k in range(0, quantity):
                repeat_list.append(this_date)
                this_date = this_date + relativedelta(**delta)
        elif endDate:
            while (this_date <= endDate):
                repeat_list.append(this_date)
                this_date = this_date + relativedelta(**delta)

        # Now, loop through the events in the queryset to create duplicates of them
        for event in self.queryset:

            # For each new occurrence, we determine the new startime by the distance from
            # midnight of the first occurrence date, where the first occurrence date is
            # replaced by the date given in repeat list
            old_min_time = event.localStartTime.replace(hour=0, minute=0, second=0, microsecond=0)

            old_occurrence_data = [
                (x.startTime - old_min_time, x.endTime - old_min_time, x.cancelled)
                for x in event.eventoccurrence_set.all()
            ]

            old_role_data = [(x.role, x.capacity) for x in event.eventrole_set.all()]

            for instance_date in repeat_list:

                # Ensure that time zones are treated properly
                combined_datetime = datetime.combine(instance_date, datetime.min.time())
                new_datetime = ensure_timezone(combined_datetime, old_min_time.tzinfo)

                # Removing the pk and ID allow new instances of the event to
                # be created upon saving with automatically generated ids.
                event.id = None
                event.pk = None
                event.save()

                # Create new occurrences
                for occurrence in old_occurrence_data:
                    EventOccurrence.objects.create(
                        event=event,
                        startTime=new_datetime + occurrence[0],
                        endTime=new_datetime + occurrence[1],
                        cancelled=occurrence[2],
                    )

                # Create new event-specific role data
                for role in old_role_data:
                    EventRole.objects.create(
                        event=event,
                        role=role[0],
                        capacity=role[1],
                    )

                # Need to save twice to ensure that startTime etc. get
                # updated properly.
                event.save()

            return super().form_valid(form)
