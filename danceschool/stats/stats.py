from django.db.models import Count, Avg, Sum, IntegerField, Case, When, Q, Min, FloatField, F
from django.db.models.functions import TruncDate
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.utils.translation import ugettext as _
from django.utils import timezone

from dateutil.relativedelta import relativedelta
import unicodecsv as csv
from collections import Counter, OrderedDict
from bisect import bisect
from calendar import month_name
from datetime import datetime

from danceschool.core.models import Customer, Series, EventOccurrence, Registration, EventRegistration, DanceTypeLevel, Location, DanceRole, SeriesTeacher, Instructor
from danceschool.core.utils.requests import getDateTimeFromGet
from danceschool.core.utils.timezone import ensure_timezone


def getAveragesByClassType(startDate=None,endDate=None):

    # If a date filter was passed in GET, then apply it
    when_all = {
        'classdescription__series__eventregistration__cancelled': False,
        'classdescription__series__eventregistration__dropIn': False
    }

    timeFilters = {}
    classFilters = {}
    roleFilters = Q()

    if startDate:
        timeFilters['classdescription__series__startTime__gte'] = startDate
        classFilters['startTime__gte'] = startDate
        roleFilters = roleFilters & (Q(eventrole__event__startTime__gte=startDate) | Q(eventregistration__event__startTime__gte=startDate))
    if endDate:
        timeFilters['classdescription__series__startTime__lte'] = endDate
        classFilters['startTime__lte'] = endDate
        roleFilters = roleFilters & (Q(eventrole__event__startTime__lte=endDate) | Q(eventregistration__event__startTime__lte=endDate))

    when_all.update(timeFilters)

    role_list = DanceRole.objects.filter(roleFilters).distinct()

    annotations = {'registrations': Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField()))}
    values_list = ['name', 'danceType__name','registrations']

    for this_role in role_list:
        annotations[this_role.pluralName] = Sum(Case(When(Q(Q(**when_all) & Q(classdescription__series__eventregistration__role=this_role)),then=1),output_field=IntegerField()))
        values_list.append(this_role.pluralName)

    registration_counts = list(DanceTypeLevel.objects.annotate(**annotations).values_list(*values_list))
    class_counter = Counter([(x.classDescription.danceTypeLevel.name, x.classDescription.danceTypeLevel.danceType.name) for x in Series.objects.filter(**classFilters).distinct()])

    results = {}
    for list_item in registration_counts:
        type_name = ' '.join((str(list_item[0]),str(list_item[1])))

        results[type_name] = {
            str(_('Registrations')): list_item[2],
        }
        m = 3
        for this_role in role_list:
            results[type_name][str(_('Total %s' % this_role.pluralName))] = list_item[m]
            m += 1

    for k,count in class_counter.items():
        type_name = ' '.join((str(k[0]),str(k[1])))
        results[type_name].update({
            str(_('Series')): count
        })
    for k,v in results.items():
        if results[k].get(str(_('Series'))):
            results[k].update({
                str(_('Average Registrations')): (results[k][str(_('Registrations'))] or 0) / float(results[k][str(_('Series'))]),
            })
            for this_role in role_list:
                results[k][str(_('Average %s' % this_role.pluralName))] = (results[k][str(_('Total %s' % this_role.pluralName))] or 0) / float(results[k][str(_('Series'))])

    return results


@staff_member_required
def AveragesByClassTypeJSON(request):

    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    results = getAveragesByClassType(startDate,endDate)

    # Needs to return a list, not a dict
    # Also, filter out types with no series or registrations
    # and sort descending
    results_list = [dict({'type': k},**dict(v)) for k,v in results.items() if v.get(str(_('Series'))) or v.get(str(_('Registrations')))]
    sorted_list = sorted(results_list, key=lambda k: k[str(_('Series'))],reverse=True)
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

    role_names = [x.replace(str(_('Average ')),'') for x in results.keys() if x.startswith(str(_('Average ')))]

    header_list = [str(_('Class Type')),str(_('Total Classes')),str(_('Total Students')),str(_('Avg. Students/Class'))]
    for this_role in role_names:
        header_list += [str(_('Total %s' % this_role)), str(_('Avg. %s/Class' % this_role))]

    # Note: These are not translated because the chart Javascript looks for these keys
    writer.writerow(header_list)

    for key,value in results.items():
        this_row = [
            key,
            value.get(str(_('Series')),0),
            value.get(str(_('Registrations')),0),
            value.get(str(_('Average Registrations')),None),
        ]
        for this_role in role_names:
            this_row += [
                value.get(str(_('Total %s' % this_role)), 0),
                value.get(str(_('Average %s' % this_role)), 0)
            ]
        writer.writerow(this_row)

    return response


def getClassTypeMonthlyData(year=None, series=None, typeLimit=None):
    '''
    To break out by class type and month simultaneously, get data for each
    series and aggregate by class type.
    '''

    # If no year specified, report current year to date.
    if not year:
        year = timezone.now().year

    role_list = DanceRole.objects.distinct()

    # Report data on all students registered unless otherwise specified
    if series not in ['registrations','studenthours'] and series not in [x.pluralName for x in role_list]:
        series = 'registrations'

    when_all = {
        'eventregistration__dropIn': False,
        'eventregistration__cancelled': False,
    }

    annotations = {'registrations': Sum(Case(When(Q(**when_all),then=1),output_field=FloatField()))}

    for this_role in role_list:
        annotations[this_role.pluralName] = Sum(Case(When(Q(Q(**when_all) & Q(eventregistration__role=this_role)),then=1),output_field=FloatField()))

    series_counts = Series.objects.filter(year=year).annotate(**annotations).annotate(studenthours=F('duration') * F('registrations')).select_related('classDescription__danceTypeLevel__danceType','classDescription__danceTypeLevel')

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
    except (ValueError, TypeError):
        year = None

    try:
        typeLimit = int(request.GET.get('typeLimit'))
    except (ValueError, TypeError):
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

    cohortFilters = {}
    roleFilters = {}

    if cohortStart:
        cohortFilters['eventregistration__event__startTime__min__gte'] = cohortStart
        roleFilters['eventregistration__event__startTime__gte'] = cohortStart

    if cohortEnd:
        cohortFilters['eventregistration__event__startTime__min__lte'] = cohortEnd
        roleFilters['eventregistration__event__startTime__lte'] = cohortEnd

    role_list = DanceRole.objects.filter(**roleFilters).distinct()

    annotations = {
        'eventregistration__event__startTime__min': Min('eventregistration__event__startTime'),
        'registrations': Sum(Case(When(Q(**when_all),then=1),output_field=IntegerField())),
    }
    for this_role in role_list:
        annotations[this_role.pluralName] = Sum(Case(When(Q(Q(**when_all) & Q(eventregistration__role=this_role)),then=1),output_field=IntegerField()))

    customers = Customer.objects.annotate(**annotations).filter(**cohortFilters).distinct()

    totalCustomers = customers.filter(registrations__gt=0).count()
    totalClasses = [x.registrations for x in customers if x.registrations]
    totalClasses.sort()

    totalsByRole = {}

    for this_role in role_list:
        totalsByRole[this_role.pluralName] = {
            'customers': customers.filter(**{this_role.pluralName + '__gt': 0}).count(),
            'classes': [getattr(x,this_role.pluralName,None) for x in customers if getattr(x,this_role.pluralName,None)],
        }
        totalsByRole[this_role.pluralName]['classes'].sort()

    results = {}
    lastAll = 0
    lastByRole = {this_role.pluralName:0 for this_role in role_list}
    iByRole = {}

    for this_bin in bins:
        range_max = this_bin[1]

        if this_bin[0] == this_bin[1]:
            this_label = '%s' % this_bin[0]
        elif this_bin[1] == 99999:
            this_label = str(_('%s or more' % this_bin[0]))
        else:
            this_label = '%s-%s' % this_bin

        i_all = bisect(totalClasses,range_max,lastAll)
        iByRole = {
            this_role.pluralName:bisect(totalsByRole[this_role.pluralName]['classes'],range_max,lastByRole[this_role.pluralName])
            for this_role in role_list
        }

        # Note: These are not translated because the chart Javascript looks for these keys
        results.update({
            this_label:
            {
                str(_('# Students')): (i_all - lastAll),
                str(_('Percentage')): 100 * (i_all - lastAll) / (float(totalCustomers) or 1),
                'bin': this_bin,
            },
        })
        for this_role in role_list:
            results[this_label].update({
                '# ' + this_role.pluralName: (iByRole[this_role.pluralName] - lastByRole[this_role.pluralName]),
                'Percentage ' + this_role.pluralName: 100 * (
                    iByRole[this_role.pluralName] - lastByRole[this_role.pluralName]
                ) /
                (float(totalsByRole[this_role.pluralName]['customers']) or 1),
            })

        lastAll = i_all
        lastByRole = {this_role.pluralName:iByRole[this_role.pluralName] for this_role in role_list}

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
    header_row = ['# of Classes']

    keys = OrderedDict()
    for v in results.values():
        keys.update(v)

    header_row += [x for x in keys.keys()]
    writer.writerow(header_row)

    for k,v in results.items():
        this_row = [k]
        this_row += [v.get(x,None) for x in keys.keys()]
        writer.writerow(this_row)

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

    timeFilters = {}

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
            door=Case(When(registration__payAtDoor=False,then=100),default=0,output_field=IntegerField()),
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

    regs = Registration.objects.filter(**timeFilters)
    counter = Counter([x.data.get('marketing_id',None) for x in regs if isinstance(x.data,dict)] + [None for x in regs if not isinstance(x.data,dict)])

    results = [{'code': k or _('None'), 'count': v} for k,v in counter.items()]
    return results


@staff_member_required
def RegistrationReferralCountsJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')
    results = getRegistrationReferralCounts(startDate,endDate)
    return JsonResponse(results,safe=False)


@staff_member_required
def MultiRegistrationJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    timeFilters = {}

    if startDate:
        timeFilters['dateTime__gte'] = startDate
    if endDate:
        timeFilters['dateTime__lte'] = endDate

    er_counter_sorted = sorted(Counter(
        Registration.objects.filter(**timeFilters).annotate(
            er_count=Count('eventregistration')).values_list('er_count',flat=True)
    ).items())

    results_list = []
    cumulative = 0
    total = sum([x[1] for x in er_counter_sorted])

    for x in er_counter_sorted:
        cumulative += x[1]
        results_list.append({
            'items': x[0], 'count': x[1], 'cumulative': cumulative,
            'pct': 100 * (x[1] / total), 'cumulative_pct': 100 * (cumulative / total)
        })
    return JsonResponse(results_list,safe=False)


@staff_member_required
def RegistrationHoursJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    timeFilters = {}

    if startDate:
        timeFilters['dateTime__gte'] = startDate
    if endDate:
        timeFilters['dateTime__lte'] = endDate

    hours_counter_sorted = sorted(Counter(
        Registration.objects.filter(**timeFilters).annotate(
            er_sum=Sum('eventregistration__event__duration')).values_list('er_sum',flat=True)
    ).items())

    results_list = []
    cumulative = 0
    total = sum([x[1] for x in hours_counter_sorted])

    for x in hours_counter_sorted:
        cumulative += x[1]
        results_list.append({
            'hours': x[0], 'count': x[1], 'cumulative': cumulative,
            'pct': 100 * (x[1] / total), 'cumulative_pct': 100 * (cumulative / total)
        })
    return JsonResponse(results_list,safe=False)


@staff_member_required
def AdvanceRegistrationDaysJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    timeFilters = {}

    if startDate:
        timeFilters['dateTime__gte'] = startDate
    if endDate:
        timeFilters['dateTime__lte'] = endDate

    advance_days_sorted = sorted(Counter(
        Registration.objects.filter(**timeFilters).annotate(
            min_start=Min('eventregistration__event__startTime')
        ).annotate(
            advance=(TruncDate('dateTime') - TruncDate('min_start'))
        ).values_list(
            'advance',flat=True)
    ).items())

    results_list = []
    cumulative = 0
    total = sum([x[1] for x in advance_days_sorted])

    for x in advance_days_sorted:
        cumulative += x[1]
        results_list.append({
            'days': x[0], 'count': x[1], 'cumulative': cumulative,
            'pct': 100 * (x[1] / total), 'cumulative_pct': 100 * (cumulative / total)
        })
    return JsonResponse(results_list,safe=False)


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
        firstStartTime = timezone.now()

    timeDiff = relativedelta(timezone.now(),firstStartTime)
    totalTime = '%s years, %s months, %s days' % (timeDiff.years, timeDiff.months,timeDiff.days)

    return (totalStudents,numSeries,totalSeriesRegs,totalTime)


@staff_member_required
def getBestCustomersJSON(request):

    bestCustomersLastTwelveMonths = Customer.objects.values(
        'first_name','last_name'
    ).filter(**{
        'eventregistration__registration__dateTime__gte': ensure_timezone(
            datetime(timezone.now().year - 1,timezone.now().month,timezone.now().day)
        ),
        'eventregistration__dropIn':False,'eventregistration__cancelled':False
    }).annotate(Count('eventregistration')).order_by('-eventregistration__count')[:10]

    bestCustomersAllTime = Customer.objects.values(
        'first_name','last_name'
    ).filter(**{
        'eventregistration__dropIn':False,
        'eventregistration__cancelled':False
    }).annotate(Count('eventregistration')).order_by('-eventregistration__count')[:10]

    mostActiveTeachersThisYear = SeriesTeacher.objects.filter(
        event__year=timezone.now().year
    ).exclude(
        staffMember__instructor__status=Instructor.InstructorStatus.guest
    ).values_list(
        'staffMember__firstName','staffMember__lastName'
    ).annotate(Count('staffMember')).order_by('-staffMember__count')

    bestCustomerData = {
        'bestCustomersLastTwelveMonths': list(bestCustomersLastTwelveMonths),
        'bestCustomersAllTime': list(bestCustomersAllTime),
        'mostActiveTeachersThisYear': list(mostActiveTeachersThisYear),
    }

    return JsonResponse(bestCustomerData)
