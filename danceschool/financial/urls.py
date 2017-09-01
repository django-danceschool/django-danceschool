from django.conf.urls import url

from .views import InstructorPaymentsView, OtherInstructorPaymentsView, FinancesByMonthView, FinancesByEventView, AllExpensesViewCSV, AllRevenuesViewCSV, FinancialDetailView, ExpenseReportingView, RevenueReportingView, CompensationRuleUpdateView
from .ajax import updateEventRegistrations
from .autocomplete_light_registry import PaymentMethodAutoComplete

urlpatterns = [
    url(r'^instructor-payments/$', InstructorPaymentsView.as_view(), name='instructorPayments'),
    url(r'^instructor-payments/(?P<year>[\w\+]+)/$', InstructorPaymentsView.as_view(), name='instructorPayments'),
    url(r'^instructor-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/$', OtherInstructorPaymentsView.as_view(), name='instructorPayments'),
    url(r'^instructor-payments/csv/$', InstructorPaymentsView.as_view(as_csv=True), name='instructorPaymentsCSV'),
    url(r'^instructor-payments/(?P<year>[\w\+]+)/csv/$', InstructorPaymentsView.as_view(as_csv=True), name='instructorPaymentsCSV'),
    url(r'^instructor-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/csv/$', OtherInstructorPaymentsView.as_view(as_csv=True), name='instructorPaymentsCSV'),

    url(r'^submit-expenses/$', ExpenseReportingView.as_view(), name='submitExpenses'),
    url(r'^submit-revenues/$', RevenueReportingView.as_view(), name='submitRevenues'),

    # These URLs are for Ajax/autocomplete functionality
    url(r'^submit-revenues/eventfilter/$', updateEventRegistrations, name='ajaxhandler_updateEventRegistrations'),
    url(r'^autocomplete/paymentmethod/$', PaymentMethodAutoComplete.as_view(), name='paymentMethod-list-autocomplete'),

    # These URLs are for the financial views
    url(r'^finances/detail/(?P<year>[\w\+]+)/(?P<month>[\w\+]+)/$', FinancialDetailView.as_view(), name='financialDetailView'),
    url(r'^finances/detail/(?P<year>[\w\+]+)/$', FinancialDetailView.as_view(), name='financialDetailView'),
    url(r'^finances/detail/$', FinancialDetailView.as_view(), name='financialDetailView'),

    url(r'^finances/csv/$', FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'),
    url(r'^finances/(?P<year>[\w\+]+)/$', FinancesByMonthView.as_view(), name='financesByMonth'),
    url(r'^finances/(?P<year>[\w\+]+)/csv/$', FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'),
    url(r'^finances/$', FinancesByMonthView.as_view(), name='financesByMonth'),

    url(r'^finances-byevent/csv/$', FinancesByEventView.as_view(as_csv=True), name='financesByEventCSV'),
    url(r'^finances-byevent/(?P<year>[\w\+]+)/csv/$', FinancesByEventView.as_view(as_csv=True), name='financesByEventCSV'),
    url(r'^finances-byevent/$', FinancesByEventView.as_view(), name='financesByEvent'),

    url(r'^finances/expenses/(?P<year>[\w\+]+)/csv/$', AllExpensesViewCSV.as_view(), name='allexpensesCSV'),
    url(r'^finances/revenues/(?P<year>[\w\+]+)/csv/$', AllRevenuesViewCSV.as_view(), name='allrevenuesCSV'),

    url(r'^compensation/update/$', CompensationRuleUpdateView.as_view(), name='updateCompensationRules'),
]
