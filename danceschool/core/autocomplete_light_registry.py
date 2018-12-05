from django.contrib.auth.models import User
from django.utils.encoding import force_text
from django.db.models import Q

from dal import autocomplete

from .models import Customer, StaffMember


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

    def get_result_label(self,item):
        return force_text(item.get_full_name() + ': ' + item.email)


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
