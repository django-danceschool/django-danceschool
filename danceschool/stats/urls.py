from django.urls import path

from . import stats
from .views import SchoolStatsView

urlpatterns = [
    # These are stats CSV queries that will be eventually moved to the management app
    path('', SchoolStatsView.as_view(), name='schoolStatsView'),

    path('monthlyperformance/csv/', stats.MonthlyPerformanceCSV, name='MonthlyPerformanceCSV'),
    path('monthlyperformance/json/', stats.MonthlyPerformanceJSON, name='MonthlyPerformanceJSON'),

    path('classcounthistogram/csv/', stats.ClassCountHistogramCSV, name='ClassCountHistogramCSV'),
    path('classcounthistogram/json/', stats.ClassCountHistogramJSON, name='ClassCountHistogramJSON'),

    path('averagesbyclasstype/csv/', stats.AveragesByClassTypeCSV, name='AveragesByClassTypeCSV'),
    path('averagesbyclasstype/json/', stats.AveragesByClassTypeJSON, name='AveragesByClassTypeJSON'),

    path('classtypemonthly/json/', stats.ClassTypeMonthlyJSON, name='ClassTypeMonthlyJSON'),

    path('locationperformance/csv/', stats.LocationPerformanceCSV, name='LocationPerformanceCSV'),
    path('locationperformance/json/', stats.LocationPerformanceJSON, name='LocationPerformanceJSON'),

    path('advanceregistration/json/', stats.AdvanceRegistrationDaysJSON, name='AdvanceRegistrationDaysJSON'),
    path('registrationhours/json/', stats.RegistrationHoursJSON, name='RegistrationHoursJSON'),
    path('multiregistration/json/', stats.MultiRegistrationJSON, name='MultiRegistrationJSON'),

    path(
        'registrationtypeaverages/json/', stats.RegistrationTypeAveragesJSON,
        name='RegistrationTypeAveragesJSON'
    ),
    path('referralcounts/json/', stats.RegistrationReferralCountsJSON, name='RegistrationReferralCountsJSON'),

    path('bestcustomers/json/', stats.getBestCustomersJSON, name='bestCustomersJSON'),
]
