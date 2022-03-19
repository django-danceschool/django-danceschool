from django.db.models import Q, F, Value, CharField, IntegerField
from django.utils.translation import gettext
from django.utils.html import format_html
from django.apps import apps
from django.core.cache import cache

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

        # These filters are applied after the query is complete or the cache is
        # referenced.
        def filter_names(q=''):
            words = q.split(' ')
            lastName = words.pop()
            firstName = words.pop() if words else lastName
            return lambda x: (
                firstName.lower() in x.get('first', '').lower() or
                lastName.lower() in x.get('last', '').lower()
            )

        cache_key = 'RegisterAutoComplete_{}'.format(
            date.strftime("%Y%m%d") if hasattr(date, "strftime") else None
        )

        # Use the cached value as long as it exists (5 minutes) and as long as
        # it actually returns one or more results.
        cached_queryset = cache.get(cache_key)
        if cached_queryset:
            filtered_cache = list(filter(filter_names(self.q), cached_queryset))
            if filtered_cache:
                return filtered_cache

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
        ).filter(customer_filters).values(
            'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
            'guestType'
        ).order_by()

        if date and apps.is_installed('danceschool.guestlist'):

            helpers = importlib.import_module('danceschool.guestlist.helpers')

            guests = helpers.getList(
                events=today_events, includeRegistrants=False
            ).values(
                'id', 'first', 'last', 'contact', 'modelType', 'guestListId',
                'guestType'
            ).order_by()
            if queryset:
                queryset = queryset.union(guests)
            else:
                queryset = guests

        # Cache this query for 5 minutes to speed up the check-in process.
        queryset_list = list(queryset)
        cache.set(cache_key, queryset_list, 300)
        return list(filter(filter_names(self.q), queryset_list))
