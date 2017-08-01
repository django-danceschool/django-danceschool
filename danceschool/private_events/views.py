from django.shortcuts import render
from django.http import HttpResponseRedirect, Http404
from django.core.urlresolvers import reverse
from django.views.generic import DetailView
from django.utils.translation import ugettext_lazy as _

from datetime import datetime
import six

from .forms import AddPrivateEventForm, EventOccurrenceFormSet, OccurrenceFormSetHelper
from danceschool.core.utils.timezone import ensure_timezone

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


class PrivateCalendarView(DetailView):
    '''
    This view is used to access the private calendar of a staff member, including any public or private events
    associated with the specified person.
    '''
    template_name = 'private_events/private_fullcalendar.html'

    def get_object(self,queryset=None):
        if hasattr(self.request.user,'staffmember') and self.request.user.staffmember.feedKey:
            return self.request.user.staffmember
        raise Http404(_('Not a valid staff member.'))

    def get_context_data(self,**kwargs):
        ''' Specify the list of feeds in the view so that the template can be agnostic about this '''
        context = super(PrivateCalendarView,self).get_context_data(**kwargs)
        feedKey = self.object.feedKey

        context.update({
            'staffMember': self.object,
            'feedKey': feedKey,
            'publicFeed': reverse('calendarFeed'),
            'privateFeeds': {
                'publicEvents': reverse('calendarFeed', args=(feedKey,)),
                'privateEvents': reverse('privateCalendarFeed', args=(feedKey,)),
            },
            'jsonPublicFeed': reverse('jsonCalendarFeed'),
            'jsonPrivateFeeds': {
                'publicEvents': reverse('jsonCalendarFeed', args=(feedKey,)),
                'privateEvents': reverse('jsonPrivateCalendarFeed', args=(feedKey,)),
            },
        })

        return context


def addPrivateEvent(request):

    if request.POST:
        form = AddPrivateEventForm(request.POST, user=request.user)
        formset = EventOccurrenceFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            obj = form.save()
            formset.instance = obj
            formset.save()
            return HttpResponseRedirect('/admin')

    # Otherwise, return the initial form for this instructor
    # GET parameters can be passed to the form, but the form will not be validated with them.
    else:
        form = AddPrivateEventForm(user=request.user)
        formset = EventOccurrenceFormSet()

        for key in request.GET:
            try:
                form.fields[key].initial = request.GET.get(key)
            except KeyError:
                pass
            try:
                # Only the startTime should be passable to the formset
                if key == 'startTime':
                    formset[0].fields['startTime'].initial = ensure_timezone(datetime.strptime(request.GET.get(key) or '','%Y-%m-%d'))
                    formset[0].fields['endTime'].initial = ensure_timezone(datetime.strptime(request.GET.get(key) or '','%Y-%m-%d'))
                    formset[0].fields['allDay'].initial = True
            except ValueError:
                pass

    return render(request,'private_events/add_private_event_form.html',{
        'form': form,
        'formset': formset,
        'formset_helper': OccurrenceFormSetHelper()},)
