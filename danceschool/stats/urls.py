from django.conf.urls import re_path

from . import stats
from .views import SchoolStatsView

urlpatterns = [
    # These are stats CSV queries that will be eventually moved to the management app
    re_path(r'^', SchoolStatsView.as_view(),name='schoolStatsView'),

    re_path(r'^monthlyperformance/csv/', stats.MonthlyPerformanceCSV,name='MonthlyPerformanceCSV'),
    re_path(r'^monthlyperformance/json/', stats.MonthlyPerformanceJSON,name='MonthlyPerformanceJSON'),

    re_path(r'^classcounthistogram/csv/',stats.ClassCountHistogramCSV,name='ClassCountHistogramCSV'),
    re_path(r'^classcounthistogram/json/',stats.ClassCountHistogramJSON,name='ClassCountHistogramJSON'),

    re_path(r'^averagesbyclasstype/csv/',stats.AveragesByClassTypeCSV,name='AveragesByClassTypeCSV'),
    re_path(r'^averagesbyclasstype/json/',stats.AveragesByClassTypeJSON,name='AveragesByClassTypeJSON'),

    re_path(r'^classtypemonthly/json/',stats.ClassTypeMonthlyJSON,name='ClassTypeMonthlyJSON'),

    re_path(r'^locationperformance/csv/',stats.LocationPerformanceCSV,name='LocationPerformanceCSV'),
    re_path(r'^locationperformance/json/',stats.LocationPerformanceJSON,name='LocationPerformanceJSON'),

    re_path(r'^advanceregistration/json/',stats.AdvanceRegistrationDaysJSON,name='AdvanceRegistrationDaysJSON'),
    re_path(r'^registrationhours/json/',stats.RegistrationHoursJSON,name='RegistrationHoursJSON'),
    re_path(r'^multiregistration/json/',stats.MultiRegistrationJSON,name='MultiRegistrationJSON'),

    re_path(r'^registrationtypeaverages/json/',stats.RegistrationTypeAveragesJSON,name='RegistrationTypeAveragesJSON'),
    re_path(r'^referralcounts/json/',stats.RegistrationReferralCountsJSON,name='RegistrationReferralCountsJSON'),

    re_path(r'^bestcustomers/json/',stats.getBestCustomersJSON,name='bestCustomersJSON'),
]
