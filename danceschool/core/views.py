from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, get_list_or_404
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.views.generic import FormView, CreateView, UpdateView, DetailView, TemplateView, RedirectView, ListView
from django.db.models import Min, Q
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin

from calendar import month_name
from datetime import datetime, timedelta
import json
from urllib.parse import unquote_plus, unquote
from braces.views import UserFormKwargsMixin, PermissionRequiredMixin, LoginRequiredMixin
from cms.constants import RIGHT
from cms.models import Page

from .models import Event, Series, PublicEvent, EventRegistration, StaffMember, Instructor
from .forms import SubstituteReportingForm, InstructorBioChangeForm, EmailContactForm, ClassChoiceForm
from .constants import getConstant, REG_VALIDATION_STR, EMAIL_VALIDATION_STR
from .emails import renderEmail
from .mixins import StaffMemberObjectMixin, FinancialContextMixin, AdminSuccessURLMixin
from .signals import get_customer_data


class RegistrationOfflineView(TemplateView):
    '''
    If registration is offline, just say so.
    '''
    template_name = 'core/registration_offline.html'


class EventRegistrationSelectView(PermissionRequiredMixin, ListView):
    '''
    This view is used to select an event for viewing registration data in the EventRegistrationSummaryView
    '''
    template_name = 'core/events_bymonth_viewregistration_list.html'
    permission_required = 'core.view_registration_summary'

    queryset = Event.objects.filter(startTime__gte=datetime.now() - timedelta(days=90))


class EventRegistrationSummaryView(PermissionRequiredMixin, DetailView):
    '''
    This view is used to access the set of registrations for a given series or event
    '''
    template_name = 'core/view_eventregistrations.html'
    permission_required = 'core.view_registration_summary'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Series.objects.filter(id=self.kwargs.get('series_id')))

    def get_context_data(self,**kwargs):
        ''' Add the list of registrations for the given series '''
        context = {
            'event': self.object,
            'registrations': EventRegistration.objects.filter(
                event=self.object,
                cancelled=False
            ).order_by('registration__customer__user__first_name','registration__customer__user__last_name'),
        }
        context.update(kwargs)
        return super(EventRegistrationSummaryView,self).get_context_data(**context)


class ClassRegistrationReferralView(RedirectView):

    def get(self,request,*args,**kwargs):

        # Always redirect to the classes page
        self.url = reverse('registration')

        # Voucher IDs are used for the referral program.
        # Marketing IDs are used for tracking click-through registrations.
        # They are put directly into session data immediately.
        voucher_id = kwargs.pop('voucher_id',None)
        marketing_id = kwargs.pop('marketing_id',None)

        if marketing_id or voucher_id:
            ''' Put these things into the session data. '''
            regSession = self.request.session.get(REG_VALIDATION_STR, {})
            regSession['voucher_id'] = voucher_id or regSession.get('voucher_id',None)
            regSession['marketing_id'] = marketing_id or regSession.get('marketing_id',None)
            self.request.session[REG_VALIDATION_STR] = regSession

        return super(ClassRegistrationReferralView,self).get(request,*args,**kwargs)


class ClassRegistrationView(FinancialContextMixin, FormView):
    '''
    This is the main view that is called from the class registration page, but
    all of the subsequent views in the process are in classreg.py
    '''
    form_class = ClassChoiceForm
    template_name = 'core/event_registration.html'
    voucher_id = None

    def get(self, request, *args, **kwargs):
        ''' Check that registration is online before proceeding '''
        regonline = getConstant('registration__registrationEnabled')
        if not regonline:
            return HttpResponseRedirect(reverse('registrationOffline'))

        return super(ClassRegistrationView,self).get(request,*args,**kwargs)

    def get_context_data(self,**kwargs):
        ''' Add the event and series listing data '''
        context = self.get_listing()
        context.update(kwargs)

        return super(ClassRegistrationView,self).get_context_data(**context)

    def get_form_kwargs(self, **kwargs):
        ''' Tell the form which fields to render '''
        kwargs = super(ClassRegistrationView, self).get_form_kwargs(**kwargs)
        kwargs['user'] = self.request.user if hasattr(self.request,'user') else None

        listing = self.get_listing()

        kwargs.update({
            'openEvents': listing['openEvents'],
            'closedEvents': listing['closedEvents'],
        })
        return kwargs

    def form_valid(self,form):
        '''
        If the form is valid, pass its contents on to the next view.  In order to permit the registration
        form to be overridden flexibly, but without permitting storage of arbitrary data keys that could
        lead to potential security issues, a form class for this view can optionally specify a list of
        keys that are permitted.  If no such list is specified as instance.permitted_event_keys, then
        the default list are used.
        '''
        regSession = self.request.session.get(REG_VALIDATION_STR, {})

        # The session expires after 15 minutes of inactivity to limit the possible extent of over-registration
        self.request.session.set_expiry(900)

        regInfo = {
            'events': {},
        }

        permitted_keys = getattr(form,'permitted_event_keys',['role',])

        # Put the form data in a format that the next views will understand.
        for key,value in form.cleaned_data.items():
            if 'event' in key and value:
                newkey = int(key.split("_")[-1])
                regInfo['events'][newkey] = {'register': True}
                regInfo['events'][newkey].update({k: v for d in value for k, v in json.loads(d).items() if k in permitted_keys})

        regSession["regInfo"] = regInfo
        regSession["payAtDoor"] = form.cleaned_data.get('payAtDoor', False)
        self.request.session[REG_VALIDATION_STR] = regSession
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('getStudentInfo')

    def get_allEvents(self):
        '''
        Splitting this method out to get the set of events to filter allows
        one to subclass for different subsets of events without copying other
        logic
        '''

        if not hasattr(self,'allEvents'):
            # Get the Event listing here to avoid duplicate queries
            self.allEvents = Event.objects.filter(
                endTime__gte=datetime.now()
            ).filter(
                Q(instance_of=PublicEvent) |
                Q(instance_of=Series)
            ).exclude(
                Q(status=Event.RegStatus.hidden) |
                Q(status=Event.RegStatus.regHidden) |
                Q(status=Event.RegStatus.linkOnly)
            ).order_by('year','month','startTime')
        return self.allEvents

    def get_listing(self):
        '''
        This function gets all of the information that we need to either render or
        validate the form.  It is structured to avoid duplicate DB queries
        '''
        if not hasattr(self,'listing'):
            allEvents = self.get_allEvents()

            openEvents = allEvents.filter(registrationOpen=True)
            closedEvents = allEvents.filter(registrationOpen=False)

            publicEvents = allEvents.instance_of(PublicEvent)
            allSeries = allEvents.instance_of(Series)
            regularSeries = allSeries.filter(series__special=False)

            self.listing = {
                'allEvents': allEvents,
                'openEvents': openEvents,
                'closedEvents': closedEvents,
                'publicEvents': publicEvents,
                'allSeries': allSeries,
                'regularSeries': regularSeries,
                'regOpenEvents': publicEvents.filter(registrationOpen=True),
                'regClosedEvents': publicEvents.filter(registrationOpen=False),
                'regOpenSeries': regularSeries.filter(registrationOpen=True),
                'regClosedSeries': regularSeries.filter(registrationOpen=False),
                'specialSeries': allSeries.filter(series__special=True,registrationOpen=True),
            }
        return self.listing


class SingleClassRegistrationView(ClassRegistrationView):
    '''
    This view is called only via a link, and it allows a person to register for a single
    class without seeing all other classes.
    '''
    template_name = 'core/single_event_registration.html'

    def get_allEvents(self):
        try:
            self.allEvents = Event.objects.filter(uuid=self.kwargs.get('uuid',''))
        except ValueError:
            raise Http404()

        if not self.allEvents:
            raise Http404()

        return self.allEvents


#################################
# Used for various form submission redirects (called by the AdminSuccessURLMixin)


class SubmissionRedirectView(TemplateView):
    template_name = 'cms/forms/submission_redirect.html'

    def get_context_data(self, **kwargs):
        context = super(SubmissionRedirectView,self).get_context_data(**kwargs)

        try:
            redirect_url = unquote(self.request.GET.get('redirect_url',''))
            if not redirect_url:
                redirect_url = Page.objects.get(pk=getConstant('general__defaultAdminSuccessPage')).get_absolute_url(settings.LANGUAGE_CODE)
        except ObjectDoesNotExist:
            redirect_url = '/'

        context.update({
            'redirect_url': redirect_url,
            'seconds': self.request.GET.get('seconds',5),
        })

        return context


#################################
# Email view function and form


class EmailConfirmationView(AdminSuccessURLMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.send_email'
    template_name = 'core/email_confirmation_page.html'
    success_message = _('Email sent successfully.')

    def get(self, request, *args, **kwargs):
        self.form_data = request.session.get(EMAIL_VALIDATION_STR,{}).get('form_data',{})
        if not self.form_data:
            return HttpResponseRedirect(reverse('emailStudents'))
        if request.GET.get('confirmed','').lower() == 'true':
            return self.send_email()
        return super(EmailConfirmationView,self).get(request, *args, **kwargs)

    def send_email(self):
        subject = self.form_data['subject']
        message = self.form_data['message']
        from_name = self.form_data['from_name']
        from_address = self.form_data['from_address']
        cc_myself = self.form_data['cc_myself']
        month = self.form_data['month']
        series = self.form_data['series']
        testemail = self.form_data['testemail']

        events_to_send = []
        if month is not None and month != '':
            events_to_send += Series.objects.filter(month=datetime.strptime(month,'%m-%Y').month, year=datetime.strptime(month,'%m-%Y').year)
        if series not in [None,'',[],['']]:
            events_to_send += [Event.objects.get(id=x) for x in series]

        # We always call one email per series so that the series-level tags
        # can be passed.
        for s in events_to_send:
            emails = []
            cc = []
            if cc_myself:
                cc.append(from_address)

            regs = EventRegistration.objects.filter(event=s)
            for r in regs:
                emails.append(r.customer.email)

            bcc = [getConstant('email__defaultEmailFrom')]

            if testemail:
                message = str(_('Test email from %s to be sent to: ' % from_address)) + '\n\n'
                message += ', '.join(bcc) + ', '.join(emails) + '\n\n'
                message += str(_('Email body:')) + '\n\n' + message
                bcc = []

            renderEmail(subject,message,from_address,from_name,cc=cc,to=[],bcc=bcc,eventregistrations=regs,event=s)

        self.request.session.pop(EMAIL_VALIDATION_STR,None)
        messages.success(self.request, self.success_message)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self,**kwargs):
        context = super(EmailConfirmationView,self).get_context_data(**kwargs)
        context.update(self.form_data)

        month = self.form_data['month']
        series = self.form_data['series']
        from_address = self.form_data['from_address']
        cc_myself = self.form_data['cc_myself']

        events_to_send = []
        if month is not None and month != '':
            events_to_send += Series.objects.filter(month=datetime.strptime(month,'%m-%Y').month, year=datetime.strptime(month,'%m-%Y').year)
        if series not in [None,'',[],['']]:
            events_to_send += [Event.objects.get(id=x) for x in series]

        # We always call one email per series so that the series-level tags
        # can be passed.
        regs = EventRegistration.objects.filter(event__in=events_to_send)

        emails = [r.customer.email for r in regs]
        cc = []
        if cc_myself:
            cc.append(from_address)
        bcc = [getConstant('email__defaultEmailFrom')]

        context.update({
            'events_to_send': events_to_send,
            'emails': emails,
            'cc': cc,
            'bcc': bcc,
        })

        return context


class SendEmailView(PermissionRequiredMixin, UserFormKwargsMixin, FormView):
    form_class = EmailContactForm
    permission_required = 'core.send_email'
    template_name = 'cms/forms/display_form_classbased_admin.html'

    def __init__(self, **kwargs):
        '''
        Get the list of recent months and recent series to pass to the form
        '''
        numMonths = 12
        lastStart = Event.objects.annotate(Min('eventoccurrence__startTime')).order_by('-eventoccurrence__startTime__min').values_list('eventoccurrence__startTime__min',flat=True).first()
        if lastStart:
            month = lastStart.month
            year = lastStart.year
        else:
            month = datetime.now().month
            year = datetime.now().year

        months = [('',_('None'))]
        for i in range(0,numMonths):
            newmonth = (month - i - 1) % 12 + 1
            newyear = year
            if month - i - 1 < 0:
                newyear = year - 1
            newdate = datetime(year=newyear,month=newmonth,day=1)
            newdateStr = newdate.strftime("%m-%Y")
            monthStr = newdate.strftime("%B, %Y")
            months.append((newdateStr,monthStr))

        self.months = months

        cutoff = datetime.now() - timedelta(days=120)

        allEvents = Event.objects.filter(startTime__gte=cutoff).order_by('-startTime')

        self.recentseries = [('','None')] + [(x.id,'%s %s: %s' % (month_name[x.month],x.year,x.name)) for x in allEvents]

        super(SendEmailView,self).__init__(**kwargs)

    def get_form_kwargs(self, **kwargs):
        kwargs = super(SendEmailView, self).get_form_kwargs(**kwargs)
        kwargs.update({"months": self.months, "recentseries": self.recentseries})
        return kwargs

    def get_initial(self):
        '''
        If the user already submitted the form and decided to return from the
        confirmation page, then re-populate the form
        '''
        initial = super(SendEmailView,self).get_initial()

        form_data = self.request.session.get(EMAIL_VALIDATION_STR,{}).get('form_data',{})
        if form_data:
            initial.update(form_data)
        return initial

    def get_context_data(self,**kwargs):
        context = super(SendEmailView,self).get_context_data(**kwargs)

        context.update({
            'form_title': _('Email Students'),
            'form_description': _('Use this form to contact current or recent students.'),
        })
        return context

    def form_valid(self, form):
        ''' Pass form data to the confirmation view '''
        self.request.session[EMAIL_VALIDATION_STR] = {'form_data': form.cleaned_data}
        return HttpResponseRedirect(reverse('emailConfirmation'))


############################################
# Customer and Instructor Stats Views


class AccountProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'core/account_profile.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self,**kwargs):
        context = {}
        user = self.get_object()

        context.update({
            'primary_email': user.emailaddress_set.filter(primary=True).first(),
            'verified_emails': user.emailaddress_set.filter(verified=True),
            'unverified_emails': user.emailaddress_set.filter(verified=False),
        })

        if hasattr(user,'customer'):
            context.update({
                'customer': user.customer,
                'customer_verified': user.emailaddress_set.filter(email=user.customer.email,verified=True).exists(),
            })
            context['customer_eventregs'] = EventRegistration.objects.filter(registration__customer=user.customer)

        context['verified_eventregs'] = EventRegistration.objects.filter(
            registration__customer__email__in=[x.email for x in context['verified_emails']]
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs',[])]
        )
        context['submitted_eventregs'] = EventRegistration.objects.filter(
            registration__submissionUser=self.request.user,registration__payAtDoor=False
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs',[])]
        ).exclude(
            id__in=[x.id for x in context.get('verified_eventregs',[])]
        )

        if hasattr(user,'staffmember'):
            context.update({
                'staffmember': user.staffmember,
                'upcoming_events': Event.objects.filter(endTime__gt=datetime.now(),eventstaffmember__staffMember=user.staffmember).distinct().order_by('-startTime'),
            })

        # Get any extra context data passed by other apps.  These data require unique keys, so when writing
        # a handler for this signal, be sure to provide unique context keys.
        if hasattr(user,'customer'):
            extra_customer_data = get_customer_data.send(
                sender=AccountProfileView,
                customer=user.customer,
            )
            for item in extra_customer_data:
                if len(item) > 1 and isinstance(item[1],dict):
                    # Ensure that 'customer' is not overwritten and add everything else
                    item[1].pop('customer',None)
                    context.update(item[1])

        return super(AccountProfileView,self).get_context_data(**context)


class OtherAccountProfileView(PermissionRequiredMixin, AccountProfileView):
    permission_required = 'core.view_other_user_profiles'

    def get_object(self, queryset=None):
        if 'user_id' in self.kwargs:
            return get_object_or_404(User.objects.filter(id=self.kwargs.get('user_id')))
        else:
            return self.request.user


class InstructorStatsView(StaffMemberObjectMixin, PermissionRequiredMixin, DetailView):
    model = StaffMember
    template_name = 'core/instructor_stats.html'
    permission_required = 'core.view_own_instructor_stats'

    def get_context_data(self,**kwargs):
        instructor = self.object
        context = {}

        context.update({
            'instructor': instructor,
            'prior_series': Event.objects.filter(startTime__lte=datetime.now(),eventstaffmember__staffMember=instructor).order_by('-startTime'),
            'upcoming_series': Event.objects.filter(startTime__gt=datetime.now(),eventstaffmember__staffMember=instructor).order_by('-startTime'),
        })

        if context['prior_series']:
            context.update({'first_series': context['prior_series'].last(),})
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
            return get_object_or_404(
                StaffMember.objects.filter(**{'firstName': unquote_plus(self.kwargs['first_name']).replace('_',' '), 'lastName': unquote_plus(self.kwargs['last_name']).replace('_',' ')}))
        else:
            return None


#####################################
# Individual Class Series/Event Views


class IndividualClassView(FinancialContextMixin, TemplateView):
    template_name = 'core/individual_class.html'

    def get(self,request,*args,**kwargs):
        # These are passed via the URL
        year = self.kwargs.get('year',datetime.now().year)
        month = self.kwargs.get('month',0)
        slug = self.kwargs.get('slug','')

        try:
            month_number = list(month_name).index(month)
        except:
            return Http404(_('Invalid month.'))

        seriesset = get_list_or_404(Series,~Q(status=Event.RegStatus.hidden),~Q(status=Event.RegStatus.linkOnly),year=year,month=month_number,classDescription__slug=slug)

        # This will pass through to the context data by default
        kwargs.update({'seriesset': seriesset})

        # For each Series in the set, add a button to the toolbar to edit the Series details
        if hasattr(request,'user') and request.user.has_perm('core.change_series'):
            for this_series in seriesset:
                this_title = _('Edit Class Details')
                if len(seriesset) > 1:
                    this_title += ' (#%s)' % this_series.id
                request.toolbar.add_button(this_title, reverse('admin:core_series_change', args=([this_series.id,])), side=RIGHT)

        return super(IndividualClassView,self).get(request,*args,**kwargs)


class IndividualEventView(FinancialContextMixin, TemplateView):
    template_name = 'core/individual_event.html'

    def get(self,request,*args,**kwargs):
        # These are passed via the URL
        year = self.kwargs.get('year',datetime.now().year)
        month = self.kwargs.get('month',0)
        slug = self.kwargs.get('slug','')

        try:
            month_number = list(month_name).index(month)
        except:
            return Http404(_('Invalid month.'))

        eventset = get_list_or_404(PublicEvent,~Q(status=Event.RegStatus.hidden),~Q(status=Event.RegStatus.linkOnly),year=year,month=month_number,slug=slug)

        # If an alternative link is given by one or more of these events, then redirect to that.
        overrideLinks = [x.link for x in eventset if x.link]
        if overrideLinks:
            return HttpResponseRedirect(overrideLinks[0])

        # This will pass through to the context data by default
        kwargs.update({'eventset': eventset})

        # For each Event in the set, add a button to the toolbar to edit the Event details
        if hasattr(request,'user') and request.user.has_perm('core.change_publicevent'):
            for this_event in eventset:
                this_title = _('Edit Event Details')
                if len(eventset) > 1:
                    this_title += ' (#%s)' % this_event.id
                request.toolbar.add_button(this_title, reverse('admin:core_publicevent_change', args=([this_event.id,])), side=RIGHT)

        return super(IndividualEventView,self).get(request,*args,**kwargs)


############################################################
# View for instructors to report that they substitute taught
#

class SubstituteReportingView(AdminSuccessURLMixin, PermissionRequiredMixin, UserFormKwargsMixin, SuccessMessageMixin, CreateView):
    '''
    This view is used to report substitute teaching.
    '''
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = SubstituteReportingForm
    permission_required = 'core.report_substitute_teaching'
    success_message = _('Substitute teaching reported successfully.')

    def get_context_data(self,**kwargs):
        context = super(SubstituteReportingView,self).get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Substitute Teaching'),
            'form_description': _('Use this form to report substitute teaching.'),
        })
        return context


############################################################
# View for instructors to change their bio information
#


class InstructorBioChangeView(AdminSuccessURLMixin, StaffMemberObjectMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    '''
    This view now permits changing the instructor's bio information.
    '''
    model = Instructor
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = InstructorBioChangeForm
    permission_required = 'core.update_instructor_bio'
    success_message = _('Instructor information updated successfully.')

    def get_context_data(self,**kwargs):
        context = super(InstructorBioChangeView,self).get_context_data(**kwargs)

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
