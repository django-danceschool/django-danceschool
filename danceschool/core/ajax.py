from django.http import HttpResponse, JsonResponse
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import EventOccurrence, SeriesTeacher, EventRegistration, EmailTemplate


class UserAccountInfo(View):
    ''' This view just returns the name and email address information for the currently logged in user '''

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        context = {}

        if not request.user.is_authenticated:
            return JsonResponse(context)

        customer = getattr(request.user,'customer',None)

        if customer:
            context.update({
                'customer': True,
                'first_name': customer.first_name or request.user.first_name,
                'last_name': customer.last_name or request.user.last_name,
                'email': customer.email or request.user.email,
                'phone': customer.phone,
            })
        else:
            context.update({
                'customer': False,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            })

        # Also add any outstanding messages (e.g. login successful message) to be
        # relayed to the user when this information is used.
        context['messages'] = []

        for message in messages.get_messages(request):
            context['messages'].append({
                "level": message.level,
                "message": message.message,
                "extra_tags": message.tags,
            })

        return JsonResponse(context)


def updateSeriesAttributes(request):
    '''
    This function handles the filtering of available series classes and seriesteachers when a series
    is chosen on the Substitute Teacher reporting form.
    '''
    if request.method == 'POST' and request.POST.get('event'):
        series_option = request.POST.get('event') or None
        seriesClasses = EventOccurrence.objects.filter(event__id=series_option)
        seriesTeachers = SeriesTeacher.objects.filter(event__id=series_option)
    else:
        # Only return attributes for valid requests
        return JsonResponse({})

    outClasses = {}
    for option in seriesClasses:
        outClasses[str(option.id)] = option.__str__()

    outTeachers = {}
    for option in seriesTeachers:
        outTeachers[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_occurrences': outClasses,
        'id_replacedStaffMember': outTeachers,
    })


def processCheckIn(request):
    '''
    This function handles the Ajax call made when a user is marked as checked in
    '''

    if request.method == 'POST':
        event_id = request.POST.get('event_id')
        reg_ids = request.POST.getlist('reg_id')

        if not event_id:
            return HttpResponse(_("Error at start."))

        # Get all possible registrations, so that we can set those that are not included to False (and set those that are included to True)
        all_eventreg = list(EventRegistration.objects.filter(event__id=event_id))

        for this_reg in all_eventreg:
            if str(this_reg.registration.id) in reg_ids and not this_reg.checkedIn:
                this_reg.checkedIn = True
                this_reg.save()
            elif str(this_reg.registration.id) not in reg_ids and this_reg.checkedIn:
                this_reg.checkedIn = False
                this_reg.save()
        return HttpResponse("OK.")


def getEmailTemplate(request):
    '''
    This function handles the Ajax call made when a user wants a specific email template
    '''
    if request.method != 'POST':
        return HttpResponse(_('Error, no POST data.'))

    if not hasattr(request,'user'):
        return HttpResponse(_('Error, not authenticated.'))

    template_id = request.POST.get('template')

    if not template_id:
        return HttpResponse(_("Error, no template ID provided."))

    try:
        this_template = EmailTemplate.objects.get(id=template_id)
    except ObjectDoesNotExist:
        return HttpResponse(_("Error getting template."))

    if this_template.groupRequired and this_template.groupRequired not in request.user.groups.all():
        return HttpResponse(_("Error, no permission to access this template."))
    if this_template.hideFromForm:
        return HttpResponse(_("Error, no permission to access this template."))

    return JsonResponse({
        'subject': this_template.subject,
        'content': this_template.content,
        'html_content': this_template.html_content,
        'richTextChoice': this_template.richTextChoice,
    })
