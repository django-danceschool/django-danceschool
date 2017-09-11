from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.views.generic import TemplateView
from django.apps import apps

from datetime import datetime

from danceschool.core.utils.timezone import ensure_timezone
from danceschool.core.models import Location, Room

from .forms import AddPrivateEventForm, EventOccurrenceFormSet, OccurrenceFormSetHelper


class PrivateCalendarView(TemplateView):
    '''
    This view is used to access the full listing of events at a selectable location.
    The user only sees private lessons is they have permissions to see other instructors'
    lesson schedules, and they only see private events that are visible to them.
    '''
    template_name = 'private_events/private_fullcalendar.html'

    def get_context_data(self, **kwargs):
        context = super(PrivateCalendarView,self).get_context_data(**kwargs)

        context.update({
            'locations': Location.objects.all().order_by('status','name'),
            'rooms': Room.objects.all().order_by('location__status','location__name', 'name'),
            'publicFeed': reverse('calendarFeed'),
            'jsonPublicFeed': reverse('jsonCalendarFeed'),
            'jsonPrivateFeeds': {
                'privateEvents': reverse('jsonPrivateCalendarFeed'),
            }
        })

        feedKey = getattr(getattr(self.request.user,'staffmember',None),'feedKey',None)
        if feedKey:
            context.update({
                'privateFeeds': {
                    'ownPublicEvents': reverse('calendarFeed', args=(feedKey,)),
                    'privateEvents': reverse('privateCalendarFeed', args=(feedKey,)),
                },
            })
            context['jsonPrivateFeeds']['ownPublicEvents'] = reverse('jsonCalendarFeed', args=(feedKey,))

        if apps.is_installed('danceschool.private_lessons'):
            context['privateLessonAdminUrl'] = reverse('admin:private_lessons_privatelessonevent_changelist')
            context['jsonPrivateFeeds'].update({
                'privateLessons': reverse('jsonPrivateLessonFeed'),
                'ownPrivateLessons': reverse('jsonOwnPrivateLessonFeed'),
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
            return HttpResponseRedirect(reverse('privateCalendar'))

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
