from django.urls import path, re_path

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
    path('staff-payments/', StaffMemberPaymentsView.as_view(), name='staffMemberPayments'),
    re_path(
        r'^staff-payments/(?P<year>[\w\+]+)/$',
        StaffMemberPaymentsView.as_view(), name='staffMemberPayments'
    ),
    re_path(
        r'^staff-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/$',
        OtherStaffMemberPaymentsView.as_view(), name='staffMemberPayments'
    ),
    path(
        'staff-payments/csv/',
        StaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),
    re_path(
        r'^staff-payments/(?P<year>[\w\+]+)/csv/$',
        StaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),
    re_path(
        r'^staff-payments/(?P<year>[\w\+]+)/(?P<first_name>[\w\+\.]+)-(?P<last_name>[\w\+\.]+)/csv/$',
        OtherStaffMemberPaymentsView.as_view(as_csv=True),
        name='staffMemberPaymentsCSV'
    ),

    path('submit-expenses/', ExpenseReportingView.as_view(), name='submitExpenses'),
    path('submit-revenues/', RevenueReportingView.as_view(), name='submitRevenues'),
    path('finances/generate-items/', ExpenseRuleGenerationView.as_view(), name='generateFinancialItems'),

    # These URLs are for Ajax/autocomplete functionality
    path(
        'submit-revenues/eventfilter/', updateEventRegistrations,
        name='ajaxhandler_updateEventRegistrations'
    ),
    path(
        'autocomplete/paymentmethod/', PaymentMethodAutoComplete.as_view(),
        name='paymentMethod-list-autocomplete'
    ),
    path(
        'autocomplete/approved/', ApprovalStatusAutoComplete.as_view(),
        name='approved-list-autocomplete'
    ),
    path(
        'autocomplete/transactionparty/',
        TransactionPartyAutoComplete.as_view(create_field='name'),
        name='transactionParty-list-autocomplete'
    ),

    # These URLs are for the financial views
    re_path(
        r'^finances/detail/(?P<year>[\w\+]+)/(?P<month>[\w\+]+)/(?P<day>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialDateDetailView'
    ),
    re_path(
        r'^finances/detail/(?P<year>[\w\+]+)/(?P<month>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialMonthDetailView'
    ),
    re_path(
        r'^finances/detail/(?P<year>[\w\+]+)/$',
        FinancialDetailView.as_view(), name='financialYearDetailView'
    ),
    path('finances/detail/', FinancialDetailView.as_view(), name='financialDetailView'),
    path(
        'finances/event/<slug:event>/',
        FinancialDetailView.as_view(), name='financialEventDetailView'
    ),

    path(
        'finances/daily/csv/', FinancesByDateView.as_view(as_csv=True),
        name='financesByDateCSV'
    ),
    path(
        'finances/daily/<slug:year>/', FinancesByDateView.as_view(),
        name='financesByDate'
    ),
    path(
        'finances/daily/<slug:year>/csv/',
        FinancesByDateView.as_view(as_csv=True), name='financesByDateCSV'
    ),
    path('finances/daily/', FinancesByDateView.as_view(), name='financesByDate'),

    path('finances/csv/', FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'),
    path('finances/<slug:year>/', FinancesByMonthView.as_view(), name='financesByMonth'),
    path(
        'finances/<slug:year>/csv/',
        FinancesByMonthView.as_view(as_csv=True), name='financesByMonthCSV'
    ),
    path('finances/', FinancesByMonthView.as_view(), name='financesByMonth'),

    path(
        'finances-byevent/csv/', FinancesByEventView.as_view(as_csv=True),
        name='financesByEventCSV'
    ),
    path(
        'finances-byevent/<slug:year>/csv/',
        FinancesByEventView.as_view(as_csv=True), name='financesByEventCSV'
    ),
    path('finances-byevent/', FinancesByEventView.as_view(), name='financesByEvent'),

    path('finances/expenses/<slug:year>/csv/', AllExpensesViewCSV.as_view(), name='allexpensesCSV'),
    path('finances/revenues/<slug:year>/csv/', AllRevenuesViewCSV.as_view(), name='allrevenuesCSV'),

    path('compensation/update/', CompensationRuleUpdateView.as_view(), name='updateCompensationRules'),
    path('compensation/reset/', CompensationRuleResetView.as_view(), name='resetCompensationRules'),
]
