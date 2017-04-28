from django.db.models import Count, Avg, Sum, IntegerField, Case, When, Q, Min, FloatField, F
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.db import connection

from datetime import datetime
from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from urllib.parse import unquote
from collections import Counter
from bisect import bisect
from calendar import month_name
import json

from danceschool.core.models import Customer, Series, EventOccurrence, Registration, EventRegistration, DanceTypeLevel, Location
from danceschool.core.constants import getConstant


def getDateTimeFromGet(request,key):
    '''
    This function just parses the request GET data for the requested key,
    and returns it in datetime format, returning none if the key is not
    available or is in incorrect format.
    '''
    if request.GET.get(key,''):
        try:
            return datetime.strptime(unquote(request.GET.get(key,'')),'%Y-%m-%d')
        except:
            pass
    return None


def getAveragesByClassType(startDate=None,endDate=None):

    # If a date filter was passed in GET, then apply it
    when_all = {
        'classdescription__series__eventregistration__cancelled': False,
        'classdescription__series__eventregistration__dropIn': False
    }
    when_lead = {'classdescription__series__eventregistration__role__id': getConstant('general__roleLeadID')}
    when_follow = {'classdescription__series__eventregistration__role__id': getConstant('general__roleFollowID')}

    timeFilters = {}
    classFilters = {}
    if startDate:
        timeFilters['classdescription__series__startTime__gte'] = startDate
        classFilters['startTime__gte'] = startDate
    if endDate:
        timeFilters['classdescription__series__startTime__lte'] = endDate
        classFilters['startTime__lte'] = endDate

    when_all.update(timeFilters)
    when_lead.update(when_all)
    when_follow.update(when_all)

    registration_counts = list(DanceTypeLevel.objects.annotate(
        registrations=Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),
        leads=Sum(Case(When(Q(**when_lead),then=1),output_field=IntegerField())),
        follows=Sum(Case(When(Q(**when_follow),then=1),output_field=IntegerField()))).values_list('name','danceType__name','registrations','leads','follows'))
    class_counter = Counter([(x.classDescription.danceTypeLevel.name, x.classDescription.danceTypeLevel.danceType.name) for x in Series.objects.filter(**classFilters).distinct()])

    results = {}
    for list_item in registration_counts:
        type_name = ' '.join((str(list_item[0]),str(list_item[1])))

        results[type_name] = {
            'registrations': list_item[2],
            'leads': list_item[3],
            'follows': list_item[4]
        }
    for k,count in class_counter.items():
        type_name = ' '.join((str(k[0]),str(k[1])))
        results[type_name].update({
            'series': count
        })
    for k,v in results.items():
        if results[k].get('series'):
            results[k].update({
                'avgRegistrations': (results[k]['registrations'] or 0) / float(results[k]['series']),
                'avgLeads': (results[k]['leads'] or 0) / float(results[k]['series']),
                'avgFollows': (results[k]['follows'] or 0) / float(results[k]['series']),
            })

    return results


@staff_member_required
def AveragesByClassTypeJSON(request):

    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    results = getAveragesByClassType(startDate,endDate)

    # Needs to return a list, not a dict
    # Also, filter out types with no series or registrations
    # and sort descending
    results_list = [dict({'type': k},**dict(v)) for k,v in results.items() if v.get('series') or v.get('registrations')]
    sorted_list = sorted(results_list, key=lambda k: k['series'],reverse=True)
    return JsonResponse(sorted_list,safe=False)


@staff_member_required
def AveragesByClassTypeCSV(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="averagesByClassDescriptionType.csv"'

    writer = csv.writer(response)

    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    results = getAveragesByClassType(startDate,endDate)

    # Note: These are not translated because the chart Javascript looks for these keys
    writer.writerow(['Class Type','Total Classes','Total Students','Total Leads','Total Follows','Avg. Students/Class','Avg. Leads/Class','Avg. Follows/Class'])

    for key,value in results.items():

        writer.writerow([
            key,
            value.get('series',0),
            value.get('registrations',0),
            value.get('leads',0),
            value.get('follows',0),
            value.get('avgRegistrations',None),
            value.get('avgLeads',None),
            value.get('avgFollows',None),
        ])

    return response


def getClassTypeMonthlyData(year=None, series=None, typeLimit=None):
    '''
    To break out by class type and month simultaneously, get data for each
    series and aggregate by class type.
    '''

    # If no year specified, report current year to date.
    if not year:
        year = datetime.now().year

    # Report data on all students registered unless otherwise specified
    if series not in ['registrations','leads','follows','studenthours']:
        series = 'registrations'

    when_all = {
        'eventregistration__dropIn': False,
        'eventregistration__cancelled': False,
    }

    when_lead = {'eventregistration__role__id': getConstant('general__roleLeadID')}
    when_follow = {'eventregistration__role__id': getConstant('general__roleFollowID')}

    when_lead.update(when_all)
    when_follow.update(when_all)

    series_counts = Series.objects.filter(year=year).annotate(
        registrations=Sum(Case(When(Q(**when_all),then=1),output_field=FloatField())),
        leads=Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),
        follows=Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),
    ).annotate(studenthours=F('duration') * F('registrations')).select_related('classDescription__danceTypeLevel__danceType','classDescription__danceTypeLevel')

    # If no limit specified on number of types, then do not aggregate dance types.
    # Otherwise, report the typeLimit most common types individually, and report all
    # others as other.  This gets tuples of names and counts
    dance_type_counts = [(dance_type,count) for dance_type,count in Counter([x.classDescription.danceTypeLevel for x in series_counts]).items()]
    dance_type_counts.sort(key=lambda k: k[1],reverse=True)

    if typeLimit:
        dance_types = [x[0] for x in dance_type_counts[:typeLimit]]
    else:
        dance_types = [x[0] for x in dance_type_counts]

    results = []

    # Month by month, calculate the result data
    for month in range(1,13):
        this_month_result = {
            'month': month,
            'month_name': month_name[month],
        }
        for dance_type in dance_types:
            this_month_result[dance_type.__str__()] = \
                series_counts.filter(classDescription__danceTypeLevel=dance_type,month=month).aggregate(Sum(series))['%s__sum' % series]

        if typeLimit:
            this_month_result['Other'] = \
                series_counts.filter(month=month).exclude(classDescription__danceTypeLevel__in=dance_types).aggregate(Sum(series))['%s__sum' % series]

        results.append(this_month_result)

    # Now get totals
    totals_result = {
        'month': 'Totals',
        'month_name': 'totals',
    }

    for dance_type in dance_types:
        totals_result[dance_type.__str__()] = \
            series_counts.filter(classDescription__danceTypeLevel=dance_type).aggregate(Sum(series))['%s__sum' % series]

    if typeLimit:
        totals_result['Other'] = \
            series_counts.exclude(classDescription__danceTypeLevel__in=dance_types).aggregate(Sum(series))['%s__sum' % series]

    results.append(totals_result)

    return results


def ClassTypeMonthlyJSON(request):
    try:
        year = int(request.GET.get('year'))
    except:
        year = None

    try:
        typeLimit = int(request.GET.get('typeLimit'))
    except:
        typeLimit = None

    series = request.GET.get('series')

    results = getClassTypeMonthlyData(year=year,series=series,typeLimit=typeLimit)
    return JsonResponse(results, safe=False)


def getClassCountHistogramData(cohortStart=None,cohortEnd=None):

    # Note: Bins are inclusive, and 99999 means 'or more'.  That should last us awhile.
    bins = [
        (1,1),
        (2,2),
        (3,3),
        (4,4),
        (5,5),
        (6,6),
        (7,7),
        (8,8),
        (9,9),
        (10,15),
        (16,20),
        (21,99999)]

    when_all = {
        'eventregistration__dropIn': False,
        'eventregistration__cancelled':False,
    }
    when_lead = {'eventregistration__role__id': getConstant('general__roleLeadID')}
    when_follow = {'eventregistration__role__id': getConstant('general__roleFollowID')}

    cohortFilters = {}

    if cohortStart:
        cohortFilters['eventregistration__event__startTime__min__gte'] = cohortStart

    if cohortEnd:
        cohortFilters['eventregistration__event__startTime__min__lte'] = cohortEnd

    customers = Customer.objects.annotate(
        Min('eventregistration__event__startTime'),
        registrations=Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),
        leads=Sum(Case(When(Q(**when_lead),then=1),output_field=IntegerField())),
        follows=Sum(Case(When(Q(**when_follow),then=1),output_field=IntegerField()))).filter(**cohortFilters).distinct()

    totalCustomers = customers.filter(registrations__gt=0).count()
    totalLeaders = customers.filter(leads__gt=0).count()
    totalFollowers = customers.filter(follows__gt=0).count()

    # Get the list of customers, leaders, and followers, as well as
    # the total classes they have taken
    totalClasses = [x.registrations for x in customers if x.registrations]
    totalClasses.sort()
    totalClassesLeaders = [x.leads for x in customers if x.leads]
    totalClassesLeaders.sort()
    totalClassesFollowers = [x.follows for x in customers if x.follows]
    totalClassesFollowers.sort()

    results = {}
    lastAll = 0
    lastLeaders = 0
    lastFollowers = 0

    for this_bin in bins:
        range_max = this_bin[1]

        if this_bin[0] == this_bin[1]:
            this_label = '%s' % this_bin[0]
        elif this_bin[1] == 99999:
            this_label = '%s or more' % this_bin[0]
        else:
            this_label = '%s-%s' % this_bin

        i_all = bisect(totalClasses,range_max,lastAll)
        i_leaders = bisect(totalClassesLeaders,range_max,lastLeaders)
        i_followers = bisect(totalClassesFollowers,range_max,lastFollowers)

        # Note: These are not translated because the chart Javascript looks for these keys
        results.update({
            this_label:
            {
                '# Students': (i_all - lastAll),
                '# Leaders': (i_leaders - lastLeaders),
                '# Followers': (i_followers - lastFollowers),
                'Pct. Students': 100 * (i_all - lastAll) / float(totalCustomers),
                'Pct. Leaders': 100 * (i_leaders - lastLeaders) / float(totalLeaders),
                'Pct. Followers': 100 * (i_followers - lastFollowers) / float(totalFollowers),
                'bin': this_bin,
            },
        })
        lastAll = i_all
        lastLeaders = i_leaders
        lastFollowers = i_followers

    return results


@staff_member_required
def ClassCountHistogramJSON(request):
    cohortStart = getDateTimeFromGet(request,'cohortStart')
    cohortEnd = getDateTimeFromGet(request,'cohortEnd')
    results = getClassCountHistogramData(cohortStart=cohortStart,cohortEnd=cohortEnd)

    # Needs to return a sorted list, not a dict
    results_list = [dict({'bin_label': k},**dict(v)) for k,v in results.items()]
    sorted_list = sorted(results_list, key=lambda k: k['bin'][0])

    return JsonResponse(sorted_list,safe=False)


@staff_member_required
def ClassCountHistogramCSV(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="studentHistogramData.csv"'

    cohortStart = getDateTimeFromGet(request,'cohortStart')
    cohortEnd = getDateTimeFromGet(request,'cohortEnd')
    results = getClassCountHistogramData(cohortStart=cohortStart,cohortEnd=cohortEnd)

    writer = csv.writer(response)

    # Note: These are not translated because the chart Javascript looks for these keys
    writer.writerow(['# of Classes','Pct. Students','Pct. Leaders','Pct. Followers','# Students','# Leaders','# Followers'])

    for k,v in results.items():
        writer.writerow([
            k,
            v.get('Pct. Students',None),
            v.get('Pct. Leaders',None),
            v.get('Pct. Followers',None),
            v.get('# Students',None),
            v.get('# Leaders',None),
            v.get('# Followers',None),
        ])

    return response


def getMonthlyPerformance():
    '''
    This function does the work of compiling monthly performance data
    that can either be rendered as CSV or as JSON
    '''
    when_all = {
        'eventregistration__dropIn': False,
        'eventregistration__cancelled': False,
    }

    # Get objects at the Series level so that we can calculate StudentHours
    series_counts = list(Series.objects.annotate(
        eventregistrations=Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),)
        .values('year','month','eventregistrations','duration'))

    for series in series_counts:
        series['studenthours'] = (series.get('eventregistrations') or 0) * (series.get('duration') or 0)

    all_years = set([x['year'] for x in series_counts])

    dataseries_list = ['EventRegistrations', 'Registrations','Hours','StudentHours','AvgStudents']

    yearTotals = {}

    # Initialize dictionaries
    for dataseries in dataseries_list:
        yearTotals[dataseries] = {'MonthlyAverage': {}}
        for year in all_years:
            yearTotals[dataseries][year] = {}

    # Fill in by year and month for a cleaner looping process
    for year in all_years:

        # Monthly Totals
        for month in range(1,13):
            # Total EventRegistrations per month is retrieved by the query above.
            yearTotals['EventRegistrations'][year][month] = sum([x['eventregistrations'] or 0 for x in series_counts if x['month'] == month and x['year'] == year])

            # Total Registrations per month and hours per month require a separate query for each month
            yearTotals['Registrations'][year][month] = len(Registration.objects.filter(eventregistration__dropIn=False, eventregistration__cancelled=False,eventregistration__event__year=year,eventregistration__event__month=month).distinct())
            yearTotals['Hours'][year][month] = sum([x['duration'] or 0 for x in series_counts if x['month'] == month and x['year'] == year])
            yearTotals['StudentHours'][year][month] = sum([x['studenthours'] or 0 for x in series_counts if x['month'] == month and x['year'] == year])

            if yearTotals['Hours'][year][month] > 0:
                yearTotals['AvgStudents'][year][month] = yearTotals['StudentHours'][year][month] / float(yearTotals['Hours'][year][month])
            else:
                yearTotals['AvgStudents'][year][month] = 0

        # Annual Totals
        for sub_series in ['EventRegistrations','Registrations','Hours','StudentHours']:
            yearTotals[sub_series][year]['Total'] = sum([x for x in yearTotals[sub_series][year].values()])

        # Annual (Monthly) Averages
        month_count = len([x for k,x in yearTotals['Hours'][year].items() if k in range(1,13) and x > 0])
        if month_count > 0:
            for sub_series in ['EventRegistrations','Registrations','Hours','StudentHours']:
                yearTotals[sub_series][year]['Average'] = yearTotals[sub_series][year]['Total'] / float(month_count)
            yearTotals['AvgStudents'][year]['Average'] = yearTotals['StudentHours'][year]['Total'] / float(yearTotals['Hours'][year]['Total'])

    # Monthly Averages
    for month in range(1,13):
        yearly_hours_data = [x[month] for k,x in yearTotals['Hours'].items() if k in all_years and x[month] > 0]
        yearly_studenthours_data = [x[month] for k,x in yearTotals['StudentHours'].items() if k in all_years and x[month] > 0]
        yearly_eventregistrations_data = [x[month] for k,x in yearTotals['EventRegistrations'].items() if k in all_years and yearTotals['Hours'][k][month] > 0]
        yearly_registrations_data = [x[month] for k,x in yearTotals['Registrations'].items() if k in all_years and yearTotals['Hours'][k][month] > 0]

        year_count = len(yearly_hours_data)

        if year_count > 0:
            yearTotals['EventRegistrations']['MonthlyAverage'][month] = sum([x for x in yearly_eventregistrations_data]) / year_count
            yearTotals['Registrations']['MonthlyAverage'][month] = sum([x for x in yearly_registrations_data]) / year_count
            yearTotals['Hours']['MonthlyAverage'][month] = sum([x for x in yearly_hours_data]) / year_count
            yearTotals['StudentHours']['MonthlyAverage'][month] = sum([x for x in yearly_studenthours_data]) / year_count
            yearTotals['AvgStudents']['MonthlyAverage'][month] = yearTotals['StudentHours']['MonthlyAverage'][month] / float(yearTotals['Hours']['MonthlyAverage'][month])

    return yearTotals


@staff_member_required
def MonthlyPerformanceJSON(request):
    series = request.GET.get('series')
    if series not in ['AvgStudents','Registrations','EventRegistrations','Hours','StudentHours']:
        series = 'EventRegistrations'

    yearTotals = getMonthlyPerformance()[series]

    # Return JSON as lists, not as dictionaries, for c3.js
    # yearTotals_list = [dict(v,**{'year':k}) for k, v in yearTotals.items()]

    # Now make the lists so that there is one row per month, not one row per year,
    # to make things easier for working with c3.js.yearTotals
    monthTotals_list = []

    years = list(set([k for k,v in yearTotals.items()]))

    # Only include calendar months for graphing
    for month in range(1,13):
        this_month_data = {'month': month, 'month_name': month_name[month]}
        for year in years:
            this_month_data[year] = yearTotals[year].get(month)
        monthTotals_list.append(this_month_data)

    monthTotals_list_sorted = sorted(monthTotals_list, key=lambda k: k['month'])

    return JsonResponse(monthTotals_list_sorted,safe=False)


@staff_member_required
def MonthlyPerformanceCSV(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="monthlyPerformance.csv"'

    writer = csv.writer(response)

    yearTotals = getMonthlyPerformance()

    all_years = [k for k in yearTotals['Hours'].keys() if k != 'MonthlyAverage']
    all_years.sort()

    # Write headers first
    headers_list = ['Data Series','Month','All-Time Avg.']
    for year in all_years:
        headers_list.append(str(year))
    writer.writerow(headers_list)

    # Note: These are not translated because the chart Javascript looks for these keys
    yearTotals_keys = {
        'Total Student-Hours': 'StudentHours',
        'Avg. Students/Hour': 'AvgStudents',
        'Hours of Instruction': 'Hours',
        'Unique Registrations': 'Registrations',
        'Total Students': 'EventRegistrations',
    }

    for series,key in yearTotals_keys.items():
        for month in range(1,13):
            this_row = [
                series,
                month_name[month],
                yearTotals[key]['MonthlyAverage'][month],
            ]

            for year in all_years:
                this_row.append(yearTotals[key][year][month])

            writer.writerow(this_row)

    return response


def getLocationPerformance(startDate=None,endDate=None):

    # This time filter ensures that only non-special Series are included.
    timeFilters = {'event__series__special': False}

    if startDate:
        timeFilters['event__startTime__gte'] = startDate
    if endDate:
        timeFilters['event__startTime__lte'] = endDate

    seriesCounts = list(Location.objects.values_list('name').filter(**timeFilters).distinct().annotate(Count('event')))

    timeFilters.update({
        'event__eventregistration__dropIn':False,
        'event__eventregistration__cancelled':False
    })

    eventRegistrationCounts = list(Location.objects.values_list('name').filter(**timeFilters).distinct().annotate(Count('event')))

    results = {}
    for list_item in seriesCounts:
        results[list_item[0]] = {'series': list_item[1]}
    for list_item in eventRegistrationCounts:
        results[list_item[0]].update({'registrations': list_item[1]})

    return results


@staff_member_required
def LocationPerformanceJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')
    results = getLocationPerformance(startDate,endDate)

    # Needs to return a list, not a dict
    results_list = [dict({'name': k},**dict(v)) for k,v in results.items()]
    return JsonResponse(results_list,safe=False)


@staff_member_required
def LocationPerformanceCSV(request):
    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="locationPerformance.csv"'

    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    results = getLocationPerformance(startDate,endDate)

    writer = csv.writer(response)

    # Note: These are not translated because the chart Javascript looks for these keys
    writer.writerow(['Location','# Series','# Students','Avg. Students/Series'])

    for location,data in results.items():
        writer.writerow([
            location,  # The location name
            data.get('series',0),  # The num. of series taught there
            data.get('registrations',0),  # The num. of students taught there
            float(data.get('registrations',0)) / data.get('series',1)
        ])

    return response


def getRegistrationTypesAveragesByYear():
    srs = EventRegistration.objects.all()
    eligible_years = [x['event__year'] for x in srs.values('event__year').annotate(Count('event__year'))]
    eligible_years.sort()

    year_averages = []

    for year in eligible_years:
        this_year_results = srs.filter(event__year=year).annotate(
            student=Case(When(registration__student=True,then=100),default=0,output_field=IntegerField()),
            door=Case(When(registration__paidOnline=False,then=100),default=0,output_field=IntegerField()),
            droppedIn=Case(When(dropIn=True,then=100),default=0,output_field=IntegerField()),
            cancellation=Case(When(cancelled=True,then=100),default=0,output_field=IntegerField()),
        ).aggregate(Student=Avg('student'),Door=Avg('door'),DropIn=Avg('droppedIn'),Cancelled=Avg('cancellation'),year=Min('event__year'))

        year_averages.append(this_year_results)

    return year_averages


@staff_member_required
def RegistrationTypeAveragesJSON(request):
    results = getRegistrationTypesAveragesByYear()
    return JsonResponse(results,safe=False)


def getRegistrationReferralCounts(startDate,endDate):
    '''
    When a user accesses the class registration page through a
    referral URL, the marketing_id gets saved in the extra JSON
    data associated with that registration.  This just returns
    counts associated with how often given referral terms appear
    in a specified time window (i.e. how many people signed up
    by clicking through a referral button).
    '''

    timeFilters = {}
    if startDate:
        timeFilters['dateTime__gte'] = startDate
    if endDate:
        timeFilters['dateTime__lt'] = endDate

    reg_count = Registration.objects.filter(**timeFilters).count()

    regs = Registration.objects.filter(**timeFilters).filter(data__marketing_id__isnull=False)
    counter = Counter([x.data['marketing_id'] for x in regs])

    results = [{'code': k, 'count': v} for k,v in counter.items()]

    results.append({
        'code': 'None',
        'count':reg_count - sum([x['count'] for x in results])
    })

    return results


@staff_member_required
def RegistrationReferralCountsJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')
    results = getRegistrationReferralCounts(startDate,endDate)
    return JsonResponse(results,safe=False)


@staff_member_required
def getGeneralStats(request):
    # total number of students:
    totalStudents = Customer.objects.distinct().count()
    numSeries = Series.objects.distinct().count()
    totalSeriesRegs = EventRegistration.objects.filter(**{'dropIn':False,'cancelled':False}).values('event','customer__user__email').distinct().count()

    # time studio in existence:
    firstClass = EventOccurrence.objects.order_by('startTime').values('startTime').first()
    if firstClass:
        firstStartTime = firstClass['startTime']
    else:
        firstStartTime = datetime.now()

    timeDiff = relativedelta(datetime.now(),firstStartTime)
    totalTime = '%s years, %s months, %s days' % (timeDiff.years, timeDiff.months,timeDiff.days)

    return (totalStudents,numSeries,totalSeriesRegs,totalTime)
