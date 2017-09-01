from django.utils.translation import ugettext_lazy as _

from dal import autocomplete

from .models import ExpenseItem, RevenueItem


def get_method_list():
    '''
    Include manual methods by default
    '''
    methods = [str(_('Cash')),str(_('Check')),str(_('Bank/Debit Card')),str(_('Other'))]
    methods += ExpenseItem.objects.order_by().values_list('paymentMethod',flat=True).distinct()
    methods += RevenueItem.objects.order_by().values_list('paymentMethod',flat=True).distinct()
    methods_list = list(set(methods))

    if None in methods_list:
        methods_list.remove(None)

    return methods_list


class PaymentMethodAutoComplete(autocomplete.Select2ListView):
    '''
    This is the autocomplete view used to indicate payment methods in the
    Revenue Reporting view.
    '''

    def get_list(self):
        return get_method_list()

    def create(self,text):
        '''
        Since this autocomplete is used to create new RevenueItems, and the set of
        RevenueItem paymentMethods is automatically updated in get_method_list(),
        this function does not need to do anything
        '''
        return text
