from django.conf.urls import url

from . import stats
from .views import SchoolStatsView

urlpatterns = [
    # These are stats CSV queries that will be eventually moved to the management app
    url(r'^$', SchoolStatsView.as_view(),name='schoolStatsView'),

    url(r'^monthlyperformance/csv/$', stats.MonthlyPerformanceCSV,name='MonthlyPerformanceCSV'),
    url(r'^monthlyperformance/json/$', stats.MonthlyPerformanceJSON,name='MonthlyPerformanceJSON'),

    url(r'^classcounthistogram/csv/$',stats.ClassCountHistogramCSV,name='ClassCountHistogramCSV'),
    url(r'^classcounthistogram/json/$',stats.ClassCountHistogramJSON,name='ClassCountHistogramJSON'),

    url(r'^averagesbyclasstype/csv/$',stats.AveragesByClassTypeCSV,name='AveragesByClassTypeCSV'),
    url(r'^averagesbyclasstype/json/$',stats.AveragesByClassTypeJSON,name='AveragesByClassTypeJSON'),

    url(r'^classtypemonthly/json/$',stats.ClassTypeMonthlyJSON,name='ClassTypeMonthlyJSON'),

    url(r'^locationperformance/csv/$',stats.LocationPerformanceCSV,name='LocationPerformanceCSV'),
    url(r'^locationperformance/json/$',stats.LocationPerformanceJSON,name='LocationPerformanceJSON'),

    url(r'^advanceregistration/json/$',stats.AdvanceRegistrationDaysJSON,name='AdvanceRegistrationDaysJSON'),
    url(r'^registrationhours/json/$',stats.RegistrationHoursJSON,name='RegistrationHoursJSON'),
    url(r'^multiregistration/json/$',stats.MultiRegistrationJSON,name='MultiRegistrationJSON'),

    url(r'^registrationtypeaverages/json/$',stats.RegistrationTypeAveragesJSON,name='RegistrationTypeAveragesJSON'),
    url(r'^referralcounts/json/$',stats.RegistrationReferralCountsJSON,name='RegistrationReferralCountsJSON'),

    url(r'^bestcustomers/json/$',stats.getBestCustomersJSON,name='bestCustomersJSON'),
]
