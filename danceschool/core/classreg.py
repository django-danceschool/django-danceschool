from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect, Http404, JsonResponse
from django.shortcuts import redirect
from django.views.generic import FormView, RedirectView, TemplateView, View
from django.urls import NoReverseMatch
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy as _
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import logging
from allauth.account.forms import LoginForm, SignupForm
from datetime import timedelta
import json
from braces.views import PermissionRequiredMixin
import uuid
from copy import deepcopy
from itertools import chain
from rest_framework import status, exceptions
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Event, Series, PublicEvent, Invoice, InvoiceItem, Customer,
    CashPaymentRecord, DanceRole, EventRole, Registration, EventRegistration
)
from .forms import (
    RegistrationContactForm, MultiRegCustomerNameForm, PartnerRequiredForm
)
from .constants import getConstant, REG_VALIDATION_STR
from .signals import (
    post_student_info, apply_discount, apply_price_adjustments,
    get_invoice_related, get_invoice_item_related, get_cart_invoice_related,
    get_cart_invoice_item_related, request_discounts, check_voucher
)
from .helpers import getPurchasableItems
from .serializers import PurchasableItemSerializer, CartSerializer
from .mixins import (
    FinancialContextMixin, EventOrderMixin, SiteHistoryMixin,
    RegistrationAdjustmentsMixin, ReferralInfoMixin
)
from .utils.timezone import ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


def clear_reg_cart(request):
    '''
    Remove only the 'cart' key from the registration session, leaving all
    other session state (invoice_id, payAtDoor, link_authorized, etc.) intact.
    '''
    reg_session = request.session.get(REG_VALIDATION_STR)
    if reg_session and 'cart' in reg_session:
        del reg_session['cart']
        request.session.modified = True


class RegistrationOfflineView(TemplateView):
    '''
    If registration is offline, just say so.
    '''
    template_name = 'core/registration/registration_offline.html'


class PurchasableItemPagination(PageNumberPagination):
    page_size = 20


class PurchasableItemsView(ListAPIView):
    serializer_class = PurchasableItemSerializer
    permission_classes = [AllowAny]
    pagination_class = PurchasableItemPagination

    def get_queryset(self) -> list:
        # If registration is not online then do not return a list of items
        # available for registration
        regOnline = getConstant('registration__registrationEnabled')
        if not regOnline:
            return []

        self.serializer_map = {}

        # payAtDoor may be requested via query parameter, but only for users
        # with door payment permissions. Regular users cannot activate door
        # mode by manipulating the query string.
        self.payAtDoor = (
            self.request.query_params.get('payAtDoor', '').lower() in ('true', '1', 'yes')
            and self.request.user.has_perm('core.accept_door_payments')
        )

        responses = getPurchasableItems(
            sender=self.__class__, request=self.request, payAtDoor=self.payAtDoor
        )
        querysets = []

        for qs, serializer in responses:
            if qs is None or not hasattr(qs, "model"):
                continue

            self.serializer_map[qs.model] = serializer
            querysets.append(qs)

        # Chain all objects from the querysets into a single iterable
        combined = chain.from_iterable(qs for qs in querysets)

        # Convert to a list so we can sort and paginate
        items = list(combined)

        # Sort safely by a shared attribute, if one exists (e.g. "name")
        # items.sort(key=lambda obj: getattr(obj, "name", "").lower())

        return items

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['serializer_map'] = getattr(self, 'serializer_map', {})
        context['payAtDoor'] = getattr(self, 'payAtDoor', False)
        return context


class CartView(RegistrationAdjustmentsMixin, APIView):
    permission_classes = [AllowAny]

    @cached_property
    def purchasable_registry(self):
        return getPurchasableItems(
            sender=self.__class__,
            request=self.request,
            payAtDoor=self.payAtDoor
        )

    def validate_cart(self, request, data=None):
        '''
        Shared serializer validation for post and delete requests. Note that
        data and door status have already been added by dispatch as properties
        of the view.
        '''
        if data is None:
            data = self.raw_data

        serializer = CartSerializer(
            data=data,
            context={
                'request': request,
                'payAtDoor': self.payAtDoor,
                'purchasable_items': self.purchasable_registry
            }
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def create_invoice_from_cart(self, cart, request):
        '''
        If there is an existing invoice, update it. Otherwise, create a new
        one with items that match the shopping cart.
        '''

        # For later reference
        invoice_update_keys = ['firstName', 'lastName', 'email']

        # Item data is popped off the cart to be handled separately.
        item_data = cart.pop('items', [])

        reg_session = request.session.get(REG_VALIDATION_STR, {})
        existing_invoice_id = reg_session.get('invoice_id')
        invoice_expiry = parse_datetime(
            reg_session.get('invoice_expiry', '')
        )
        if existing_invoice_id and (invoice_expiry < timezone.now()):
            # Delete any preliminary invoice that has expired
            Invoice.objects.filter(
                id=existing_invoice_id, status=Invoice.PaymentStatus.preliminary
            ).delete()
            invoice = None
        elif existing_invoice_id:
            invoice = Invoice.objects.filter(
                id=existing_invoice_id, _items_editable=True
            ).first()
        else:
            invoice = None

        if invoice:
            for key in invoice_update_keys:
                value = cart.pop(key, None)
                if value:
                    setattr(invoice, key, value)
                data = invoice.data or {}
                data.update(cart)
                invoice.data = data
        else:
            # Some information on the shopping cart can go into invoice fields.
            # All else goes in Invoice data. Note that items have already been
            # popped off.
            invoice_defaults = {
                key: cart.pop(key, None) for key in invoice_update_keys
            }
            invoice_defaults.update({
                'submissionUser': (
                    request.user if request.user.is_authenticated else None
                ),
                'data': cart,
                'status': Invoice.PaymentStatus.preliminary,
                'buyerPaysSalesTax': getConstant('registration__buyerPaysSalesTax'),
            })
            invoice = Invoice(**invoice_defaults)

        # Update expiration date for this invoice (will also be updated in
        # session data).  Also reset all totals to 0 (will be populated by
        # signal handlers.)
        invoice.expirationDate = (
            timezone.now() +
            timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
        )
        for attr in ['grossTotal', 'total', 'taxes', 'adjustments', 'fees']:
            setattr(invoice, attr, 0)

        if reg_session.get('marketing_id'):
            invoice.data.update({
                'marketing_id': reg_session.pop('marketing_id', None)
            })

        # Delete any existing items on this invoice (the values in the cart
        # always prevail). Guard against unsaved invoices with no PK yet.
        if invoice.pk:
            invoice.invoiceitem_set.all().delete()

        # Expand items with quantity > 1 into multiple single-quantity items so
        # that each person in a group registration gets their own EventRegistration.
        expanded = []
        for item in item_data:
            qty = max(1, int(item.get('quantity') or 1))
            for _qty_i in range(qty):
                expanded.append({**item, 'quantity': 1})
        item_data = expanded

        # Collect related objects (e.g. Registration, MerchOrder) that need to
        # be created or retrieved for this invoice before processing items.
        # Signal handlers return these under __relateditem_* keys so they can
        # be saved after the invoice itself.
        response = {}
        errors = []
        signal_responses = get_cart_invoice_related.send(
            sender=self.__class__,
            request=request,
            invoice=invoice,
            item_data=item_data,
            payAtDoor=self.payAtDoor,
        )

        for s in signal_responses:
            if isinstance(s[1], dict) and s[1].get('status') != 'success':
                errors += s[1].get('errors', [])
            elif isinstance(s[1], dict):
                response.update(s[1].get('response', {}))
        if errors:
            raise exceptions.ValidationError(errors)

        # Loop through cart items and create InvoiceItems. Signal handlers are
        # responsible for resolving pricing and creating linked records such as
        # EventRegistration or MerchOrderItem. The purchasable_registry is
        # passed so handlers can use the already-fetched querysets rather than
        # issuing redundant DB queries. We use a while loop so handlers can
        # append child items (e.g. add-on events) to item_data, which are then
        # processed in subsequent iterations.
        items_response = []
        counter = 0
        while counter < len(item_data):
            i = item_data[counter]
            counter += 1

            this_item = InvoiceItem(invoice=invoice)
            for attr in ['grossTotal', 'total', 'taxes', 'adjustments', 'fees']:
                setattr(this_item, attr, 0)

            this_item_response = {'__item': this_item}

            item_signal_responses = get_cart_invoice_item_related.send(
                sender=self.__class__,
                item=this_item,
                item_data=i,
                cart_data=item_data,
                prior_response=response,
                purchasable_registry=self.purchasable_registry,
                request=request,
                cart_student=cart.get('student', False),
            )

            for s in item_signal_responses:
                if isinstance(s[1], dict) and s[1].get('status') != 'success':
                    errors += s[1].get('errors', [])
                elif isinstance(s[1], dict):
                    this_item_response.update(s[1].get('response', {}))

            # Allow handlers to enqueue child items (e.g. add-on events).
            item_data.extend(this_item_response.pop('child_items', []))
            items_response.append(this_item_response)

        if errors:
            raise exceptions.ValidationError(errors)

        # Save the invoice and any top-level related objects.
        invoice.save()
        for key, value in response.items():
            if isinstance(key, str) and key.startswith('__relateditem'):
                value.save()

        # Save invoice items with parent-child linking via register_uuid.
        for i in items_response:
            this_invoice_item = i.get('__item')
            if isinstance(this_invoice_item, InvoiceItem):
                if i.get('register_uuid') and i.get('child_item', False):
                    parent_response = next(
                        (
                            x for x in items_response if
                            x.get('register_uuid') == i['register_uuid'] and
                            not x.get('child_item', False)
                        ),
                        None
                    )
                    if parent_response:
                        this_invoice_item.parent_item = parent_response['__item']
                this_invoice_item.save(updateInvoiceTotals=False)
            for key, value in i.items():
                if isinstance(key, str) and key.startswith('__relateditem'):
                    value.save()

        invoice.updateTotals()
        return invoice

    def get_discount_preview(self, cart_items, cart_data):
        '''
        Fire the request_discounts signal with a temporary, unsaved Invoice to
        get a read-only discount preview.  No RegistrationDiscount records are
        created here — that only happens during checkout via apply_discount.

        Returns a dict with keys ``discounts``, ``gross_total``,
        ``discounted_total``, and ``total_discount``, or None when no discount
        applies or the discounts app is not active.
        '''
        # Only Event items are eligible for discounts.
        event_items = [i for i in cart_items if i.get('item_type') == 'Event']
        if not event_items:
            return None

        # Find the Event queryset in the purchasable registry so we can compute
        # prices without an extra DB round-trip.
        event_qs = None
        for qs, _ in self.purchasable_registry:
            if qs.model.__name__ == 'Event':
                event_qs = qs
                break
        if event_qs is None:
            return None

        event_ids = [i['item_id'] for i in event_items]
        events_by_id = {e.id: e for e in event_qs.filter(id__in=event_ids)}

        gross_total = sum(
            events_by_id[i['item_id']].getBasePrice(payAtDoor=self.payAtDoor)
            * i.get('quantity', 1)
            for i in event_items
            if i['item_id'] in events_by_id
        )

        # Build a temporary, unsaved Invoice.  grossTotal is needed so
        # getDiscounts() can compute the discount amount.  Customer fields
        # allow first-time-customer logic to work when provided.
        tmp_invoice = Invoice(
            grossTotal=gross_total,
            firstName=cart_data.get('firstName', ''),
            lastName=cart_data.get('lastName', ''),
            email=cart_data.get('email', ''),
        )

        discount_responses = request_discounts.send(
            sender=RegistrationAdjustmentsMixin,
            registration=None,
            invoice=tmp_invoice,
            cart_items=event_items,
            customer_final=False,
            voucher_code=cart_data.get('discount_code'),
            student=cart_data.get('student', False),
            payAtDoor=self.payAtDoor,
        )
        discount_responses = [x[1] for x in discount_responses if len(x) > 1 and x[1]]

        if not discount_responses:
            return None

        discount_responses.sort(
            key=lambda k: min(
                [getattr(x, 'net_price', gross_total) for x in k.items] +
                [gross_total]
            ) if k and hasattr(k, 'items') else gross_total
        )

        best = discount_responses[0]
        discount_codes = getattr(best, 'items', [])
        if not discount_codes:
            return None

        discounted_total = (
            min(getattr(x, 'net_price', gross_total) for x in discount_codes)
            + getattr(best, 'ineligible_total', 0)
        )
        total_discount = gross_total - discounted_total

        return {
            'discounts': [
                {
                    'name': getattr(getattr(x, 'code', None), 'name', str(x.code)),
                    'discount_amount': float(x.discount_amount),
                }
                for x in discount_codes
            ],
            'gross_total': float(gross_total),
            'discounted_total': float(discounted_total),
            'total_discount': float(total_discount),
        }

    def get_voucher_preview(self, cart_items, discount_code):
        '''
        Fire the check_voucher signal with the given discount_code to get a
        read-only voucher preview.  No VoucherUse records are created here.

        Returns a dict with keys ``voucher_id``, ``voucher_name``,
        ``voucher_amount``, and ``before_tax``, or None when the code is absent
        or the vouchers app is not active.
        '''
        if not discount_code:
            return None

        responses = check_voucher.send(
            sender=self.__class__,
            voucherId=discount_code,
            cart_items=cart_items,
            customer=None,
            validateCustomer=False,
            invoice=None,
            payAtDoor=self.payAtDoor,
        )
        responses = [r[1] for r in responses if len(r) > 1 and r[1]]
        if not responses:
            return None

        result = responses[0]
        if result.get('status') == 'valid':
            return {
                'voucher_id': result.get('id'),
                'voucher_name': result.get('name'),
                'voucher_amount': float(result.get('available', 0)),
                'before_tax': result.get('beforeTax', True),
            }
        elif result.get('status') == 'invalid':
            errors = result.get('errors', [])
            return {
                'voucher_id': discount_code,
                'error': errors[0].get('message', '') if errors else '',
            }
        return None

    def get_success_url(self):
        return reverse('getStudentInfo')

    def dispatch(self, request, *args, **kwargs):
        '''
        Determine at-the-door status, and check permissions for door
        registrations. Set door status as a property of the view so that the
        cached purchasable registry can access it.
        '''
        mode=kwargs.pop('mode', 'online')

        # request.data is a DRF attribute that only exists after super().dispatch()
        # wraps the request. Parse the body directly here so that payAtDoor can be
        # determined before permission checks run.
        if 'data' in kwargs:
            data = kwargs.get('data') or {}
        else:
            try:
                data = json.loads(request.body) if request.body else {}
            except (ValueError, AttributeError):
                data = {}

        # Set the existing cart as a property of the view since it will be used
        # by all subsequent request methods.
        self.existing_cart = (
            request.session.get(REG_VALIDATION_STR, {}).get('cart', {})
        )

        # Fill in door status based on the available information.
        payAtDoor = False

        # First, if there is an existing cart, get door status from it.
        if self.existing_cart:
            payAtDoor = self.existing_cart.pop('payAtDoor', False)
        # If door status is not already True, then we may update status based on
        # the passed data or keyword arguments. This permits changes from online
        # to at-the-door, but not the other way.
        if not payAtDoor:
            payAtDoor = data.pop('payAtDoor', (mode == 'door'))

        # Now set data and door status as properties so they will persist
        # throughout the view.
        self.raw_data = data
        self.payAtDoor = payAtDoor

        return super().dispatch(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Check for door permissions inside DRF's request lifecycle so that
        # PermissionDenied is handled by DRF's exception handler (returns 403).
        if self.payAtDoor and not request.user.has_perm('core.accept_door_payments'):
            raise exceptions.PermissionDenied(
                'You lack door registration permissions.'
            )

    def get(self, request):
        return Response(self.existing_cart)

    def post(self, request, *args, **kwargs):
        # Return the validated cart minus any parameters that should not
        # persist (such as the checkout flag).
        new_cart_data = self.validate_cart(request)
        checkout = new_cart_data.pop('checkout', False)

        request.session.setdefault(REG_VALIDATION_STR, {})['cart'] = new_cart_data
        # Persist door status and student flag at the session top level so that
        # StudentInfoView can read them without relying on the POST body.
        request.session[REG_VALIDATION_STR]['payAtDoor'] = self.payAtDoor
        request.session[REG_VALIDATION_STR]['student'] = bool(new_cart_data.get('student'))
        request.session.modified = True

        # Handle checkout flow
        if checkout:
            if not new_cart_data.get('items'):
                return Response(
                    [{'message': str(_('Please select at least one item before checking out.'))}],
                    status=status.HTTP_400_BAD_REQUEST
                )
            invoice = self.create_invoice_from_cart(dict(new_cart_data), request)
            reg_session = request.session.setdefault(REG_VALIDATION_STR, {})
            reg_session['invoice_id'] = str(invoice.id)
            reg_session['invoice_expiry'] = invoice.expirationDate.isoformat()
            request.session.modified = True
            return HttpResponseRedirect(self.get_success_url())

        # Add a read-only discount/voucher preview to the response so the cart
        # UI can display the expected savings without creating any DB records.
        response_data = dict(new_cart_data)
        discount_preview = self.get_discount_preview(
            new_cart_data.get('items', []), new_cart_data
        )
        if discount_preview:
            response_data['discount_preview'] = discount_preview

        voucher_preview = self.get_voucher_preview(
            new_cart_data.get('items', []), new_cart_data.get('discount_code')
        )
        if voucher_preview:
            response_data['voucher_preview'] = voucher_preview

        return Response(response_data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        item_id = request.data.get("item_id")
        cart = request.session.get(REG_VALIDATION_STR, {}).get('cart', {})
        cart['items'] = [c for c in cart.get('items', []) if c["item_id"] != item_id]
        new_cart_data = self.validate_cart(
            request, data=cart
        )
        request.session.setdefault(REG_VALIDATION_STR, {})['cart'] = new_cart_data
        request.session.modified = True
        return Response(cart, status=status.HTTP_200_OK)


class CartSummaryView(RegistrationAdjustmentsMixin, TemplateView):
    '''
    Displays a summary of the current session cart, with per-item remove
    buttons, a discount/voucher preview, and navigation buttons to either
    return to PublicRegisterView (add more items) or proceed to checkout
    (StudentInfoView).

    This view is intentionally outside the main registration flow.  It is
    meant to serve as an interstitial page when items are added to the cart
    from outside PublicRegisterView (e.g. a "Register Now" button on an event
    detail page) and the user should be given the opportunity to review or
    extend their cart before continuing.
    '''
    template_name = 'core/cart_summary.html'

    def dispatch(self, request, *args, **kwargs):
        reg_session = request.session.get(REG_VALIDATION_STR, {})
        # Work on a shallow copy so we don't accidentally mutate the session.
        self.cart = dict(reg_session.get('cart', {}))
        self.payAtDoor = self.cart.get('payAtDoor', reg_session.get('payAtDoor', False))
        return super().dispatch(request, *args, **kwargs)

    def _enrich_cart_items(self):
        '''
        Return a list of dicts augmenting each session cart item with display
        information: the Event object, role name, per-unit price, event URL,
        and whether the registration is a drop-in.

        Only the events referenced by items currently in the cart are queried.
        '''
        cart_items = self.cart.get('items', [])

        event_ids = [i['item_id'] for i in cart_items if i.get('item_type') == 'Event']
        events_by_id = {
            e.id: e for e in Event.objects.filter(id__in=event_ids)
        } if event_ids else {}

        enriched = []
        for item in cart_items:
            d = dict(item)
            sku = d.get('sku', '')
            if d.get('item_type') == 'Event':
                event = events_by_id.get(d['item_id'])
                if event:
                    d['event'] = event
                    d['event_url'] = event.get_absolute_url()
                    d['price'] = event.getBasePrice(payAtDoor=self.payAtDoor)
                    d['is_dropin'] = 'DROPIN' in sku
                    if '_ROLE_' in sku:
                        try:
                            role_id = int(sku.rsplit('_ROLE_', 1)[-1])
                            try:
                                eventrole = EventRole.objects.get(
                                    role__id=role_id, event=event
                                )
                                d['role'] = eventrole.role
                            except ObjectDoesNotExist:
                                d['role'] = DanceRole.objects.filter(id=role_id).first()
                        except (ValueError, ObjectDoesNotExist):
                            pass
            enriched.append(d)
        return enriched

    def _get_discount_preview(self, events_by_id):
        '''
        Fire the request_discounts signal with a temporary, unsaved Invoice to
        get a read-only discount preview.  Returns the same dict format as
        CartView.get_discount_preview, or None when no discount applies.

        ``events_by_id`` is the already-fetched {id: event} mapping built in
        _enrich_cart_items so we avoid a second database round-trip.
        '''
        cart_items = self.cart.get('items', [])
        event_items = [i for i in cart_items if i.get('item_type') == 'Event']
        if not event_items:
            return None

        gross_total = sum(
            events_by_id[i['item_id']].getBasePrice(payAtDoor=self.payAtDoor)
            * i.get('quantity', 1)
            for i in event_items
            if i['item_id'] in events_by_id
        )

        tmp_invoice = Invoice(
            grossTotal=gross_total,
            firstName=self.cart.get('firstName', ''),
            lastName=self.cart.get('lastName', ''),
            email=self.cart.get('email', ''),
        )

        discount_responses = request_discounts.send(
            sender=RegistrationAdjustmentsMixin,
            registration=None,
            invoice=tmp_invoice,
            cart_items=event_items,
            customer_final=False,
            voucher_code=self.cart.get('discount_code'),
            student=self.cart.get('student', False),
            payAtDoor=self.payAtDoor,
        )
        discount_responses = [x[1] for x in discount_responses if len(x) > 1 and x[1]]
        if not discount_responses:
            return None

        discount_responses.sort(
            key=lambda k: min(
                [getattr(x, 'net_price', gross_total) for x in k.items] + [gross_total]
            ) if k and hasattr(k, 'items') else gross_total
        )

        best = discount_responses[0]
        discount_codes = getattr(best, 'items', [])
        if not discount_codes:
            return None

        discounted_total = (
            min(getattr(x, 'net_price', gross_total) for x in discount_codes)
            + getattr(best, 'ineligible_total', 0)
        )

        return {
            'discounts': [
                {
                    'name': getattr(getattr(x, 'code', None), 'name', str(x.code)),
                    'discount_amount': float(x.discount_amount),
                }
                for x in discount_codes
            ],
            'gross_total': float(gross_total),
            'discounted_total': float(discounted_total),
            'total_discount': float(gross_total - discounted_total),
        }

    def _get_voucher_preview(self):
        '''
        Fire the check_voucher signal to get a read-only voucher preview.
        Returns the same dict format as CartView.get_voucher_preview, or None.
        '''
        discount_code = self.cart.get('discount_code')
        if not discount_code:
            return None

        cart_items = self.cart.get('items', [])
        responses = check_voucher.send(
            sender=self.__class__,
            voucherId=discount_code,
            cart_items=cart_items,
            customer=None,
            validateCustomer=False,
            invoice=None,
            payAtDoor=self.payAtDoor,
        )
        responses = [r[1] for r in responses if len(r) > 1 and r[1]]
        if not responses:
            return None

        result = responses[0]
        if result.get('status') == 'valid':
            return {
                'voucher_id': result.get('id'),
                'voucher_name': result.get('name'),
                'voucher_amount': float(result.get('available', 0)),
                'before_tax': result.get('beforeTax', True),
            }
        elif result.get('status') == 'invalid':
            errors = result.get('errors', [])
            return {
                'voucher_id': discount_code,
                'error': errors[0].get('message', '') if errors else '',
            }
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_items = self._enrich_cart_items()

        # Build the events_by_id map from the already-enriched items so the
        # discount preview doesn't issue a second DB query.
        events_by_id = {
            d['item_id']: d['event']
            for d in cart_items
            if d.get('item_type') == 'Event' and d.get('event')
        }

        discount_preview = self._get_discount_preview(events_by_id)
        voucher_preview = self._get_voucher_preview()

        gross_total = sum(
            d.get('price', 0) * d.get('quantity', 1)
            for d in cart_items
            if d.get('price') is not None
        )
        net_total = gross_total
        if discount_preview:
            net_total -= discount_preview.get('total_discount', 0)
        if voucher_preview and not voucher_preview.get('error'):
            net_total -= voucher_preview.get('voucher_amount', 0)

        from django.urls import NoReverseMatch
        try:
            add_more_url = reverse('registration')
        except NoReverseMatch:
            add_more_url = '/'

        context.update({
            'cart_items': cart_items,
            'discount_preview': discount_preview,
            'voucher_preview': voucher_preview,
            'gross_total': gross_total,
            'net_total': max(net_total, 0),
            'currencySymbol': getConstant('general__currencySymbol'),
            'payAtDoor': self.payAtDoor,
            'add_more_url': add_more_url,
        })
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', '')

        if action == 'add':
            try:
                item_id = int(request.POST.get('item_id', ''))
            except (ValueError, TypeError):
                messages.error(request, _('Invalid item.'))
                return HttpResponseRedirect(reverse('cartSummary'))

            # Build the new item dict from the POST fields.
            sku = request.POST.get('sku') or f'EVENT_{item_id}_GENERAL'
            try:
                quantity = max(1, int(request.POST.get('quantity', 1)))
            except (ValueError, TypeError):
                quantity = 1

            new_item = {
                'item_type': 'Event',
                'item_id': item_id,
                'sku': sku,
                'quantity': quantity,
            }
            if request.POST.get('dropIn') == 'true':
                new_item['dropIn'] = True
                try:
                    occurrence_id = int(request.POST.get('dropInOccurrence', ''))
                    new_item['dropInOccurrence'] = occurrence_id
                except (ValueError, TypeError):
                    pass

            cart = request.session.get(REG_VALIDATION_STR, {}).get('cart', {})
            cart.setdefault('items', []).append(new_item)
            request.session.setdefault(REG_VALIDATION_STR, {})['cart'] = cart
            request.session.modified = True
            return HttpResponseRedirect(reverse('cartSummary'))

        if action == 'remove':
            item_id = request.POST.get('item_id')
            if item_id:
                try:
                    item_id_int = int(item_id)
                    cart = request.session.get(REG_VALIDATION_STR, {}).get('cart', {})
                    cart['items'] = [
                        i for i in cart.get('items', [])
                        if i.get('item_id') != item_id_int
                    ]
                    request.session.setdefault(REG_VALIDATION_STR, {})['cart'] = cart
                    request.session.modified = True
                except (ValueError, TypeError):
                    pass
            return HttpResponseRedirect(reverse('cartSummary'))

        if action == 'checkout':
            cart = request.session.get(REG_VALIDATION_STR, {}).get('cart', {})
            if not cart.get('items'):
                messages.error(
                    request,
                    _('Please add at least one item before checking out.')
                )
                return HttpResponseRedirect(reverse('cartSummary'))

            # Delegate invoice creation to CartView, which owns that logic.
            # CartView.create_invoice_from_cart only needs request, payAtDoor,
            # and purchasable_registry on the instance.  We build a minimal
            # stand-in rather than going through the full API dispatch cycle.
            cart_view = CartView()
            cart_view.request = request
            cart_view.payAtDoor = self.payAtDoor
            cart_view.args = ()
            cart_view.kwargs = {}
            try:
                invoice = cart_view.create_invoice_from_cart(deepcopy(cart), request)
            except (ValidationError, exceptions.ValidationError) as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(reverse('cartSummary'))

            reg_session = request.session.setdefault(REG_VALIDATION_STR, {})
            reg_session['invoice_id'] = str(invoice.id)
            reg_session['invoice_expiry'] = invoice.expirationDate.isoformat()
            reg_session['payAtDoor'] = self.payAtDoor
            request.session.modified = True
            return HttpResponseRedirect(reverse('getStudentInfo'))

        return HttpResponseRedirect(reverse('cartSummary'))


class RegistrationSummaryView(
    FinancialContextMixin, RegistrationAdjustmentsMixin, SiteHistoryMixin, TemplateView
):
    template_name = 'core/registration_summary.html'

    # Ensures that customer-specific discounts are applied at this stage
    customers_final = True

    def dispatch(self, request, *args, **kwargs):
        ''' Always check that the temporary registration has not expired '''
        regSession = self.request.session.get(REG_VALIDATION_STR, {})

        if not regSession:
            return HttpResponseRedirect(reverse('registration'))

        try:
            invoice = Invoice.objects.get(
                id=self.request.session[REG_VALIDATION_STR].get('invoice_id')
            )
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to summary view.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoice_expiry', ''),
        )
        if not expiry or expiry < timezone.now():
            clear_reg_cart(request)
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

        voucherId = invoice.data.get('discount_code') or invoice.data.get('gift')

        if reg:
            discount_codes, total_discount_amount, voucherId = self.getDiscounts(
                invoice, registration=reg, voucher_code=voucherId
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
        # need to be made to the price (e.g., from vouchers if the voucher app
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


class PartnerRequiredView(RegistrationAdjustmentsMixin, FormView):
    '''
    When one or more events in a customer's registration have a partner
    required, this page is used to collect partner name information for each
    registrant to that event.
    '''
    form_class = PartnerRequiredForm
    template_name = 'core/partner_required_form.html'

    # Ensures that customer-specific discounts are applied at this stage
    customers_final = True

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
                id=self.request.session[REG_VALIDATION_STR].get('invoice_id')
            )
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to sign-up form.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoice_expiry', ''),
        )
        if not expiry or expiry < timezone.now():
            clear_reg_cart(request)
            messages.info(request, _('Your registration session has expired. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        if self.invoice.status != Invoice.PaymentStatus.preliminary:
            messages.error(request, _('The current invoice has already been submitted. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        self.registration = Registration.objects.filter(
            invoice=self.invoice
        ).prefetch_related(
            'eventregistration_set', 'eventregistration_set__event',
            'eventregistration_set__customer'
        ).first()

        if not self.registration:
            messages.error(request, _('Invalid registration passed to additional customer name form.'))
            return HttpResponseRedirect(reverse('registration'))

        self.partnerRequiredRegs = self.registration.eventregistration_set.filter(
            event__partnerRequired=True
        )

        if not self.partnerRequiredRegs:
            return HttpResponseRedirect(self.get_success_url())

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        reg = self.registration

        payAtDoor = self.request.session[REG_VALIDATION_STR].get('payAtDoor', False)

        # Get a voucher ID to check from the current contents of the form
        voucherId = self.invoice.data.get('discount_code') or self.invoice.data.get('gift')

        discount_codes, total_discount_amount, voucherId = self.getDiscounts(
            self.invoice, registration=reg, voucher_code=voucherId
        )
        addons = self.getAddons(self.invoice, reg)

        # Update totals (without saving anything), so that taxes are
        # recalculated and the invoice handler knows how much to apply.
        items_queryset = self.invoice.updateTotals(
            save=False, allocateAmounts={'total': -1*total_discount_amount}
        )

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
        kwargs['partnerRequiredRegs'] = self.partnerRequiredRegs
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
        self.request.session[REG_VALIDATION_STR]["invoice_expiry"] = \
            expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session.modified = True

        for er in self.partnerRequiredRegs:
            partner_data = {
                'firstName': form.cleaned_data.pop('er_%s_partner_firstName' % er.id),
                'lastName': form.cleaned_data.pop('er_%s_partner_lastName' % er.id)
            }

            customerId = form.cleaned_data.pop('er_%s_partner_customerId' % er.id, None)
            if not Customer.objects.filter(id=customerId).exists():
                customerId = None

            if customerId:
                partner_data['customerId'] = customerId

            er.data['partner'] = partner_data
            er.save()

        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST


class MultiRegCustomerNameView(RegistrationAdjustmentsMixin, FormView):
    '''
    This page collects additional name and email information needed when there
    are multiple EventRegistrations associated with an Invoice.  For each

    '''
    form_class = MultiRegCustomerNameForm
    template_name = 'core/multireg_customer_name_form.html'

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
                id=self.request.session[REG_VALIDATION_STR].get('invoice_id')
            )
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to sign-up form.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoice_expiry', ''),
        )
        if not expiry or expiry < timezone.now():
            clear_reg_cart(request)
            messages.info(request, _('Your registration session has expired. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        if self.invoice.status != Invoice.PaymentStatus.preliminary:
            messages.error(request, _('The current invoice has already been submitted. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        self.registration = Registration.objects.filter(
            invoice=self.invoice
        ).prefetch_related('eventregistration_set').first()

        self.multiReg = (
            self.registration and
            self.registration.eventregistration_set.filter(
                invoiceItem__parent_item__isnull=True
            ).count() > 1
        )

        if not self.registration or not self.multiReg:
            messages.error(request, _('Invalid registration passed to additional customer name form.'))
            return HttpResponseRedirect(reverse('registration'))

        self.partnerRequired = self.registration.eventregistration_set.filter(
            event__partnerRequired=True
        ).exists()

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        reg = self.registration

        payAtDoor = self.request.session[REG_VALIDATION_STR].get('payAtDoor', False)

        # Get a voucher ID to check from the current contents of the form
        voucherId = self.invoice.data.get('discount_code') or self.invoice.data.get('gift')

        discount_codes, total_discount_amount, voucherId = self.getDiscounts(
            self.invoice, registration=reg, voucher_code=voucherId
        )
        addons = self.getAddons(self.invoice, reg)

        # Update totals (without saving anything), so that taxes are
        # recalculated and the invoice handler knows how much to apply.
        items_queryset = self.invoice.updateTotals(
            save=False, allocateAmounts={'total': -1*total_discount_amount}
        )

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
        kwargs['multiReg'] = self.multiReg
        return kwargs

    def get_success_url(self):
        if self.partnerRequired:
            return reverse('partnerRequiredForm')
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
        self.request.session[REG_VALIDATION_STR]["invoice_expiry"] = \
            expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session.modified = True

        for er in self.registration.eventregistration_set.all():
            firstName = form.cleaned_data.pop('er_%s_firstName' % er.id)
            lastName = form.cleaned_data.pop('er_%s_lastName' % er.id)
            email = form.cleaned_data.pop('er_%s_email' % er.id)
            phone = form.cleaned_data.pop('er_%s_phone' % er.id, None)
            student = form.cleaned_data.pop('er_%s_student' % er.id, False)

            customer, created = Customer.objects.update_or_create(
                first_name=firstName, last_name=lastName,
                email=email, defaults={'phone': phone}
            )
            er.customer = customer
            er.student = student
            er.data.update(form.cleaned_data)
            er.save()

        # This signal allows vouchers to be applied temporarily, and it can
        # be used for other tasks.  It is sent here because it has not been
        # sent in the StudentInfoView if we got here.
        post_student_info.send(
            sender=StudentInfoView, invoice=self.invoice,
            registration=self.registration
        )
        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST


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
                id=self.request.session[REG_VALIDATION_STR].get('invoice_id')
            )
        except ObjectDoesNotExist:
            messages.error(request, _('Invalid invoice identifier passed to sign-up form.'))
            return HttpResponseRedirect(reverse('registration'))

        expiry = parse_datetime(
            self.request.session[REG_VALIDATION_STR].get('invoice_expiry', ''),
        )
        if not expiry or expiry < timezone.now():
            clear_reg_cart(request)
            messages.info(request, _('Your registration session has expired. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        if self.invoice.status != Invoice.PaymentStatus.preliminary:
            messages.error(request, _('The current invoice has already been submitted. Please try again.'))
            return HttpResponseRedirect(reverse('registration'))

        self.registration = Registration.objects.filter(
            invoice=self.invoice
        ).prefetch_related('eventregistration_set').first()

        multiRegRule = getConstant('registration__multiRegNameFormRule')

        self.multiReg = (
            self.registration and
            self.registration.eventregistration_set.filter(
                invoiceItem__parent_item__isnull=True
            ).count() > 1 and
            (
                multiRegRule == 'Y' or
                (multiRegRule == 'O' and not self.registration.payAtDoor)
            )
        )

        self.partnerRequired = (
            self.registration and
            self.registration.eventregistration_set.filter(
                event__partnerRequired=True
            ).exists()
        )

        # Ensure that session data is always updated when this view is called
        # so that passed voucher_ids are cleared.
        request.session.modified = True

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        reg = self.registration

        payAtDoor = self.request.session[REG_VALIDATION_STR].get('payAtDoor', False)

        # Get a voucher ID to check from the current contents of the form
        voucherId = getattr(context_data['form'].fields.get('gift'), 'initial', None)

        discount_codes, total_discount_amount, voucherId = self.getDiscounts(
            self.invoice, registration=reg, voucher_code=voucherId
        )
        addons = self.getAddons(self.invoice, reg)

        # Update totals (without saving anything), so that taxes are
        # recalculated and the invoice handler knows how much to apply.
        items_queryset = self.invoice.updateTotals(
            save=False, allocateAmounts={'total': -1*total_discount_amount}
        )

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
            'is_multiple_registration': self.multiReg,
        })

        return context_data

    def get_initial(self):
        ''' The initial value of the student field can be populated from session data. '''
        return {'student': self.request.session[REG_VALIDATION_STR].get('student', False)}

    def get_form_kwargs(self, **kwargs):
        ''' Pass along the request data to the form '''
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['request'] = self.request
        kwargs['registration'] = self.registration
        kwargs['invoice'] = self.invoice
        kwargs['multiReg'] = self.multiReg
        try:
            kwargs['add_more_url'] = reverse('registration')
        except NoReverseMatch:
            kwargs['add_more_url'] = None
        return kwargs

    def get_success_url(self):
        if self.multiReg:
            return reverse('multiRegNameInfo')
        elif self.partnerRequired:
            return reverse('partnerRequiredForm')
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
        self.request.session[REG_VALIDATION_STR]["invoice_expiry"] = \
            expiry.strftime('%Y-%m-%dT%H:%M:%S%z')
        self.request.session.modified = True

        # Notice that student and phone are not popped so that they go into the
        # Invoice data.
        firstName = form.cleaned_data.pop('firstName')
        lastName = form.cleaned_data.pop('lastName')
        email = form.cleaned_data.pop('email')
        phone = form.cleaned_data.get('phone', None)
        student = form.cleaned_data.get('student', False)

        reg = self.registration
        if reg:

            # Update the expiration date for this registration, and pass in the data from
            # this form.
            reg.comments = form.cleaned_data.pop('comments', None)
            reg.howHeardAboutUs = form.cleaned_data.pop('howHeardAboutUs', None)

            if not self.multiReg:
                customer, created = Customer.objects.update_or_create(
                    first_name=firstName, last_name=lastName,
                    email=email, defaults={'phone': phone}
                )
                reg.eventregistration_set.update(
                    customer=customer, student=student
                )

            invoice = reg.link_invoice(
                expirationDate=expiry, firstName=firstName, lastName=lastName,
                email=email, save=False
            )

            # Anything else in the form goes to the Invoice data.
            invoice.data.update(form.cleaned_data)
            invoice.save()
            reg.save()
        else:
            invoice = self.invoice

            if invoice.status == Invoice.PaymentStatus.preliminary:
                invoice.expirationDate = expiry

            invoice.firstName = firstName
            invoice.lastName = lastName
            invoice.email = email
            invoice.data.update(form.cleaned_data)
            invoice.save()

        # This signal allows vouchers to be applied temporarily, and it can
        # be used for other tasks.  We only send it here if we are not collecting
        # additional name information in the next step.
        if not self.multiReg:
            post_student_info.send(
                sender=StudentInfoView, invoice=invoice, registration=reg
            )
        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST
