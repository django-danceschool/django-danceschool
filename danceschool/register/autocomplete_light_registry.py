from django.db.models import Q, F, Value, CharField, IntegerField
from django.utils.translation import gettext
from django.utils.html import format_html
from django.apps import apps

from dal import autocomplete
from datetime import timedelta
from dateutil.parser import parse
import importlib

from danceschool.core.models import Customer, Event, EventOccurrence
from danceschool.core.utils.timezone import ensure_localtime


class RegisterAutoComplete(autocomplete.Select2QuerySetView):

    def get_result_value(self, result):
        """Return the value of a result."""
        return '{first} {last} ({guestType})'.format(**result)

    def get_result_label(self, result):
        """Return the label of a result."""
        if result.get('guestType') != 'Customer':
            return format_html(
                '<span data-id="{id}" data-type="{guestType}" data-model-type="{modelType}"' +
                'data-guest-list-id="{guestListId}">{first} {last} ({guestType})</span>',
                **result
            )
        return format_html(
            '<span data-id="{id}" data-type="{guestType}" data-model-type="{modelType}"' +
            'data-guest-list-id="{guestListId}">{first} {last}</span>',
                **result
        )

    def get_queryset(self):
        # Filter out results for unauthenticated users.
        if not self.request.user.has_perm('core.can_autocomplete_users'):
            return Customer.objects.none()

        try:
            date = parse(self.forwarded.get('date', ''))
        except ValueError:
            date = None

        name_filters = Q()
        if self.q:
            words = self.q.split(' ')
            lastName = words.pop()
            firstName = words.pop() if words else lastName
            name_filters = Q(first__icontains=firstName) | Q(last__icontains=lastName)

        customer_filters = Q()
        if date:
            start = ensure_localtime(date)
            end = ensure_localtime(date) + timedelta(days=1)

            today_occs = EventOccurrence.objects.filter(
                endTime__gte=start, startTime__lte=end
            )
            today_events = Event.objects.filter(eventoccurrence__in=today_occs).distinct()

            customer_filters = (
                Q(eventregistration__event__in=today_events) &
                Q(eventregistration__registration__final=True) & (
                    Q(eventregistration__dropIn=False) | (
                        Q(eventregistration__dropIn=True) &
                        Q(eventregistration__occurrences__in=today_occs)
                    )
                )
            )

        queryset = Customer.objects.annotate(
            first=F('first_name'), last=F('last_name'), contact=F('email'),
            modelType=Value('Customer', output_field=CharField()),
            guestListId=Value(None, output_field=IntegerField()),
            guestType=Value(gettext('Customer'), output_field=CharField()),
        ).filter(name_filters).filter(customer_filters).values(
            'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
            'guestType'
        ).order_by()

        if date and apps.is_installed('danceschool.guestlist'):

            helpers = importlib.import_module('danceschool.guestlist.helpers')

            guests = helpers.getList(
                events=today_events, filters=name_filters, includeRegistrants=False
            ).values(
                'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
                'guestType'
            ).order_by()
            if queryset:
                queryset = queryset.union(guests)
            else:
                queryset = guests

        return queryset