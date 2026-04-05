from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.generic import DetailView, ListView, CreateView, UpdateView
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.messages.views import SuccessMessageMixin
from urllib.parse import unquote_plus
from braces.views import PermissionRequiredMixin, UserFormKwargsMixin
from calendar import month_name
import re

from ..models import StaffMember, Instructor, Event, EventOccurrence, EventStaffMember
from ..forms.staff import SubstituteReportingForm, StaffMemberBioChangeForm
from ..constants import getConstant
from ..mixins import StaffMemberObjectMixin, AdminSuccessURLMixin

import logging

logger = logging.getLogger(__name__)


class InstructorStatsView(StaffMemberObjectMixin, PermissionRequiredMixin, DetailView):
    model = StaffMember
    template_name = 'core/instructor_stats.html'
    permission_required = 'core.view_own_instructor_stats'

    def get_context_data(self, **kwargs):
        instructor = self.object
        context = {}

        context.update({
            'instructor': instructor,
            'prior_series': Event.objects.filter(
                startTime__lte=timezone.now(),
                eventstaffmember__staffMember=instructor).order_by('-startTime'),
            'upcoming_series': Event.objects.filter(
                startTime__gt=timezone.now(),
                eventstaffmember__staffMember=instructor).order_by('-startTime'),
        })

        if context['prior_series']:
            context.update({'first_series': context['prior_series'].last(), })
            context.update({
                'teaching_since': month_name[context['first_series'].month] + ' ' + str(context['first_series'].year),
                'student_count': sum([x.numRegistered for x in context['prior_series']]),
            })
        context.update({'series_count': len(context['prior_series']) + len(context['upcoming_series'])})

        # Note: This get the detailview's context, not all the mixins.  Supering itself led to an infinite loop.
        return super(DetailView, self).get_context_data(**context)


class OtherInstructorStatsView(InstructorStatsView):
    permission_required = 'core.view_other_instructor_stats'

    def get_object(self, queryset=None):
        if 'first_name' in self.kwargs and 'last_name' in self.kwargs:
            first_name = re.sub('^_$','', self.kwargs['first_name'])
            last_name = re.sub('^_$','', self.kwargs['last_name'])

            return get_object_or_404(
                StaffMember.objects.filter(
                    **{'firstName': unquote_plus(first_name).replace('_', ' '),
                        'lastName': unquote_plus(last_name).replace('_', ' ')})
                    )
        else:
            return None


############################################################
# View for instructors to report that they substitute taught
#

class SubstituteReportingView(AdminSuccessURLMixin, PermissionRequiredMixin, UserFormKwargsMixin,
                              SuccessMessageMixin, CreateView):
    '''
    This view is used to report substitute teaching or other staff substitutions.
    '''
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = SubstituteReportingForm
    permission_required = 'core.report_substitute_teaching'
    success_message = _('Substitution reported successfully.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Substitution'),
            'form_description': _('Use this form to report substitute teaching or other staff substitutions.'),
        })
        return context


############################################################
# View for instructors to change their bio information
#


class StaffMemberBioChangeView(AdminSuccessURLMixin, StaffMemberObjectMixin, PermissionRequiredMixin,
                               SuccessMessageMixin, UpdateView):
    '''
    This view now permits changing the instructor's bio information.
    '''
    model = StaffMember
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = StaffMemberBioChangeForm
    permission_required = 'core.update_instructor_bio'
    success_message = _('Staff member information updated successfully.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Update Contact Information'),
            'form_description': _('Use this form to update your contact information.'),
        })
        return context


############################################################
# View for Instructor/Staff directory
#


class StaffDirectoryView(PermissionRequiredMixin, ListView):
    '''
    This view shows a directory of instructors/staff
    '''
    template_name = 'core/staff_directory.html'
    permission_required = 'core.view_staff_directory'
    queryset = StaffMember.objects.exclude(instructor__status__in=[
        Instructor.InstructorStatus.retired,
        Instructor.InstructorStatus.retiredGuest,
        Instructor.InstructorStatus.hidden,
    ])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        staff = context.get('staffmember_list', StaffMember.objects.none())

        context.update({
            'active_instructors_list': staff.filter(instructor__status='R'),
            'assistant_instructors_list': staff.filter(instructor__status__in=['T', 'A']),
            'guest_instructors_list': staff.filter(instructor__status='G'),
            'other_staff_list': staff.filter(instructor__isnull=True),
        })
        return context


def updateSeriesAttributes(request):
    '''
    This function handles the filtering of available series classes and seriesteachers when a series
    is chosen on the Substitute reporting form.
    '''
    if request.method == 'POST' and request.POST.get('event'):
        event_id = request.POST.get('event') or None
        occurrence_filters = Q(event__id=event_id)
        staff_filters = Q(event__id=event_id)
    else:
        # Only return attributes for valid requests
        return JsonResponse({})

    category_id = request.POST.get('category')
    if (
        category_id and category_id.isdigit() and
        int(category_id) == getConstant('general__eventStaffCategorySubstitute').id
    ):
        staff_filters &= (
            Q(category=getConstant('general__eventStaffCategoryInstructor')) |
            Q(category=getConstant('general__eventStaffCategoryAssistant'))
        )
    elif category_id:
        staff_filters &= Q(category__id=category_id)

    occurrence_ids = request.POST.getlist('occurrences[]')
    if not occurrence_ids:
        # Don't return staff unless occurrences are specified.
        staff_filters = Q(pk__in=[])

    outOccurrences = {}
    for option in EventOccurrence.objects.filter(occurrence_filters):
        outOccurrences[str(option.id)] = option.__str__()

    outStaff = {}
    for option in EventStaffMember.objects.filter(
        staff_filters
    ).prefetch_related('occurrences'):
        if option.occurrences.filter(id__in=occurrence_ids).count() == len(occurrence_ids):
            outStaff[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_occurrences': outOccurrences,
        'id_replacedStaffMember': outStaff,
    })
