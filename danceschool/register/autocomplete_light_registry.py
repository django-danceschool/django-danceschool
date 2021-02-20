from django.db.models import Q, F, Value, CharField, IntegerField
from django.utils.translation import gettext
from django.utils.html import format_html
from django.apps import apps

from dal import autocomplete
from datetime import timedelta
from dateutil.parser import parse

from danceschool.core.models import Customer, Event, EventOccurrence
from danceschool.core.utils.timezone import ensure_localtime


class RegisterAutoComplete(autocomplete.Select2QuerySetView):

    def get_result_value(self, result):
        """Return the value of a result."""
        return '{} {} ({})'.format(
            result.get('firstName'), result.get('lastName'), result.get('guestType')
        )

    def get_result_label(self, result):
        """Return the label of a result."""
        if result.get('guestType') != 'Customer':
            return format_html(
                '<span data-id="{id}" data-type="{guestType}" data-model-type="{modelType}"' +
                'data-guest-list-id="{guestListId}">{firstName} {lastName} ({guestType})</span>',
                **result
            )
        return format_html(
            '<span data-id="{id}" data-type="{guestType}" data-model-type="{modelType}"' +
            'data-guest-list-id="{guestListId}">{firstName} {lastName}</span>',
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
            name_filters = Q(firstName__icontains=firstName) | Q(lastName__icontains=lastName)

        customer_filters = Q()
        if date:
            start = ensure_localtime(date)
            end = ensure_localtime(date) + timedelta(days=1)

            today_occs = EventOccurrence.objects.filter(
                endTime__gte=start, startTime__lte=end
            )
            today_events = Event.objects.filter(eventoccurrence__in=today_occs).distinct()

            customer_filters = (
                Q(registration__eventregistration__event__in=today_events) &
                Q(registration__final=True) & (
                    Q(registration__eventregistration__dropIn=False) | (
                        Q(registration__eventregistration__dropIn=True) &
                        Q(registration__eventregistration__occurrences__in=today_occs)
                    )
                )
            )

        queryset = Customer.objects.annotate(
            firstName=F('first_name'), lastName=F('last_name'),
            modelType=Value('Customer', output_field=CharField()),
            guestListId=Value(None, output_field=IntegerField()),
            guestType=Value(gettext('Customer'), output_field=CharField()),
        ).filter(name_filters).filter(customer_filters).values(
            'id', 'modelType', 'guestListId', 'firstName', 'lastName',
            'guestType',
        )

        if date and apps.is_installed('danceschool.guestlist'):

            GuestList = apps.get_model('guestlist', 'GuestList')

            # Needed to avoid DatabaseError from ORDER BY in SQL subqueries.
            queryset = queryset.order_by()

            # This is the same logic as the appliesToEvent() method of GuestList
            applicable_lists = GuestList.objects.filter(
                Q(individualEvents__in=today_events) |
                Q(eventSessions__in=today_events.filter(session__isnull=False).values_list(
                    'session', flat=True
                )) |
                Q(seriesCategories__in=today_events.filter(
                    series__category__isnull=False
                ).values_list('series__category', flat=True)) |
                Q(eventCategories__in=today_events.filter(
                    publicevent__category__isnull=False
                ).values_list('publicevent__category', flat=True))
            )

            for this_list in applicable_lists:
                for this_event in today_events:
                    queryset = queryset.union(
                        this_list.getListForEvent(
                            this_event, filters=name_filters, includeRegistrants=False
                        ).order_by()
                    )

            # Now that all the subqueries are together, order by the common
            # lastName and firstName fields.
            queryset = queryset.values(
                'id', 'modelType', 'guestListId', 'firstName', 'lastName',
                'guestType',
            ).distinct().order_by(
                'lastName', 'firstName'
            )

        return queryset
