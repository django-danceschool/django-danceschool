from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect, Http404, JsonResponse
from django.views.generic import FormView, RedirectView, TemplateView, View
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import logging
from allauth.account.forms import LoginForm, SignupForm
from datetime import timedelta
import json
from braces.views import PermissionRequiredMixin

from .models import (
    Event, Series, PublicEvent, Invoice, CashPaymentRecord, DanceRole,
    Registration, EventRegistration
)
from .forms import ClassChoiceForm, RegistrationContactForm, DoorAmountForm
from .constants import getConstant, REG_VALIDATION_STR
from .signals import (
    post_student_info, apply_discount, apply_price_adjustments
)
from .mixins import (
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
    RegistrationAdjustmentsMixin, ReferralInfoMixin
)


# Define logger for this file
logger = logging.getLogger(__name__)


class RegistrationOfflineView(TemplateView):
    '''
    If registration is offline, just say so.
    '''
    template_name = 'core/registration/registration_offline.html'


class ClassRegistrationReferralView(ReferralInfoMixin, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        ''' Always redirects to the classes page. '''
        return reverse('registration')


class ClassRegistrationView(FinancialContextMixin, EventOrderMixin, SiteHistoryMixin, FormView):
    '''
    This is the main view that is called from the class registration page.
    '''
    form_class = ClassChoiceForm
    template_name = 'core/registration/event_registration.html'
    returnJson = False

    # The temporary registration and the list of event registrations is kept
    # as an attribute of the view so that it may be used in subclassed versions
    # of methods like get_success_url() (see e.g. the door app).
    registration = None
    event_registrations = []

    def dispatch(self, request, *args, **kwargs):
        '''
        Check that registration is online before proceeding.  If this is a POST
        request, determine whether the response should be provided in JSON form.
        '''
        self.returnJson = (request.POST.get('json') in ['true', True])

        regonline = getConstant('registration__registrationEnabled')
        if not regonline:
            returnUrl = reverse('registrationOffline')

            if self.returnJson:
                return JsonResponse({'status': 'success', 'redirect': returnUrl})
            return HttpResponseRedirect(returnUrl)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ''' Add the event and series listing data '''
        context = self.get_listing()
        context.update({
            'showDescriptionRule': getConstant('registration__showDescriptionRule') or 'all',
            'multiRegSeriesRule': getConstant('registration__multiRegSeriesRule') or 'N',
            'multiRegPublicEventRule': getConstant('registration__multiRegPublicEventRule') or 'N',
            'multiRegDropInRule': getConstant('registration__multiRegDropInRule') or 'Y',
        })
        context.update(kwargs)

        # Update the site session data so that registration processes know to send return links to
        # the registration page.  set_return_page() is in SiteHistoryMixin.
        self.set_return_page('registration', _('Registration'))

        return super().get_context_data(**context)

    def get_form_kwargs(self, **kwargs):
        ''' Tell the form which fields to render '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['user'] = self.request.user if hasattr(self.request, 'user') else None

        listing = self.get_listing()

        kwargs.update({
            'openEvents': listing['openEvents'],
            'closedEvents': listing['closedEvents'],
        })
        return kwargs

    def form_invalid(self, form):
        if self.returnJson:
            context = self.get_context_data(form=form)

            return JsonResponse({
                'status': 'failure',
                'errors': form.errors,
            })
        return super().form_invalid(form)

    def form_valid(self, form):
        '''
        If the form is valid, pass its contents on to the next view.  In order to permit the registration
        form to be overridden flexibly, but without permitting storage of arbitrary data keys that could
        lead to potential security issues, a form class for this view can optionally specify a list of
        keys that are permitted.  If no such list is specified as instance.permitted_event_keys, then
        the default list are used.
        '''
        regSession = self.request.session.get(REG_VALIDATION_STR, {})

        # The session expires after a period of inactivity that is specified in preferences.
        expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
        permitted_keys = getattr(form, 'permitted_event_keys', ['role', ])

        # These are prefixes that may be used for events in the form.  Each one
        # corresponds to a polymorphic content type (PublicEvent, Series, etc.)
        event_types = ['event_', 'publicevent_', 'series_']

        try:
            event_listing = {
                int(key.split("_")[-1]): [
                    {k: v for k, v in json.loads(y).items() if k in permitted_keys} for y in value
                ]
                for key, value in form.cleaned_data.items() if any(x in key for x in event_types) and value
            }
            non_event_listing = {
                key: value for key, value in form.cleaned_data.items() if
                not any(x in key for x in event_types)
            }
        except (ValueError, TypeError) as e:
            form.add_error(None, ValidationError(_('Invalid event information passed.'), code='invalid'))
            return self.form_invalid(form)

        associated_events = Event.objects.filter(id__in=[k for k in event_listing.keys()])

        # Include the submission user if the user is authenticated
        if self.request.user.is_authenticated:
            submissionUser = self.request.user
        else:
            submissionUser = None

        reg = Registration(
            submissionUser=submissionUser, dateTime=timezone.now(),
            payAtDoor=non_event_listing.pop('payAtDoor', False), final=False
        )

        # Anything passed by this form that is not an Event field (any extra fields) are
        # passed directly into the Registration's data.
        reg.data = non_event_listing or {}

        if regSession.get('marketing_id'):
            reg.data.update({'marketing_id': regSession.pop('marketing_id', None)})

        # Reset the list of event registrations (if it's not empty) and build it
        # from the form submission data.
        self.event_registrations = []

        for key, value_list in event_listing.items():
            this_event = associated_events.get(id=key)

            for value in value_list:

                # Check if registration is still feasible based on both completed registrations
                # and registrations that are not yet complete
                this_role_id = value.get('role', None) if 'role' in permitted_keys else None
                soldOut = this_event.soldOutForRole(role=this_role_id, includeTemporaryRegs=True)

                if soldOut:
                    if self.request.user.has_perm('core.override_register_soldout'):
                        # This message will be displayed on the Step 2 page by default.
                        messages.warning(self.request, _(
                            'Registration for \'%s\' is sold out. ' % this_event.name +
                            'Based on your user permission level, you may proceed ' +
                            'with registration.  However, if you do not wish to exceed ' +
                            'the listed capacity of the event, please do not proceed.'
                        ))
                    else:
                        # For users without permissions, don't allow registration for sold out things
                        # at all.
                        form.add_error(None, ValidationError(
                            _(
                                'Registration for "%s" is tentatively sold out while ' +
                                'others complete their registration.  Please try ' +
                                'again later.' % this_event.name
                            ), code='invalid')
                        )
                        return self.form_invalid(form)

                dropInList = [int(k.split("_")[-1]) for k, v in value.items() if k.startswith('dropin_') and v is True]

                # If nothing is sold out, then proceed to create Registration and
                # EventRegistration objects for the items selected by this form.  The
                # expiration date is set to be identical to that of the session.

                logger.debug('Creating temporary event registration for: %s' % key)
                if len(dropInList) > 0:
                    this_price = this_event.getBasePrice(dropIns=len(dropInList))
                    tr = EventRegistration(
                        event=this_event, dropIn=True,
                        occurrences=dropInList,
                    )
                else:
                    this_price = this_event.getBasePrice(payAtDoor=reg.payAtDoor)
                    tr = EventRegistration(
                        event=this_event, role_id=this_role_id
                    )
                # If it's possible to store additional data and such data exist, then store them.
                tr.data = {k: v for k, v in value.items() if k in permitted_keys and k != 'role'}
                tr.data['__price'] = this_price
                self.event_registrations.append(tr)

        # If we got this far with no issues, then save
        invoice = reg.link_invoice(expirationDate=expiry)
        reg.save()

        for er in self.event_registrations:
            # Saving the event registration automatically creates an InvoiceItem.
            er.registration = reg
            this_price = er.data.pop('__price')
            er.save(grossTotal=this_price, total=this_price)

        # Put these in a property in case the get_success_url() method needs them.
        self.registration = reg
        self.invoice = invoice

        regSession["registrationId"] = reg.id
        regSession["invoiceId"] = invoice.id.__str__()
        regSession["invoiceExpiry"] = expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session[REG_VALIDATION_STR] = regSession

        if self.returnJson:
            return JsonResponse({
                'status': 'success', 'redirect': self.get_success_url()
            })
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('getStudentInfo')

    def get_allEvents(self):
        '''
        Splitting this method out to get the set of events to filter allows
        one to subclass for different subsets of events without copying other
        logic
        '''

        if not hasattr(self, 'allEvents'):
            timeFilters = {'endTime__gte': timezone.now()}
            if getConstant('registration__displayLimitDays') or 0 > 0:
                timeFilters['startTime__lte'] = timezone.now() + timedelta(
                    days=getConstant('registration__displayLimitDays')
                )

            # Get the Event listing here to avoid duplicate queries
            self.allEvents = Event.objects.filter(
                **timeFilters
            ).filter(
                Q(instance_of=PublicEvent) |
                Q(instance_of=Series)
            ).annotate(
                **self.get_annotations()
            ).exclude(
                Q(status=Event.RegStatus.hidden) |
                Q(status=Event.RegStatus.regHidden) |
                Q(status=Event.RegStatus.linkOnly)
            ).order_by(*self.get_ordering())

        return self.allEvents

    def get_listing(self):
        '''
        This function gets all of the information that we need to either render or
        validate the form.  It is structured to avoid duplicate DB queries
        '''
        if not hasattr(self, 'listing'):
            allEvents = self.get_allEvents()

            openEvents = allEvents.filter(registrationOpen=True)
            closedEvents = allEvents.filter(registrationOpen=False)

            publicEvents = allEvents.instance_of(PublicEvent)
            allSeries = allEvents.instance_of(Series)

            self.listing = {
                'allEvents': allEvents,
                'openEvents': openEvents,
                'closedEvents': closedEvents,
                'publicEvents': publicEvents,
                'allSeries': allSeries,
                'regOpenEvents': publicEvents.filter(registrationOpen=True).filter(
                    Q(publicevent__category__isnull=True) | Q(publicevent__category__separateOnRegistrationPage=False)
                ),
                'regClosedEvents': publicEvents.filter(registrationOpen=False).filter(
                    Q(publicevent__category__isnull=True) | Q(publicevent__category__separateOnRegistrationPage=False)
                ),
                'categorySeparateEvents': publicEvents.filter(
                    publicevent__category__separateOnRegistrationPage=True
                ).order_by('publicevent__category'),
                'regOpenSeries': allSeries.filter(registrationOpen=True).filter(
                    Q(series__category__isnull=True) | Q(series__category__separateOnRegistrationPage=False)
                ),
                'regClosedSeries': allSeries.filter(registrationOpen=False).filter(
                    Q(series__category__isnull=True) | Q(series__category__separateOnRegistrationPage=False)
                ),
                'categorySeparateSeries': allSeries.filter(
                    series__category__separateOnRegistrationPage=True
                ).order_by('series__category'),
            }
        return self.listing


class AjaxClassRegistrationView(PermissionRequiredMixin, RegistrationAdjustmentsMixin, View):
    '''
    This view handles Ajax requests to create or update a Registration.
    Create requests can be done at any time, but update requests only work if
    the Registration to be updated is already in the session data and
    has not expired.  The view returns JSON indicating success or failure as well
    as the URL to which the page it returns to can optionally redirect to.
    '''

    permission_required = 'core.ajax_registration'

    def dispatch(self, request, *args, **kwargs):
        '''
        Check that registration is online before proceeding, and reinitialize
        class attributes in case this instance is preserved through an Ajax
        session.
        '''
        regonline = getConstant('registration__registrationEnabled')
        if not regonline:
            returnUrl = reverse('registrationOffline')
            return JsonResponse({'status': 'success', 'redirect': returnUrl})

        # The registration and the list of event registrations is kept
        # as an attribute of the view so that it may be used in subclassed versions
        # of methods like get_success_url() (see e.g. the door app).
        self.registration = None
        self.event_registrations = []

        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        '''
        Handle creation or update of a temporary registration.
        '''

        regSession = self.request.session.get(REG_VALIDATION_STR, {})
        errors = []

        if request.user.is_authenticated:
            submissionUser = request.user
        else:
            submissionUser = None

        try:
            post_data = json.loads(request.body)
        except json.decoder.JSONDecodeError:
            errors.append({
                'code': 'invalid_json',
                'message': _('Invalid JSON.')
            })
            return JsonResponse({
                'status': 'failure',
                'errors': errors,
            })

        # Used later for updating the registration if needed.
        reg_nullable_keys = [
            'firstName', 'lastName', 'email', 'phone', 'howHeardAboutUs',
        ]
        reg_bool_keys = ['student', 'payAtDoor']

        # Determine whether to create a new registration or update an existing one.
        reg_id = post_data.get('id', None)
        if reg_id:
            try:
                reg = Registration.objects.get(id=reg_id)
            except ObjectDoesNotExist:
                errors.append({
                    'code': 'invalid_id',
                    'message': _('Invalid registration ID passed.')
                })
                return JsonResponse({
                    'status': 'failure',
                    'errors': errors,
                })

            # In order to update an existing registration, the ID passed in POST must
            # match the id contained in the current session data, and the existing
            # registration must not have expired.
            if reg.id != regSession.get('registrationId'):
                errors.append({
                    'code': 'invalid_reg_id',
                    'message': _('Invalid registration ID passed.')
                })

            session_expiry = parse_datetime(
                regSession.get('invoiceExpiry', ''),
            )
            if not session_expiry or session_expiry < timezone.now():
                errors.append({
                    'code': 'expired',
                    'message': _('Your registration session has expired. Please try again.'),
                })
        else:
            # Pass the POST and specify defaults.
            reg_defaults = {key: post_data.get(key, None) for key in reg_nullable_keys}
            reg_defaults.update({key: post_data.get(key, False) for key in reg_bool_keys})

            reg_defaults.update({
                'submissionUser': submissionUser,
                'dateTime': timezone.now(),
                'comments': post_data.get('comments', ''),
                'data': {},
                'final': False,
            })

            if post_data.get('data', False):
                if isinstance(post_data['data'], dict):
                    reg_defaults['data'] = post_data['data']
                else:
                    try:
                        reg_defaults['data'] = json.loads(post_data['data'])
                    except json.decoder.JSONDecodeError:
                        errors.append({
                            'code': 'invalid_json',
                            'message': _('You have passed invalid JSON data for this registation.')
                        })

            # Create a new Registration (not finalized)
            reg = Registration(**reg_defaults)

        # We now have a registration, but before going further, return failure
        # if any errors have arisen.
        if errors:
            return JsonResponse({
                'status': 'failure',
                'errors': errors,
            })

        # If new values for optional registration parameters have been passed,
        # then update them.
        for key in reg_nullable_keys + reg_bool_keys:
            if post_data.get(key, None):
                setattr(reg, key, post_data[key])

        # Update expiration date for this invoice (will also be updated in)
        # session data.
        expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))

        if regSession.get('marketing_id'):
            reg.data.update({'marketing_id': regSession.pop('marketing_id', None)})

        # Should be a list of dictionaries describing event registrations,
        # either existing or to be created.  Some keys are intended to be boolean
        # but are passed as strings, so handle those as well to avoid
        # unexpected behavior.
        event_post = post_data.get('events')
        for e in event_post:
            for k in ['dropIn', 'requireFull']:
                if isinstance(e.get(k, None), str):
                    e[k] = ('true' in e[k].lower())

        eventregs = EventRegistration.objects.filter(
            id__in=[x['eventreg'] for x in event_post if x.get('eventreg', None)]
        )
        events = Event.objects.filter(
            id__in=[x['event'] for x in event_post if x.get('event', None)]
        )

        grossPrice = 0
        existing_eventreg_ids = list(reg.eventregistration_set.values_list('id', flat=True))
        unmatched_eventreg_ids = existing_eventreg_ids.copy()

        for e in event_post:
            try:
                this_event = events.get(id=e['event'])
            except ObjectDoesNotExist:
                errors.append({
                    'code': 'invalid_event_id',
                    'message': _('Invalid event ID passed.')
                })
                continue

            # The existing event registration should be found if its ID is passed.
            # Otherwise, update an existing one.
            created_eventreg = False

            if e.get('eventreg', None):
                try:
                    this_eventreg = eventregs.get(id=e['eventreg'])
                    logger.debug('Found existing temporary event registration: {}'.format(this_eventreg.id))
                    unmatched_eventreg_ids.remove(this_eventreg.id)
                except [ObjectDoesNotExist, ValueError]:
                    errors.append({
                        'code': 'invalid_eventreg_id',
                        'message': _('Invalid event registration ID passed.')
                    })
                    continue
            else:
                # Before continuing, enforce rules on duplicate registrations, etc.
                dropIn = e.get('dropIn', False)
                # Check the other eventregistrations in POST data to ensure
                # that this is the only one for this event.
                same_event = [x for x in event_post if x.get('event', None) == this_event.id]

                if len(same_event) > 1 and ((
                    this_event.polymorphic_ctype.model == 'series' and not dropIn and (
                        (getConstant('registration__multiRegSeriesRule') == 'N') or
                        (getConstant('registration__multiRegSeriesRule') == 'D' and not reg.payAtDoor)
                    )
                ) or (
                    this_event.polymorphic_ctype.model == 'publicevent' and not dropIn and (
                        (getConstant('registration__multiRegPublicEventRule') == 'N') or
                        (getConstant('registration__multiRegPublicEventRule') == 'D' and not reg.payAtDoor)
                    )
                ) or (
                    dropIn and (
                        (getConstant('registration__multiRegDropInRule') == 'N') or
                        (getConstant('registration__multiRegDropInRule') == 'D' and not reg.payAtDoor)
                    )
                )):
                    errors.append({
                        'code': 'duplicate_event',
                        'message': _(
                            'You cannot register more than once for event: {event_name}. '.format(
                                event_name=this_event.name
                            ) +
                            'Please remove the existing item from your cart and try again.'
                        )
                    })
                    continue
                elif (
                    len(same_event) > 1 and
                    len([x for x in same_event if x.get('dropIn', False) != dropIn]) > 0
                ):
                    errors.append({
                        'code': 'dropin_with_full',
                        'message': _(
                            'You cannot register as both a drop-in and as a ' +
                            'full registrant for event: {event_name}. '.format(
                                event_name=this_event.name
                            ) +
                            'Please remove the existing item from your cart and try again.'
                        )
                    })
                    continue

                logger.debug('Creating event registration for event: {}'.format(this_event.id))
                this_eventreg = EventRegistration(event=this_event)
                created_eventreg = True

            if not (
                this_event.registrationOpen or
                request.user.has_perm('core.override_register_closed')
            ):
                errors.append({
                    'code': 'registration_closed',
                    'message': _('Registration is closed for event {}.'.format(this_event.id))
                })

            if (
                created_eventreg and this_event.soldOut and not
                request.user.has_perm('core.override_register_soldout')
            ):
                errors.append({
                    'code': 'sold_out',
                    'message': _('Event {} is sold out.'.format(this_event.id))
                })

            this_role = e.get('roleId', None)
            if (
                created_eventreg and
                this_event.soldOutForRole(this_role, includeTemporaryRegs=True) and not
                request.user.has_perm('core.override_register_soldout')
            ):
                errors.append({
                    'code': 'sold_out_role',
                    'message': _('Event {} is sold out for role {}.'.format(this_event.id, this_role))
                })

            # Check that the user can register for drop-ins, and that drop-ins are
            # either enabled, or they have override permissions.
            dropIn = e.get('dropIn', False)
            if not isinstance(this_event, Series) and dropIn:
                errors.append({
                    'code': 'invalid_dropin',
                    'message': _('Cannot register as a drop-in for events that are not class series.')
                })
            elif (dropIn and (
                    not request.user.has_perm('core.register_dropins') or
                    (
                        not this_event.allowDropins and not
                        request.user.has_perm('override_register_dropins')
                    )
            )):
                errors.append({
                    'code': 'no_dropin_permission',
                    'message': _('You are not permitted to register for drop-in classes.')
                })

            # No need to continue if we've already identified errors
            if errors:
                continue

            # Update the contents of the event registration.
            if dropIn:
                this_eventreg.dropIn = True
                this_eventreg.data['__price'] = this_event.getBasePrice(dropIns=1)
                this_eventreg.occurrences = None
            else:
                this_eventreg.dropIn = False
                this_eventreg.data['__price'] = this_event.getBasePrice(payAtDoor=reg.payAtDoor)
                this_eventreg.role = DanceRole.objects.filter(id=this_role).first()

            # Sometimes requireFull is passed as a string and sometimes as boolean,
            # this just ensures that it works correctly either way.  Also,
            # record payment methods if they were passed.
            this_eventreg.data['requireFull'] = (str(e.get('requireFull', 'True')).lower() == 'true')
            if e.get('paymentMethod', None):
                this_eventreg.data['paymentMethod'] = e['paymentMethod']
                this_eventreg.data['autoSubmit'] = e.get('autoSubmit', None)
            if e.get('doorChoiceId', None):
                this_eventreg.data['doorChoiceId'] = e['doorChoiceId']

            if e.get('data', False):
                if isinstance(e['data'], dict):
                    e['data'].pop('__price', None)
                    this_eventreg.data.update(e['data'])
                else:
                    try:
                        new_data = json.loads(e['data'])
                        new_data.pop('__price', None)
                        this_eventreg.data.update(new_data)
                    except json.decoder.JSONDecodeError:
                        errors.append({
                            'code': 'invalid_json',
                            'message': _('You have passed invalid JSON data for this registation.')
                        })

            self.event_registrations.append(this_eventreg)
            grossPrice += this_eventreg.data['__price']

        # We now have a registration, but before going further, return failure
        # if any errors have arisen.
        if errors:
            return JsonResponse({
                'status': 'failure',
                'errors': errors,
            })

        # If we got this far with no issues, then save everything.  Delete any
        # existing associated EventRegistrations that were not passed
        # in via POST.
        invoice = reg.link_invoice(expirationDate=expiry)
        reg.save()
        reg.eventregistration_set.filter(id__in=unmatched_eventreg_ids).delete()

        for er in self.event_registrations:
            # Saving the event registration automatically creates an InvoiceItem.
            # We pop the price information out of data before saving and pass it
            # to the save method so that the linked invoice item has the right
            # price information.
            er.registration = reg
            this_price = er.data.pop('__price', None)
            er.save(grossTotal=this_price, total=this_price)

        # Put this in a property in case the get_success_url() method needs it.
        self.registration = reg
        self.invoice = invoice

        reg_response = {
            'id': reg.id,
            'invoiceId': invoice.id.__str__(),
            'payAtDoor': reg.payAtDoor,
            'subtotal': grossPrice,
            'total': grossPrice,
            'itemCount': len(self.event_registrations),
            'events': [
                {
                    'event': x.event.id, 'name': x.event.name,
                    'eventreg': x.id,
                    'dropIn': x.dropIn, 'roleId': getattr(x.role, 'id', None),
                    'roleName': getattr(x.role, 'name', None),
                    'price': x.data.get('__price', None),
                    'requireFull': x.data.get('requireFull', True),
                    'paymentMethod': x.data.get('paymentMethod', None),
                    'autoSubmit': x.data.get('autoSubmit', None),
                    'doorChoiceId': x.data.get('doorChoiceId', None),
                }
                for x in self.event_registrations
            ],
        }

        # Pass back student status.
        if reg.student:
            reg_response.update({'student': reg.student})

        # Add any additional items (such as merchandise from additional apps)
        # that could modify the cart totals.
        additional_items = self.getAdditionalItems(
            post_data.get('items', []), post_data.get('orders', {})
        )
        if additional_items:
            reg_response.update({
                'total': grossPrice + additional_items.get('subtotal', 0),
                'subtotal': grossPrice + additional_items.get('subtotal', 0),
                'itemCount': (
                    reg_response.get('itemCount', 0) +
                    additional_items.get('itemCount', 0)
                ),
                'items': additional_items.get('items', {})
            })

        discount_codes, total_discount_amount, discounted_total = self.getDiscounts(
            reg, grossPrice
        )
        if total_discount_amount > 0:

            reg_response.update({
                'discounts': [
                    {
                        'name': x.code.name,
                        'id': x.code.id,
                        'net_price': x.net_price,
                        'discount_amount': x.discount_amount,
                    }
                    for x in discount_codes
                ],
                'discount_amount': total_discount_amount,
                'total': discounted_total,
            })

        addons = self.getAddons(reg)
        if addons:
            reg_response.update({
                'addonItems': addons,
            })

        voucherId = post_data.get('voucherId', None)
        if voucherId:
            reg_response.update(
                self.getVoucher(
                    voucherId, reg, discounted_total,
                    post_data.get('firstName', None),
                    post_data.get('lastName', None),
                    post_data.get('email', None),
                )
            )

        response_dict = {
            'status': 'success',
            'reg': reg_response,
        }

        # Pass the redirect URL and send the voucher ID to session data if
        # this is being finalized.
        if post_data.get('finalize') is True:

            data_changed_flag = False

            # Will only be set to False if every event has a set value of
            # requireFull, and if all of them are False.
            requireFullRegistration = (
                True in
                [x.get('requireFull', True) for x in event_post]
            )

            # If all events are to be registered using the same payment method
            # and auto-submit is always True, then pass this info to the registration.
            methods = [x.get('paymentMethod', None) for x in event_post]
            if len(set(methods)) == 1 and methods[0]:
                data_changed_flag = True
                reg.data['paymentMethod'] = methods[0]

                if False not in [
                    x.get('autoSubmit', False) for x in event_post
                ]:
                    reg.data['autoSubmit'] = True

            if not requireFullRegistration:

                # Update the registration to put the voucher code in data if
                # needed so that the Temporary Voucher Use is created before
                # we proceed to the summary page.
                if response_dict['reg'].get('voucherId', None):
                    data_changed_flag = True
                    reg.data['gift'] = response_dict['reg']['voucherId']

                if data_changed_flag:
                    reg.save()

                post_student_info.send(
                    sender=AjaxClassRegistrationView,
                    registration=self.registration,
                )
                response_dict['redirect'] = reverse('showRegSummary')
            else:
                if data_changed_flag:
                    reg.save()
                response_dict['redirect'] = reverse('getStudentInfo')

            regSession["voucher_id"] = reg_response.get('voucherId', None)

        regSession["registrationId"] = reg.id
        regSession["invoiceId"] = invoice.id.__str__()
        regSession["invoiceExpiry"] = expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session[REG_VALIDATION_STR] = regSession

        return JsonResponse(response_dict)


class SingleClassRegistrationReferralView(ReferralInfoMixin, RedirectView):
    '''
    Single class registration can accept marketing IDs and voucher codes.
    '''

    def get_redirect_url(self, *args, **kwargs):
        return reverse('singleClassRegistration', kwargs=kwargs)


class SingleClassRegistrationView(ReferralInfoMixin, ClassRegistrationView):
    '''
    This view is called only via a link, and it allows a person to register for a single
    class without seeing all other classes.
    '''
    template_name = 'core/registration/single_event_registration.html'

    def get_allEvents(self):
        try:
            self.allEvents = Event.objects.filter(
                uuid=self.kwargs.get('uuid', '')
            ).exclude(
                status=Event.RegStatus.hidden
            )
        except ValueError:
            raise Http404()

        if not self.allEvents:
            raise Http404()

        return self.allEvents


class RegistrationSummaryView(
    FinancialContextMixin, RegistrationAdjustmentsMixin, SiteHistoryMixin, TemplateView
):
    template_name = 'core/registration_summary.html'

    def dispatch(self, request, *args, **kwargs):
        ''' Always check that the temporary registration has not expired '''
        regSession = self.request.session.get(REG_VALIDATION_STR, {})

        if not regSession:
            return HttpResponseRedirect(reverse('registration'))

        try:
            invoice = Invoice.objects.get(id=self.request.session[REG_VALIDATION_STR].get('invoiceId'))
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to summary view.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoiceExpiry', ''),
        )
        if not expiry or expiry < timezone.now():
            messages.info(request, _('Your registration session has expired. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        tr_id = self.request.session[REG_VALIDATION_STR].get('registrationId')

        if tr_id:
            reg = Registration.objects.get(
                id=tr_id
            )
        else:
            reg = None
        if reg and reg.invoice != invoice:
            messages.error(request, _('Invoice and registration do not match.'))
            return HttpResponseRedirect(reverse('registration'))

        # If OK, pass the registration and proceed
        kwargs.update({
            'reg': reg,
            'invoice': invoice,
        })
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        reg = kwargs.get('reg')
        invoice = kwargs.get('invoice')

        discount_codes = None
        total_discount_amount = 0
        discounted_total = invoice.total
        addons = []

        if reg:
            initial_reg_price = reg.invoiceDetails['reg_grossTotal']
            discount_codes, total_discount_amount, discounted_total = self.getDiscounts(
                reg, initial_reg_price
            )
            addons = self.getAddons(reg)

            for discount in discount_codes:
                apply_discount.send(
                    sender=RegistrationSummaryView,
                    discount=discount.code,
                    discount_amount=discount.discount_amount,
                    registration=reg,
                )

        # The return value to this signal should contain any adjustments that
        # need to be made to the price (e.g. from vouchers if the voucher app
        # is installed)
        adjustment_responses = apply_price_adjustments.send(
            sender=RegistrationSummaryView,
            invoice=invoice,
            registration=reg,
            initial_price=discounted_total
        )

        adjustment_list = []
        adjustment_amount = 0

        for response in adjustment_responses:
            adjustment_list += response[1][0]
            adjustment_amount += response[1][1]

        # The updateTotals method allocates the total adjustment across the
        # invoice items.
        invoice.updateTotals(allocateAmounts={
            'total': -1*(adjustment_amount + total_discount_amount)
        })

        # Update the session key to keep track of this registration
        regSession = request.session[REG_VALIDATION_STR]
        regSession["temp_invoice_id"] = invoice.id.__str__()
        if reg:
            regSession["temp_reg_id"] = reg.id
            regSession['addons'] = addons
            regSession['total_discount_amount'] = total_discount_amount
            if discount_codes:
                regSession['discount_codes'] = [
                    (x.code.name, x.code.pk, x.discount_amount) for x in discount_codes
                ]

        regSession['voucher_names'] = adjustment_list
        regSession['total_voucher_amount'] = adjustment_amount
        request.session[REG_VALIDATION_STR] = regSession

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ''' Pass the initial kwargs, then update with the needed registration info. '''
        context_data = super().get_context_data(**kwargs)

        regSession = self.request.session[REG_VALIDATION_STR]
        invoice_id = regSession["temp_invoice_id"]
        invoice = Invoice.objects.get(id=invoice_id)

        reg_id = regSession.get("temp_reg_id",None)
        if reg_id:
            reg = Registration.objects.get(id=reg_id)
        else:
            reg = None

        discount_codes = regSession.get('discount_codes', None)
        discount_amount = regSession.get('total_discount_amount', 0)
        voucher_names = regSession.get('voucher_names', [])
        total_voucher_amount = regSession.get('total_voucher_amount', 0)
        addons = regSession.get('addons', [])

        isFree = (invoice.total == 0)
        isComplete = (isFree or regSession.get('direct_payment', False) is True)

        if isComplete:
            # Include the submission user if the user is authenticated
            if self.request.user.is_authenticated:
                submissionUser = self.request.user
            else:
                submissionUser = None

            if isFree:
                invoice.processPayment(
                    amount=0, fees=0, submissionUser=submissionUser,
                    forceFinalize=True
                )
            else:
                amountPaid = invoice.total
                paymentMethod = regSession.get('direct_payment_method', 'Cash')

                this_cash_payment = CashPaymentRecord.objects.create(
                    invoice=invoice, amount=amountPaid,
                    status=CashPaymentRecord.PaymentStatus.collected,
                    paymentMethod=paymentMethod,
                    payerEmail=invoice.email,
                    submissionUser=submissionUser,
                    collectedByUser=submissionUser,
                )
                invoice.processPayment(
                    amount=amountPaid, fees=0, paidOnline=False,
                    methodName=paymentMethod, submissionUser=submissionUser,
                    collectedByUser=submissionUser,
                    methodTxn='CASHPAYMENT_%s' % this_cash_payment.recordId,
                    forceFinalize=True,
                )
            if reg:
                # Ensures that the registration has a status that reflects the
                # payment that has been processed
                reg.refresh_from_db()

        context_data.update({
            'returnPage': self.get_return_page().get(
                'url', reverse('registration')
            ),
            'registration': reg,
            'invoice': invoice,
            "addonItems": addons,
            "discount_codes": discount_codes,
            "discount_code_amount": discount_amount,
            "voucher_names": voucher_names,
            "total_voucher_amount": total_voucher_amount,
            "total_discount_amount": discount_amount + total_voucher_amount,
            "currencyCode": getConstant('general__currencyCode'),
            'payAtDoor': getattr(reg, 'payAtDoor', False),
            'is_complete': isComplete,
            'is_free': isFree,
        })

        return context_data


class StudentInfoView(RegistrationAdjustmentsMixin, FormView):
    '''
    This page displays a preliminary total of what is being signed up for, and it also
    collects customer information, either by having the user sign in in an Ajax view, or by
    manually entering the information.  When the form is submitted, the view just passes
    everything into the session data and continues on to the next step.  To add additional
    fields to this form, or to modify existing fields, just override the form class to
    a form that adds/modifies whatever fields you would like.
    '''
    form_class = RegistrationContactForm
    template_name = 'core/student_info_form.html'

    def dispatch(self, request, *args, **kwargs):
        '''
        Require session data to be set to proceed, otherwise go back to step 1.
        Because they have the same expiration date, this also implies that the
        Registration object is not yet expired.
        '''
        if REG_VALIDATION_STR not in request.session:
            return HttpResponseRedirect(reverse('registration'))

        try:
            self.invoice = Invoice.objects.get(
                id=self.request.session[REG_VALIDATION_STR].get('invoiceId')
            )
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to sign-up form.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoiceExpiry', ''),
        )
        if not expiry or expiry < timezone.now():
            messages.info(request, _('Your registration session has expired. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        tr_id = self.request.session[REG_VALIDATION_STR].get('registrationId')

        if tr_id:
            self.registration = Registration.objects.get(
                id=tr_id
            )
        else:
            self.registration = None
        if self.registration and self.registration.invoice != self.invoice:
            messages.error(request, _('Invoice and registration do not match.'))
            return HttpResponseRedirect(reverse('registration'))

        # Ensure that session data is always updated when this view is called
        # so that passed voucher_ids are cleared.
        request.session.modified = True

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        reg = self.registration

        context_data.update({
            'invoice': self.invoice,
            'currencySymbol': getConstant('general__currencySymbol'),
        })

        if reg:
            initial_reg_price = reg.invoiceDetails['reg_grossTotal']

            discount_codes, total_discount_amount, discounted_total = self.getDiscounts(
                reg, initial_reg_price
            )
            addons = self.getAddons(reg)

            context_data.update({
                'reg': reg,
                'payAtDoor': reg.payAtDoor,
                'currencySymbol': getConstant('general__currencySymbol'),
                'addonItems': addons,
                'discount_codes': discount_codes,
                'discount_code_amount': total_discount_amount,
            })

            # Get a voucher ID to check from the current contents of the form
            voucherId = getattr(context_data['form'].fields.get('gift'), 'initial', None)

            if voucherId:
                context_data.update(
                    self.getVoucher(voucherId, reg, discounted_total)
                )

        if (
            getattr(reg,'payAtDoor', None) or
            self.request.user.is_authenticated or not
            getConstant('registration__allowAjaxSignin')
        ):
            context_data['show_ajax_form'] = False
        else:
            # Add a login form and a signup form
            context_data.update({
                'show_ajax_form': True,
                'login_form': LoginForm(),
                'signup_form': SignupForm(),
            })

        return context_data

    def get_form_kwargs(self, **kwargs):
        ''' Pass along the request data to the form '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['request'] = self.request
        kwargs['registration'] = self.registration
        kwargs['invoice'] = self.invoice
        return kwargs

    def get_success_url(self):
        return reverse('showRegSummary')

    def form_valid(self, form):
        '''
        Even if this form is valid, the handlers for this form may have added messages
        to the request.  In that case, then the page should be handled as if the form
        were invalid.  Otherwise, update the session data with the form data and then
        move to the next view
        '''

        # The session expires after a period of inactivity that is specified in preferences.
        expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
        self.request.session[REG_VALIDATION_STR]["invoiceExpiry"] = \
            expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session.modified = True

        reg = self.registration
        if reg:

            # Update the expiration date for this registration, and pass in the data from
            # this form.
            reg.firstName = form.cleaned_data.pop('firstName')
            reg.lastName = form.cleaned_data.pop('lastName')
            reg.email = form.cleaned_data.pop('email')
            reg.phone = form.cleaned_data.pop('phone', None)
            reg.student = form.cleaned_data.pop('student', False)
            reg.comments = form.cleaned_data.pop('comments', None)
            reg.howHeardAboutUs = form.cleaned_data.pop('howHeardAboutUs', None)

            # Anything else in the form goes to the Registration data.
            reg.data.update(form.cleaned_data)
            invoice = reg.link_invoice(expirationDate=expiry)
            reg.save()
        else:
            invoice = self.invoice

            if invoice.status == Invoice.PaymentStatus.preliminary:
                invoice.expirationDate = expiry

            invoice.firstName = form.cleaned_data.pop('firstName')
            invoice.lastName = form.cleaned_data.pop('lastName')
            invoice.email = form.cleaned_data.pop('email')
            invoice.data.update(form.cleaned_data)
            invoice.save()

        # This signal allows vouchers to be applied temporarily, and it can
        # be used for other tasks
        post_student_info.send(sender=StudentInfoView, registration=reg)
        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST
