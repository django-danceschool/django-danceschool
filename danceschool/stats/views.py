from django.views.generic import TemplateView
from django.db.models import Count

from datetime import datetime
import six
from braces.views import PermissionRequiredMixin

from danceschool.core.models import Instructor, SeriesTeacher, Customer

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


class SchoolStatsView(PermissionRequiredMixin, TemplateView):
    template_name = 'stats/schoolstats.html'
    permission_required = 'core.view_school_stats'

    def get_context_data(self, **kwargs):
        from .stats import getGeneralStats

        request = self.request
        context_data = kwargs

        (totalStudents,numSeries,totalSeriesRegs,totalTime) = getGeneralStats(request)

        bestCustomersLastTwelveMonths = Customer.objects.values('user__first_name','user__last_name').filter(**{'eventregistration__registration__dateTime__gte':datetime(datetime.now().year - 1,datetime.now().month,datetime.now().day),'eventregistration__dropIn':False,'eventregistration__cancelled':False}).annotate(Count('eventregistration')).order_by('-eventregistration__count')[:20]
        bestCustomersAllTime = Customer.objects.values('user__first_name','user__last_name').filter(**{'eventregistration__dropIn':False,'eventregistration__cancelled':False}).annotate(Count('eventregistration')).order_by('-eventregistration__count')[:20]

        mostActiveTeachersThisYear = SeriesTeacher.objects.filter(event__year=datetime.now().year).exclude(staffMember__instructor__status=Instructor.InstructorStatus.guest).values_list('staffMember__firstName','staffMember__lastName').annotate(Count('staffMember')).order_by('-staffMember__count')

        context_data.update({
            'totalStudents':totalStudents,
            'numSeries':numSeries,
            'totalSeriesRegs':totalSeriesRegs,
            'totalTime':totalTime,
            'bestCustomersAllTime': bestCustomersAllTime,
            'bestCustomersLastTwelveMonths': bestCustomersLastTwelveMonths,
            'mostActiveTeachersThisYear': mostActiveTeachersThisYear,
        })
        return context_data
