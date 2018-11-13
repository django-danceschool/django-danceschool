from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView
from django.shortcuts import get_object_or_404
from django.http import Http404, JsonResponse

from braces.views import PermissionRequiredMixin

from .models import GuestList, Event


class GuestListView(PermissionRequiredMixin,DetailView):
    '''
    This view is used to access the guest list for a given series or event
    '''
    template_name = 'guestlist/guestlist.html'
    permission_required = 'guestlist.view_guestlist'

    def get_object(self, queryset=None):
        ''' Get the guest list from the URL '''
        return get_object_or_404(
            GuestList.objects.filter(id=self.kwargs.get('guestlist_id')))

    def get_context_data(self,**kwargs):
        ''' Add the list of names for the given guest list '''
        event = Event.objects.filter(id=self.kwargs.get('event_id')).first()
        if self.kwargs.get('event_id') and not self.object.appliesToEvent(event):
            raise Http404(_('Invalid event.'))

        # Use the most current event if nothing has been specified.
        if not event:
            event = self.object.currentEvent

        context = {
            'guestList': self.object,
            'event': event,
            'names': self.object.getListForEvent(event),
        }
        context.update(kwargs)
        return super(GuestListView,self).get_context_data(**context)


class GuestListJsonView(GuestListView):
    '''
    This view provides the guest list in JSON format.
    '''
    template_name = None

    def render_to_response(self, context, **response_kwargs):
        json_context = {
            'names': context.get('names'),
            'guestlist_id': getattr(context.get('guestList'),'id'),
            'event_id': getattr(context.get('event'),'id'),            
        }

        return JsonResponse(json_context)
