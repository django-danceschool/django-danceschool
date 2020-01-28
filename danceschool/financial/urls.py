from django.conf.urls import url

from .views import (
    StaffMemberPaymentsView, OtherStaffMemberPaymentsView, FinancesByMonthView,
    FinancesByDateView, FinancesByEventView, AllExpensesViewCSV, AllRevenuesViewCSV,
    FinancialDetailView, ExpenseReportingView, RevenueReportingView,
    CompensationRuleUpdateView, CompensationRuleResetView, ExpenseRuleGenerationView
)
from .ajax import updateEventRegistrations
from .autocomplete_light_registry import (
    PaymentMethodAutoComplete, TransactionPartyAutoComplete,
    ApprovalStatusAutoComplete
)


urlpatterns = [
    url(r'^staff-payments/$', StaffMemberPaymentsView.as_view(), name='staffMemberPayments'),
    url(
        r'^staff-payments/(?P<year>[\w\+]+)/$',
        StaffMemberPaymentsView.as_view(), name='staffMemberPayments'
    ),
    url(
        r'^staff-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/$',
        OtherStaffMemberPaymentsView.as_view(), name='staffMemberPayments'
    ),
    url(
        r'^staff-payments/csv/$',
        StaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),
    url(
        r'^staff-payments/(?P<year>[\w\+]+)/csv/$',
        StaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),
    url(
        r'^staff-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/csv/$',
        OtherStaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),

    url(r'^submit-expenses/$', ExpenseReportingView.as_view(), name='submitExpenses'),
    url(r'^submit-revenues/$', RevenueReportingView.as_view(), name='submitRevenues'),
    url(r'^finances/generate-items/$', ExpenseRuleGenerationView.as_view(), name='generateFinancialItems'),

    # These URLs are for Ajax/autocomplete functionality
    url(
        r'^submit-revenues/eventfilter/$', updateEventRegistrations,
        name='ajaxhandler_updateEventRegistrations'
    ),
    url(
        r'^autocomplete/paymentmethod/$', PaymentMethodAutoComplete.as_view(),
        name='paymentMethod-list-autocomplete'
    ),
    url(
        r'^autocomplete/approved/$', ApprovalStatusAutoComplete.as_view(),
        name='approved-list-autocomplete'
    ),
    url(
        r'^autocomplete/transactionparty/$',
        TransactionPartyAutoComplete.as_view(create_field='name'),
        name='transactionParty-list-autocomplete'
    ),

    # These URLs are for the financial views
    url(
        r'^finances/detail/(?P<year>[\w\+]+)/(?P<month>[\w\+]+)/(?P<day>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialDateDetailView'
    ),
    url(
        r'^finances/detail/(?P<year>[\w\+]+)/(?P<month>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialMonthDetailView'
    ),
    url(
        r'^finances/detail/(?P<year>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialYearDetailView'
    ),
    url(r'^finances/detail/$', FinancialDetailView.as_view(), name='financialDetailView'),
    url(
        r'^finances/event/(?P<event>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialEventDetailView'
    ),

    url(
        r'^finances/daily/csv/$', FinancesByDateView.as_view(as_csv=True),
        name='financesByDateCSV'
    ),
    url(
        r'^finances/daily/(?P<year>[\w\+]+)/$', FinancesByDateView.as_view(),
        name='financesByDate'
    ),
    url(
        r'^finances/daily/(?P<year>[\w\+]+)/csv/$',
        FinancesByDateView.as_view(as_csv=True), name='financesByDateCSV'
    ),
    url(r'^finances/daily/$', FinancesByDateView.as_view(), name='financesByDate'),

    url(r'^finances/csv/$', FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'),
    url(r'^finances/(?P<year>[\w\+]+)/$', FinancesByMonthView.as_view(), name='financesByMonth'),
    url(
        r'^finances/(?P<year>[\w\+]+)/csv/$',
        FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'
    ),
    url(r'^finances/$', FinancesByMonthView.as_view(), name='financesByMonth'),

    url(
        r'^finances-byevent/csv/$', FinancesByEventView.as_view(as_csv=True),
        name='financesByEventCSV'
    ),
    url(
        r'^finances-byevent/(?P<year>[\w\+]+)/csv/$',
        FinancesByEventView.as_view(as_csv=True), name='financesByEventCSV'
    ),
    url(r'^finances-byevent/$', FinancesByEventView.as_view(), name='financesByEvent'),

    url(r'^finances/expenses/(?P<year>[\w\+]+)/csv/$', AllExpensesViewCSV.as_view(), name='allexpensesCSV'),
    url(r'^finances/revenues/(?P<year>[\w\+]+)/csv/$', AllRevenuesViewCSV.as_view(), name='allrevenuesCSV'),

    url(r'^compensation/update/$', CompensationRuleUpdateView.as_view(), name='updateCompensationRules'),
    url(r'^compensation/reset/$', CompensationRuleResetView.as_view(), name='resetCompensationRules'),
]
