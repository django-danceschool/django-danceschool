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
    Event, Series, PublicEvent, Invoice, InvoiceItem,
    CashPaymentRecord, DanceRole, Registration, EventRegistration
)
from .forms import ClassChoiceForm, RegistrationContactForm
from .constants import getConstant, REG_VALIDATION_STR
from .signals import (
    post_student_info, apply_discount, apply_price_adjustments,
    get_invoice_related, get_invoice_item_related
)
from .mixins import (
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
    RegistrationAdjustmentsMixin, ReferralInfoMixin
)
from .utils.timezone import ensure_localtime


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
    includeCounts = True
    voucherField = False
    pluralName = True

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

        # Automatically pass along some of the optional form kwargs
        for key in ['includeCounts', 'pluralName', 'voucherField']:
            if isinstance(getattr(self, key, None), bool):
                kwargs[key] = getattr(self, key, None)

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
            event_listing = {}
            for key, value in form.cleaned_data.items():
                if any(x in key for x in event_types) and value:
                    this_event = {}
                    for y in value:
                        for k,v in json.loads(y).items():
                            if k in permitted_keys and k not in this_event:
                                this_event[k] = v
                    event_listing[int(key.split("_")[-1])] = this_event
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

        for key, value in event_listing.items():
            this_event = associated_events.get(id=key)

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
                )
            else:
                this_price = this_event.getBasePrice(payAtDoor=reg.payAtDoor)
                tr = EventRegistration(
                    event=this_event, role_id=this_role_id
                )
            # If it's possible to store additional data and such data exist, then store them.
            tr.data = {k: v for k, v in value.items() if k in permitted_keys and k != 'role'}
            if dropInList:
                tr.data['__dropInOccurrences'] = dropInList

            checkin_rule = getConstant('registration__doorCheckInRule')
            if reg.payAtDoor and checkin_rule == 'E':
                # Check into the full event
                tr.data['__checkInEvent'] = True
            elif reg.payAtDoor and checkin_rule == 'O' and dropInList:
                # Check into the first upcoming drop-in occurrence
                best_occ = tr.event.eventoccurrence_set.filter(
                    id__in=dropInList,
                    startTime__gte=ensure_localtime(timezone.now()) - timedelta(minutes=45)
                ).first()
                tr.data['__checkInOccurrence'] = getattr(best_occ, 'id', None)
            elif reg.payAtDoor and checkin_rule == 'O':
                # Check into the next upcoming occurrence (45 min. grace period)
                tr.data['__checkInOccurrence'] = getattr(
                    tr.event.getNextOccurrence(
                        ensure_localtime(timezone.now()) - timedelta(minutes=45)
                    ),
                    'id',
                    None
                )

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

        regSession["invoiceId"] = invoice.id.__str__()
        regSession["invoiceExpiry"] = expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        regSession["payAtDoor"] = reg.payAtDoor
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

        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        '''
        Handle creation or update of an invoice.
        '''

        regSession = request.session.get(REG_VALIDATION_STR, {})

        # This dictionary holds the information that will be serialized to JSON
        # and sent back to the requesting user.  It is populated gradually as
        # the view's logic proceeds.  Some special keys are also populated and
        # then popped off before the response is sent, such as the __related__
        # keys corresponding to other models that are one-to-one linked to an
        # Invoice or InvoiceItem, which need to be carried along and saved only
        # after the Invoice/InvoiceItem is saved.
        response = {}

        # This is the list of errors that are potentially populated by the
        # various checks in this view or by its signal handlers.  When a
        # particular error makes it impossible to proceed with the view's logic,
        # an error response will be sent if this list is non-empty.
        errors = []

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

        # Used later for updating the invoice and registration if needed.
        invoice_nullable_keys = ['firstName', 'lastName', 'email']

        # Determine whether to create a new Invoice or update an existing one.
        # Regardless of which is the case, the Invoice ID will be added to the
        # response data after the Invoice has been saved and before returning
        # if the update process is successful.
        invoice_id = post_data.get('id', None)
        if invoice_id:
            try:
                invoice = Invoice.objects.get(id=invoice_id)
            except ObjectDoesNotExist:
                errors.append({
                    'code': 'invalid_id',
                    'message': _('Invalid invoice ID passed.'),
                })
                return JsonResponse({
                    'status': 'failure',
                    'errors': errors,
                })

            # In order to update an existing invoice, the ID passed in POST must
            # match the id contained in the current session data, and the existing
            # invoice must not have expired or be non-editable.
            if str(invoice.id) != regSession.get('invoiceId'):
                errors.append({
                    'code': 'invalid_invoice_id',
                    'message': _('Invalid invoice ID passed.')
                })

            session_expiry = parse_datetime(
                regSession.get('invoiceExpiry', ''),
            )
            if not session_expiry or session_expiry < timezone.now():
                errors.append({
                    'code': 'expired',
                    'message': _('Your registration session has expired. Please try again.'),
                })

            if not invoice.itemsEditable:
                errors.append({
                    'code': 'not_editable',
                    'message': _('This invoice can no longer be modified.'),
                })
        else:
            invoice_defaults = {key: post_data.get(key, None) for key in invoice_nullable_keys}
            invoice_defaults.update({
                'submissionUser': request.user if request.user.is_authenticated else None,
                'data': {},
                'status': Invoice.PaymentStatus.preliminary,
                'buyerPaysSalesTax': getConstant('registration__buyerPaysSalesTax'),
            })
            invoice = Invoice(**invoice_defaults)

            if post_data.get('data', False):
                if isinstance(post_data['data'], dict):
                    invoice_defaults['data'] = post_data['data']
                else:
                    try:
                        invoice_defaults['data'] = json.loads(post_data['data'])
                    except json.decoder.JSONDecodeError:
                        errors.append({
                            'code': 'invalid_json',
                            'message': _('You have passed invalid JSON data for this registation.')
                        })

        # We now have an invoice, but before going further, return failure
        # if any errors have arisen.
        if errors:
            return JsonResponse({
                'status': 'failure',
                'errors': errors,
            })

        # Update expiration date for this invoice (will also be updated in
        # session data).  Also reset all totals to 0 (will be populated by signal handlers.)
        invoice.expirationDate = (
            timezone.now() +
            timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
        )
        for attr in ['grossTotal', 'total', 'taxes', 'adjustments', 'fees']:
            setattr(invoice, attr, 0)

        if regSession.get('marketing_id'):
            self.invoice.data.update({'marketing_id': regSession.pop('marketing_id', None)})

        # Some keys are intended to be boolean
        # but are passed as strings, so handle those as well to avoid
        # unexpected behavior.
        for x in post_data.get('items', []):
            for k in ['dropIn', 'requireFull', 'autoSubmit', 'autoFulfill',]:
                if isinstance(x.get(k, None), str):
                    x[k] = ('true' in x[k].lower())

        # Should be a list of dictionaries describing event registrations,
        # either existing or to be created.
        item_post = post_data.get('items')
        existing_items = InvoiceItem.objects.filter(
            id__in=[x['id'] for x in item_post if x.get('id', None)]
        )

        # TODO: This should be determined internally in the view so it cannot
        # be modified by the user.
        response.update({
            'payAtDoor': post_data.get('payAtDoor', False),
        })

        # Pass the response dictionary over to handle registrations.  The method
        # passes the dictionary back to us with any necessary updates.  Keys
        # beginning with "__relateditem" can be used to hold related items such
        # as associated models.  Keys beginning with "__related" will be removed
        # from the response dictionary before it is converted to JSON and returned
        # to the user.  Note also that although the dictionaries and objects
        # passed to linkRegistration and the signal handlers can be modified
        # within the handler, this is an anti-pattern.  It is preferred to return
        # a response dictionary in a response of the form
        # {'status': 'success', 'response': 'response'}, which is used to update
        # the overall response in AjaxClassRegistrationView.
        signal_response = self.linkRegistration(invoice, post_data)
        if signal_response.get('status') != 'success':
            errors += signal_response.get('errors', [])
        else:
            response.update(signal_response.get('response',{}))

        # Fill the set of related items (such as the set of events). It is
        # strongly recommended that handlers of this signal use the dispatch_uid
        # parameter to ensure that they are not called more than once.
        signal_responses = get_invoice_related.send(
            sender=AjaxClassRegistrationView,
            invoice=invoice, post_data=post_data, prior_response=response,
            request=request
        )

        for s in signal_responses:
            if isinstance(s[1], dict) and s[1].get('status') != 'success':
                errors += s[1].get('errors', [])
            elif isinstance(s[1], dict):
                response.update(s[1].get('response', {}))

        # We now have an invoice and any related items (such as a Registration
        # or MerchOrder) that need to be linked to that Registration.  Loop
        # through the set of passed items and either create
        # InvoiceItems/EventRegistrations for them, or update existing ones.
        existing_item_ids = list(invoice.invoiceitem_set.values_list('id', flat=True))
        unmatched_item_ids = existing_item_ids.copy()

        # This list will be populated with the response dictionaries to be sent
        # back to the view related to each individual item.  This method
        # populates a few key fields, but additional fields may be specified
        # by signal handlers that are called to process each item in the cart.
        items_response = []

        for i in item_post:

            if i.get('id', None):
                try:
                    this_item = existing_items.get(id=i['id'])
                    logger.debug('Found existing invoice item: {}'.format(this_item.id))
                    unmatched_item_ids.remove(this_item.id)
                except (ObjectDoesNotExist, ValueError):
                    errors.append({
                        'code': 'invalid_item_id',
                        'message': _('Invalid invoice item ID passed.')
                    })
                    break
            else:
                this_item = InvoiceItem(invoice=invoice)

            # The response data will be updated by the signal handlers below,
            # and it will also need to be updated after the item is saved.
            this_item_response = {
                'requireFull': i.get('requireFull', None),
                'paymentMethod': i.get('paymentMethod', None),
                'autoSubmit': i.get('autoSubmit', None),
                'choiceId': i.get('choiceId', None),
                '__item': this_item,
            }

            # Reset all item totals to 0 (will be populated by the signal handler)
            for attr in ['grossTotal', 'total', 'taxes', 'adjustments', 'fees']:
                setattr(this_item, attr, 0)

            # Add key parameters from the item JSON to the Invoice item data.
            this_item.data.update({
                'choiceId': i.get('choiceId', None),
                'requireFull': i.get('requireFull', True),
            })
            if i.get('paymentMethod', None):
                this_item.data.update({
                    'paymentMethod': i.get('paymentMethod'),
                    'autoSubmit': i.get('autoSubmit', None),
                })

            if i.get('type') == 'eventRegistration':
                signal_response = self.linkEventRegistration(
                    item=this_item, item_data=i, post_data=post_data,
                    prior_response=response, request=request
                )
                if signal_response.get('status') != 'success':
                    errors += signal_response.get('errors', [])
                this_item_response.update(signal_response.get('response',{}))

            signal_responses = get_invoice_item_related.send(
                sender=AjaxClassRegistrationView,
                item=this_item, item_data=i, post_data=post_data,
                prior_response=response, request=request
            )

            for s in signal_responses:
                if isinstance(s[1], dict) and s[1].get('status', None) != 'success':
                    errors += s[1].get('errors', [])
                elif isinstance(s[1], dict):
                    this_item_response.update(s[1].get('response', {}))
            items_response.append(this_item_response)

        # We now have an Invoice and the set of invoice items, but before going
        # further, return failure if any errors have arisen.
        if errors:
            return JsonResponse({
                'status': 'failure',
                'errors': errors,
            })

        # Add the item-related responses to the overall response dictionary.
        response['items'] = items_response

        # If we got this far with no issues, then save the invoice and invoice
        # items.  Delete any existing associated InvoiceItems whose IDs were not
        # passed in via POST.  Also, put the identifiers for the invoice and
        # invoice items into the response dictionary along with item level prices.
        # The invoice total is always updated at the end, so we pass a flag that
        # prevents it from being saved every time an item is saved.
        invoice.save()
        for key, value in response.items():
            if isinstance(key, str) and key.startswith('__relateditem'):
                value.save()
        for i in response.get('items', []):
            this_invoice_item = i.pop('__item', None)
            if isinstance(this_invoice_item, InvoiceItem):
                this_invoice_item.save(updateInvoiceTotals=False)
                i.update({
                    'id': str(this_invoice_item.id),
                    'grossTotal': this_invoice_item.grossTotal,
                })
            for key, value in i.items():
                if isinstance(key, str) and key.startswith('__relateditem'):
                    value.save()

        # Delete any items that are no longer in the POST data and ensure that
        # the Invoice totals are kept in sync.
        invoice.invoiceitem_set.filter(id__in=unmatched_item_ids).delete()
        items_queryset = invoice.updateTotals()

        # If a transaction is associated with event registration, then process
        # discount, addons, and vouchers
        reg = response.pop('__relateditem_registration', None)

        # Pass back student status.
        if getattr(reg, 'student', False):
            response.update({'student': reg.student})

        # Pop out keys associated with related items that are no longer needed,
        # since once the signal handlers are complete the remaining logic does
        # not use them.
        list_keys = list(response.keys())
        for key in list_keys:
            if key.startswith('__related'):
                response.pop(key)

        for i in response.get('items', []):
            list_keys = list(i.keys())
            for key in list_keys:
                if key.startswith('__related'):
                    i.pop(key)

        discount_codes, total_discount_amount = self.getDiscounts(
            invoice, registration=reg
        )
        if total_discount_amount > 0:
            response.update({
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
                'total': invoice.grossTotal - total_discount_amount,
            })

            # Update totals (without saving anything), so that taxes are
            # recalculated and the invoice handler knows how much to apply.
            if not post_data.get('finalize', False):
                items_queryset = invoice.updateTotals(
                    save=False, prior_queryset=items_queryset,
                    allocateAmounts={'total': -1*total_discount_amount}
                )

        addons = self.getAddons(invoice, reg)
        if addons:
            response.update({
                'addonItems': addons,
            })

        voucherId = post_data.get('voucher', {}).get('voucherId', None)
        if voucherId:
            response.update({
                'voucher': self.getVoucher(
                    voucherId, invoice, 0,
                    post_data.get('firstName', None),
                    post_data.get('lastName', None),
                    post_data.get('email', None),
                ),
            })

            if not post_data.get('finalize', False):
                # Recalculate taxes, but do not save the invoice
                # with the updates, since the voucher will only be applied later.
                # We pass the queryset that was returned by previous calls to
                # updateTotals(), so the update takes into account any discounts
                # that were previously applied.
                if response['voucher'].get('beforeTax'):
                    allocateAmounts = {'total': -1*response['voucher'].get('voucherAmount', 0)}
                else:
                    allocateAmounts = {'adjustments': -1*response['voucher'].get('voucherAmount', 0)}
                items_queryset = invoice.updateTotals(
                    save=False, allocateAmounts=allocateAmounts,
                    prior_queryset=items_queryset)

        response.update({
            'id': str(invoice.id),
            'grossTotal': invoice.grossTotal,
            'total': invoice.total,
            'adjustments': invoice.adjustments,
            'taxes': invoice.taxes,
            'outstandingBalance': invoice.outstandingBalance,
            'buyerPaysSalesTax': invoice.buyerPaysSalesTax,
            'itemCount': len(response.get('items', []))
        })

        # Format the response for return to the page that called this view 
        response_dict = {
            'status': 'success',
            'invoice': response,
        }

        # Pass the redirect URL and send the voucher ID to session data if
        # this is being finalized.
        if post_data.get('finalize') is True:

            data_changed_flag = False

            # Will only be set to False if every event has a set value of
            # requireFull, and if all of them are False.
            requireFullRegistration = (
                True in
                [x.get('requireFull', True) for x in item_post]
            )

            # If all events are to be registered using the same payment method
            # and auto-submit is always True, then pass this info to the registration.
            methods = [x.get('paymentMethod', None) for x in item_post]
            if len(set(methods)) == 1 and methods[0]:
                data_changed_flag = True
                invoice.data['paymentMethod'] = methods[0]

                if False not in [
                    x.get('autoSubmit', False) for x in item_post
                ]:
                    invoice.data['autoSubmit'] = True

            if not requireFullRegistration:

                # Update the registration to put the voucher code in data if
                # needed so that the Temporary Voucher Use is created before
                # we proceed to the summary page.
                if response.get('voucher', {}).get('voucherId', None):
                    invoice.data['gift'] = response['voucher']['voucherId']
                    data_changed_flag = True

                if data_changed_flag:
                    invoice.save()

                post_student_info.send(
                    sender=AjaxClassRegistrationView,
                    invoice=invoice, registration=reg
                )
                response_dict['redirect'] = reverse('showRegSummary')
            else:
                if data_changed_flag:
                    invoice.save()
                response_dict['redirect'] = reverse('getStudentInfo')

            regSession["voucher_id"] = response.get('voucher', {}).get('voucherId', None)

        regSession["invoiceId"] = invoice.id.__str__()
        regSession["invoiceExpiry"] = invoice.expirationDate.strftime('%Y-%m-%dT%H:%M:%S%z')
        regSession["payAtDoor"] = response.get('payAtDoor', False)
        request.session[REG_VALIDATION_STR] = regSession

        return JsonResponse(response_dict)

    def linkRegistration(self, invoice, post_data):
        '''
        This method checks to see whether a registration is needed for this
        transaction, and whether one already exists.  It returns a Registration.
        '''

        # Used for specifying defaults
        reg_nullable_keys = ['firstName', 'lastName', 'email', 'phone', 'howHeardAboutUs']
        reg_bool_keys = ['student', 'payAtDoor']

        eventreg_items = [x for x in post_data.get('items', []) if x.get('type', None) == 'eventRegistration']
        if not eventreg_items:
            return {}

        # Most transactions involve signing up for classes and events.  If so,
        # then we need to ensure that there is a Registration instance
        # associated with this invoice.
        response = {
            '__related_events': Event.objects.filter(
                id__in=[x.get('event') for x in eventreg_items if x.get('event', None)]
            ),
        }

        try:
            reg = Registration.objects.get(invoice=invoice)

            # If new values for optional registration parameters have been passed,
            # then update them.
            for key in reg_nullable_keys + reg_bool_keys:
                if post_data.get(key, None):
                    setattr(reg, key, post_data[key])
        except ObjectDoesNotExist:
            # Pass the POST and specify defaults.
            reg_defaults = {key: post_data.get(key, None) for key in reg_nullable_keys}
            reg_defaults.update({key: post_data.get(key, False) for key in reg_bool_keys})

            reg_defaults.update({
                'invoice': invoice,
                'submissionUser': invoice.submissionUser,
                'dateTime': timezone.now(),
                'comments': post_data.get('comments', ''),
                'data': {},
                'final': False,
            })

            # Create a new Registration (not finalized)
            reg = Registration(**reg_defaults)
        response['__relateditem_registration'] = reg
        return {'status': 'success', 'response': response}

    def linkEventRegistration(self, item, item_data, post_data, prior_response, request):
        '''
        This method checks whether an event registration can be added based on
        rules regarding drop-ins, multiple registration, etc.
        '''
        errors = []
        response = {'type': 'eventRegistration'}

        events = prior_response.get('__related_events', Event.objects.none())
        registration = prior_response.get('__relateditem_registration')

        if not registration:
            errors.append({
                'code': 'no_registration',
                'message': _('No registration set to link registration-related items.'),
            })

        try:
            this_event = events.get(id=item_data.get('event', None))
            response.update({
                'event': this_event.id,
                'description': this_event.name,
            })
        except ObjectDoesNotExist:
            errors.append({
                'code': 'invalid_event_id',
                'message': _('Invalid event ID passed.'),
            })
            this_event = None

        if errors:
            return {'status': 'failure', 'errors': errors}

        # Before continuing, we enforce rules on duplicate registrations, etc.
        # To do this, we need to know the drop-in status of the registration as
        # well as the associated role.
        response['dropIn'] = item_data.get('dropIn', False)

        # Pass back information about how automatic check-in should proceed.
        for v in ['dropInOccurrence', 'checkInType', 'checkInOccurrence']:
            response[v] = item_data.get(v, None)

        this_role = None

        if item_data.get('roleId', None):
            try:
                this_role = DanceRole.objects.get(id=item_data.get('roleId', None))
                response.update({
                    'roleId': this_role.id,
                    'roleName': this_role.name,
                })
            except ObjectDoesNotExist:
                errors.append({
                    'code': 'invalid_role',
                    'message': _('Invalid role specified.')
                })

        # Check the other eventregistrations in POST data to ensure
        # that this is the only one for this event.
        same_event = [x for x in post_data.get('items',[]) if x.get('event', None) == this_event.id]

        if len(same_event) > 1 and ((
            this_event.polymorphic_ctype.model == 'series' and not response['dropIn'] and (
                (getConstant('registration__multiRegSeriesRule') == 'N') or
                (
                    getConstant('registration__multiRegSeriesRule') == 'D' and not
                    registration.payAtDoor
                )
            )
        ) or (
            this_event.polymorphic_ctype.model == 'publicevent' and not response['dropIn'] and (
                (getConstant('registration__multiRegPublicEventRule') == 'N') or
                (
                    getConstant('registration__multiRegPublicEventRule') == 'D' and not
                    registration.payAtDoor
                )
            )
        ) or (
            response['dropIn'] and (
                (getConstant('registration__multiRegDropInRule') == 'N') or
                (
                    getConstant('registration__multiRegDropInRule') == 'D' and not
                    registration.payAtDoor
                )
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

        elif (
            len(same_event) > 1 and
            len([x for x in same_event if x.get('dropIn', False) != response['dropIn']]) > 0
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

        if not (
            this_event.registrationOpen or
            request.user.has_perm('core.override_register_closed')
        ):
            errors.append({
                'code': 'registration_closed',
                'message': _('Registration is closed for event {}.'.format(this_event.id))
            })

        # Check that the user can register for drop-ins, and that drop-ins are
        # either enabled, or they have override permissions.
        if not isinstance(this_event, Series) and response['dropIn']:
            errors.append({
                'code': 'invalid_dropin',
                'message': _('Cannot register as a drop-in for events that are not class series.')
            })
        elif (response['dropIn'] and (
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

        if errors:
            return {'status': 'error', 'errors': errors}

        # Since there are no errors, we can proceed to find an existing
        # EventRegistration or to create a new one.
        created_eventreg = False

        this_eventreg = EventRegistration.objects.filter(invoiceItem=item).first()

        if not this_eventreg:
            logger.debug('Creating event registration for event: {}'.format(this_event.id))
            this_eventreg = EventRegistration(
                event=this_event,
                invoiceItem=item,
                registration=registration,
            )
            created_eventreg = True

        if this_eventreg.event != this_event:
            errors.append({
                'code': 'event_mismatch',
                'message': _('Existing event registration is for a different event.'),
            })
        if this_eventreg.registration != registration:
            errors.append({
                'code': 'registration_mismatch',
                'message': _('Existing event registration is associated with a different registration.'),
            })

        if errors:
            return {'status': 'error', 'errors': errors}

        # Update the contents of the event registration and the invoice item.
        if response['dropIn']:
            this_eventreg.dropIn = True
            item.grossTotal = this_event.getBasePrice(dropIns=1)
            this_eventreg.role = this_role

            # We cannot add occurrences to the many-to-many relationship until
            # after the event registration has been saved.  So, we add it to
            # the EventRegistration data for now.
            if item_data.get('dropInOccurrence'):
                this_eventreg.data['__dropInOccurrences'] = [item_data['dropInOccurrence'],]
        else:
            this_eventreg.dropIn = False
            item.grossTotal = this_event.getBasePrice(payAtDoor=registration.payAtDoor)
            this_eventreg.role = this_role

        if item_data.get('checkInType') in ['E', 'S'] and item_data.get('checkInOccurrence'):
            this_eventreg.data['__checkInOccurrence'] = item_data['checkInOccurrence']
        elif item_data.get('checkInType') == 'F':
            this_eventreg.data['__checkInEvent'] = True

        item.total = item.grossTotal
        item.taxRate = getConstant('registration__salesTaxRate') or 0
        item.calculateTaxes()

        if item_data.get('data', False):
            if isinstance(item_data['data'], dict):
                this_eventreg.data.update(item_data['data'])
            else:
                try:
                    this_eventreg.data.update(json.loads(item_data['data']))
                except json.decoder.JSONDecodeError:
                    errors.append({
                        'code': 'invalid_json',
                        'message': _('You have passed invalid JSON data for this registation.')
                    })

        if (
            created_eventreg and this_event.soldOut and not
            request.user.has_perm('core.override_register_soldout')
        ):
            errors.append({
                'code': 'sold_out',
                'message': _('Event {} is sold out.'.format(this_event.id))
            })

        if (
            created_eventreg and
            this_event.soldOutForRole(this_role, includeTemporaryRegs=True) and not
            request.user.has_perm('core.override_register_soldout')
        ):
            errors.append({
                'code': 'sold_out_role',
                'message': _('Event {} is sold out for role {}.'.format(this_event.id, this_role))
            })

        # Now that all checks are complete, return failure or success.
        if errors:
            return {'status': 'failure', 'errors': errors}

        response['__relateditem_eventregistration'] = this_eventreg
        return {'status': 'success', 'response': response}


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

        reg = Registration.objects.filter(invoice=invoice).first()

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
        addons = []

        if reg:
            discount_codes, total_discount_amount = self.getDiscounts(
                invoice, registration=reg
            )
            addons = self.getAddons(invoice, reg)

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
            prior_adjustment=-1*total_discount_amount,
        )

        combined_response = {
            'total_pretax': 0,
            'total_posttax': 0,
            'items': [],
        }

        for response in adjustment_responses:
            combined_response['total_pretax'] += response[1].get('total_pretax', 0)
            combined_response['total_posttax'] += response[1].get('total_posttax', 0)
            combined_response['items'] += response[1].get('items', [])

        # The updateTotals method allocates the total adjustment across the
        # invoice items, and also recalculates the taxes for each item.
        invoice.updateTotals(
            allocateAmounts={
                'total': -1*(combined_response['total_pretax'] + total_discount_amount),
                'adjustments': -1*(combined_response['total_posttax']),
            },
            save=True,
        )

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

        regSession['vouchers'] = combined_response
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
        vouchers = regSession.get('vouchers', {})
        addons = regSession.get('addons', [])

        zeroBalance = (invoice.outstandingBalance == 0)
        isComplete = (zeroBalance or regSession.get('direct_payment', False) is True)

        if isComplete:
            # Include the submission user if the user is authenticated
            if self.request.user.is_authenticated:
                submissionUser = self.request.user
            else:
                submissionUser = None

            if zeroBalance:
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
            "vouchers": vouchers,
            "total_discount_amount": discount_amount + vouchers.get('total_pretax', 0),
            "total_adjustment_amount": vouchers.get('total_posttax', 0),
            "currencyCode": getConstant('general__currencyCode'),
            'payAtDoor': regSession.get('payAtDoor', False),
            'is_complete': isComplete,
            'zero_balance': zeroBalance,
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

        self.registration = Registration.objects.filter(invoice=self.invoice).first()

        # Ensure that session data is always updated when this view is called
        # so that passed voucher_ids are cleared.
        request.session.modified = True

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        reg = self.registration

        payAtDoor = self.request.session[REG_VALIDATION_STR].get('payAtDoor', False)

        discount_codes, total_discount_amount = self.getDiscounts(
            self.invoice, registration=reg
        )
        addons = self.getAddons(self.invoice, reg)

        # Update totals (without saving anything), so that taxes are
        # recalculated and the invoice handler knows how much to apply.
        items_queryset = self.invoice.updateTotals(
            save=False, allocateAmounts={'total': -1*total_discount_amount}
        )

        # Get a voucher ID to check from the current contents of the form
        voucherId = getattr(context_data['form'].fields.get('gift'), 'initial', None)

        if voucherId:
            context_data['voucher'] = self.getVoucher(voucherId, self.invoice)

            # Recalculate taxes, but do not save the invoice
            # with the updates, since the voucher will only be applied later.
            if context_data['voucher'].get('beforeTax'):
                allocateAmounts = {'total': -1*context_data['voucher'].get('voucherAmount', 0)}
            else:
                allocateAmounts = {'adjustments': -1*context_data['voucher'].get('voucherAmount', 0)}
            items_queryset = self.invoice.updateTotals(
                save=False, allocateAmounts=allocateAmounts,
                prior_queryset=items_queryset
            )

        if (
            payAtDoor or
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

        context_data.update({
            'invoice': self.invoice,
            'currencySymbol': getConstant('general__currencySymbol'),
            'reg': reg,
            'payAtDoor': payAtDoor,
            'addonItems': addons,
            'discount_codes': discount_codes,
            'discount_code_amount': total_discount_amount,
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

            invoice = reg.link_invoice(expirationDate=expiry)

            # Anything else in the form goes to the Invoice data.
            invoice.data.update(form.cleaned_data)
            invoice.save()
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
        post_student_info.send(sender=StudentInfoView, invoice=invoice, registration=reg)
        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST
