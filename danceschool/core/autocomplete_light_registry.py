from django.contrib.auth.models import User
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.db.models import Q

from dal import autocomplete
from calendar import month_name

from .models import Customer, StaffMember, Series, PublicEvent, Event


class UserAutoComplete(autocomplete.Select2QuerySetView):

    def get_queryset(self):
        # Filter out results for unauthenticated users.
        if not self.request.user.has_perm('core.can_autocomplete_users'):
            return User.objects.none()

        qs = User.objects.all()

        if self.q:
            words = self.q.split(' ')
            lastName = words.pop()
            firstName = words.pop() if words else lastName

            qs = qs.filter(
                Q(first_name__istartswith=firstName) | Q(last_name__istartswith=lastName) |
                Q(email__istartswith=self.q)
            )

        return qs

    def get_result_label(self, result):
        return force_text(result.get_full_name() + ': ' + result.email)


class CustomerAutoComplete(autocomplete.Select2QuerySetView):

    def get_queryset(self):
        # Filter out results for unauthenticated users.
        if not self.request.user.has_perm('core.can_autocomplete_users'):
            return Customer.objects.none()

        qs = Customer.objects.all()

        if self.q:
            words = self.q.split(' ')
            lastName = words.pop()
            firstName = words.pop() if words else lastName

            qs = qs.filter(
                Q(first_name__istartswith=firstName) | Q(last_name__istartswith=lastName) |
                Q(email__istartswith=self.q)
            )

        return qs


class EventAutoComplete(autocomplete.Select2QuerySetView):
    '''
    Allow the user to filter autocomplates on the name of the series/event and
    on the year or month name.
    '''

    def get_queryset(self):

        qs = Event.objects.filter(
            Q(instance_of=PublicEvent) | Q(instance_of=Series)
        )

        if not self.request.user.is_staff:
            qs = qs.exclude(status=Event.RegStatus.hidden)

        if self.q:
            try:
                month_dict = {v: k for k,v in enumerate(month_name)}
                month_value = next(value for key, value in month_dict.items() if key.startswith(self.q.title()))
            except StopIteration:
                month_value = ''

            qs = qs.filter(
                Q(series__classDescription__title__icontains=self.q) | 
                Q(publicevent__title__icontains=self.q) |
                Q(year__icontains=self.q) |
                Q(month__icontains=month_value)
            )

        return qs

    def get_result_label(self, result):
        return format_html(
            '{}: {} {} <br /><small>{}</small>',
            result.name, result.getMonthName, result.year,
            ', '.join([x.startTime.strftime('%b. %d') for x in result.eventoccurrence_set.all()])
        )

    def get_selected_result_label(self, result):
        return format_html(
            '{}: {} {}',
            result.name, result.getMonthName, result.year,
        )


class StaffMemberAutoComplete(autocomplete.Select2QuerySetView):

    def get_queryset(self):
        # Filter out results for unauthenticated users.
        if not self.request.user.has_perm('core.can_autocomplete_staffmembers'):
            return StaffMember.objects.none()

        qs = StaffMember.objects.all()

        if self.q:
            words = self.q.split(' ')
            lastName = words.pop()
            firstName = words.pop() if words else lastName

            qs = qs.filter(
                Q(firstName__istartswith=firstName) | Q(lastName__istartswith=lastName) |
                Q(publicEmail__istartswith=self.q)
            )

        return qs

    def create_object(self, text):
        ''' Allow creation of staff members using a full name string. '''
        if self.create_field == 'fullName':
            firstName = text.split(' ')[0]
            lastName = ' '.join(text.split(' ')[1:])
            return self.get_queryset().create(**{'firstName': firstName, 'lastName': lastName})
        else:
            return super(StaffMemberAutoComplete,self).create_object(text)
