from django.http import JsonResponse
from django.db.models import Count, Q, Case, When, IntegerField
from django.contrib.admin.views.decorators import staff_member_required

from collections import Counter

from danceschool.core.models import Registration
from danceschool.core.utils.requests import getDateTimeFromGet

from .models import DiscountCombo


@staff_member_required
def popularDiscountsJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    timeLimit = Q(registrationdiscount__registration__dateTime__isnull=False)

    if startDate:
        timeLimit = timeLimit & Q(registrationdiscount__registration__dateTime__gte=startDate)
    if endDate:
        timeLimit = timeLimit & Q(registrationdiscount__registration__dateTime__lte=endDate)

    uses = list(DiscountCombo.objects.annotate(
        counter=Count(Case(
            When(timeLimit, then=1), output_field=IntegerField())
        )).filter(counter__gt=0).values('name','counter').order_by('-counter')[:10])

    return JsonResponse(uses,safe=False)


@staff_member_required
def discountFrequencyJSON(request):
    startDate = getDateTimeFromGet(request,'startDate')
    endDate = getDateTimeFromGet(request,'endDate')

    timeLimit = Q()

    if startDate:
        timeLimit = timeLimit & Q(dateTime__gte=startDate)
    if endDate:
        timeLimit = timeLimit & Q(dateTime__lte=endDate)

    # Percentage of registrations using discounts
    discounts_counter_sorted = sorted(Counter(Registration.objects.filter(timeLimit).annotate(
        discounts_applied=Count('registrationdiscount')).values_list('discounts_applied',flat=True)).items())

    results_list = [{'discounts': x[0], 'count': x[1]} for x in discounts_counter_sorted]
    return JsonResponse(results_list,safe=False)
