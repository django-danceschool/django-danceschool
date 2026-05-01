from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Prefetch
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from allauth.account.signals import email_confirmed
from allauth.account.models import EmailAddress
from datetime import timedelta
import logging
import uuid

from .constants import getConstant
from .models import Event, EventRegistration, EventRole, Invoice, Registration, Series
from .serializers import EventSerializer
from .signals import (
    collect_purchasable_items, get_cart_invoice_related,
    get_cart_invoice_item_related, post_registration
)
from .utils.timezone import ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(get_cart_invoice_related, dispatch_uid='linkCartRegistration')
def linkCartRegistration(sender, **kwargs):
    '''
    If the cart contains any event items, ensure that a Registration object is
    linked to the invoice. Returns the Registration under the
    __relateditem_registration key so it is saved after the invoice itself.
    '''
    invoice = kwargs.get('invoice')
    item_data = kwargs.get('item_data', [])
    payAtDoor = kwargs.get('payAtDoor', False)

    if not isinstance(invoice, Invoice):
        return {
            'status': 'error',
            'errors': [{
                'code': 'no_invoice_passed',
                'message': _('No invoice passed to get_cart_invoice_related signal handler.')
            }]
        }

    # Only create a Registration if at least one item corresponds to an Event.
    event_ids = [x.get('item_id') for x in item_data if x.get('item_id')]
    if not Event.objects.filter(id__in=event_ids).exists():
        return {}

    try:
        reg = Registration.objects.get(invoice=invoice)
        if payAtDoor != reg.payAtDoor:
            reg.payAtDoor = payAtDoor
    except ObjectDoesNotExist:
        reg = Registration(
            invoice=invoice,
            submissionUser=invoice.submissionUser,
            dateTime=timezone.now(),
            payAtDoor=payAtDoor,
            data={},
            final=False,
        )

    return {'status': 'success', 'response': {'__relateditem_registration': reg}}


@receiver(get_cart_invoice_item_related, dispatch_uid='linkCartEventRegistration')
def linkCartEventRegistration(sender, **kwargs):
    '''
    For each event item in the cart, creates an EventRegistration linked to the
    InvoiceItem, enforcing rules on sold-out status, drop-ins, and duplicate
    registrations.
    '''
    item = kwargs.get('item')
    item_data = kwargs.get('item_data', {})
    cart_data = kwargs.get('cart_data', [])
    prior_response = kwargs.get('prior_response', {})
    purchasable_registry = kwargs.get('purchasable_registry', [])
    request = kwargs.get('request')

    item_id = item_data.get('item_id')
    sku = item_data.get('sku', '')
    cart_student = kwargs.get('cart_student', False)

    # Find the event in the purchasable registry (uses already-fetched querysets).
    this_event = None
    for qs, _serializer in purchasable_registry:
        if issubclass(qs.model, Event):
            try:
                this_event = qs.get(id=item_id)
            except ObjectDoesNotExist:
                pass
            break  # Only one Event queryset expected; stop after checking it.

    # Add-on events are not directly purchasable, so fall back for child items.
    if this_event is None and item_data.get('child_item'):
        try:
            this_event = Event.objects.get(id=item_id)
        except ObjectDoesNotExist:
            pass

    if this_event is None:
        return {}  # Not an event item; let other handlers process it.

    errors = []
    response = {'event': this_event.id, 'description': this_event.name}

    registration = prior_response.get('__relateditem_registration')
    if not registration:
        return {
            'status': 'error',
            'errors': [{'code': 'no_registration', 'message': _('No registration linked to this cart.')}]
        }

    is_dropin = bool(item_data.get('dropIn', False))

    # Resolve the parent event for allocated-total pricing.
    # Child add-on items reference their parent; for top-level items, parent == self.
    parent_event_id = item_data.get('parent_item_id') or item_id
    if parent_event_id == item_id:
        parent_event = this_event
    else:
        try:
            parent_event = Event.objects.get(id=parent_event_id)
        except ObjectDoesNotExist:
            return {
                'status': 'error',
                'errors': [{'code': 'invalid_parent_event', 'message': _('Invalid parent event ID.')}]
            }

    # Ensure a register_uuid is set on this item dict (modifying in-place so
    # subsequent iterations see the same uuid when checking child items).
    register_uuid = item_data.setdefault('register_uuid', str(uuid.uuid4()))
    response['register_uuid'] = register_uuid
    response['child_item'] = item_data.get('child_item', False)
    response['parent_item_id'] = item_data.get('parent_item_id', None)
    response['dropIn'] = is_dropin

    # Resolve the dance role from the SKU.  The numeric suffix is the
    # DanceRole id (role_id) — not the EventRole pk — so that the SKU format
    # is stable even when EventRole records do not exist for the event.
    this_role = None
    if '_ROLE_' in sku:
        try:
            role_id = int(sku.rsplit('_ROLE_', 1)[-1])
            try:
                # Prefer the EventRole when one exists (gives us capacity info).
                eventrole = EventRole.objects.get(role__id=role_id, event=this_event)
                this_role = eventrole.role
            except ObjectDoesNotExist:
                # No EventRole record (e.g. roles come from the DanceType);
                # look up the DanceRole directly.
                from .models import DanceRole
                this_role = DanceRole.objects.get(id=role_id)
            response.update({'roleId': role_id, 'roleName': this_role.name})
        except (ValueError, ObjectDoesNotExist):
            errors.append({'code': 'invalid_role', 'message': _('Invalid role specified.')})

    # Build child items for any add-on events (only for top-level items and only
    # if the child items are not already present in the cart from a prior run).
    if not item_data.get('child_item'):
        existing_children = [
            x for x in cart_data
            if x.get('register_uuid') == register_uuid and x.get('child_item')
        ]
        if not existing_children:
            child_items = []
            for addOn in this_event.eventaddon_set.all():
                addon_event = addOn.addOnEvent
                child_items.append({
                    'item_type': 'Event',
                    'item_id': addon_event.id,
                    'sku': 'EVENT_{}_GENERAL'.format(addon_event.id),
                    'quantity': 1,
                    'child_item': True,
                    'parent_item_id': item_id,
                    'register_uuid': register_uuid,
                })
            if child_items:
                response['child_items'] = child_items

    # Check for duplicate registrations for the same event AND role in this cart.
    # Only consider items that have already been processed (have a register_uuid
    # assigned), so we don't flag legitimate multi-role carts as duplicates.
    same_event_items = [
        x for x in cart_data
        if (
            x.get('item_id') == this_event.id and
            x.get('sku') == sku and
            x.get('register_uuid') not in (None, register_uuid)
        )
    ]
    if same_event_items:
        if not is_dropin:
            model_name = (
                this_event.polymorphic_ctype.model
                if hasattr(this_event, 'polymorphic_ctype') else ''
            )
            rule = (
                getConstant('registration__multiRegSeriesRule')
                if model_name == 'series'
                else getConstant('registration__multiRegPublicEventRule')
            )
            if rule == 'N' or (rule == 'D' and not registration.payAtDoor):
                errors.append({
                    'code': 'duplicate_event_%s' % this_event.id,
                    'message': _(
                        'You cannot register more than once for event: {event_name}. '
                        'Please remove the existing item from your cart and try again.'
                    ).format(event_name=this_event.name)
                })
        else:
            rule = getConstant('registration__multiRegDropInRule')
            if rule == 'N' or (rule == 'D' and not registration.payAtDoor):
                errors.append({
                    'code': 'duplicate_dropin_%s' % this_event.id,
                    'message': _(
                        'You cannot register more than once for event: {event_name}. '
                        'Please remove the existing item from your cart and try again.'
                    ).format(event_name=this_event.name)
                })

    # Check that registration is open.
    if not (
        this_event.registrationOpen or
        request.user.has_perm('core.override_register_closed')
    ):
        errors.append({
            'code': 'registration_closed',
            'message': _('Registration is closed for event {}.'.format(this_event.id))
        })

    # Validate drop-in eligibility.
    if not isinstance(this_event, Series) and is_dropin:
        errors.append({
            'code': 'invalid_dropin',
            'message': _('Cannot register as a drop-in for events that are not class series.')
        })
    elif is_dropin and (
        not request.user.has_perm('core.register_dropins') or
        (
            not this_event.allowDropins and
            not request.user.has_perm('core.override_register_dropins')
        )
    ):
        errors.append({
            'code': 'no_dropin_permission',
            'message': _('You are not permitted to register for drop-in classes.')
        })

    if errors:
        return {'status': 'error', 'errors': errors}

    # Since create_invoice_from_cart() deletes all existing invoice items before
    # the loop, the InvoiceItem is always unsaved here; always create fresh.
    this_eventreg = EventRegistration(
        event=this_event,
        invoiceItem=item,
        registration=registration,
        student=cart_student,
    )
    created_eventreg = True

    # Set pricing via allocated totals (handles multi-event price splits).
    allocated_totals = parent_event.getAllocatedTotals(payAtDoor=registration.payAtDoor)

    if is_dropin:
        this_eventreg.dropIn = True
        this_eventreg.role = this_role
        item.grossTotal = this_event.getBasePrice(dropIns=1)

        # Store the occurrence ID(s) so Registration.finalize() can link
        # this drop-in to the correct EventOccurrence.
        dropin_occurrence_id = item_data.get('dropInOccurrence')
        if dropin_occurrence_id:
            this_eventreg.data['__dropInOccurrences'] = [dropin_occurrence_id]

        # Replicate the door check-in logic from create_event_registration.
        checkin_rule = getConstant('registration__doorCheckInRule')
        if registration.payAtDoor and checkin_rule == 'E':
            this_eventreg.data['__checkInEvent'] = True
        elif registration.payAtDoor and checkin_rule == 'O' and dropin_occurrence_id:
            best_occ = this_event.eventoccurrence_set.filter(
                id=dropin_occurrence_id,
                startTime__gte=ensure_localtime(timezone.now()) - timedelta(minutes=45)
            ).first()
            this_eventreg.data['__checkInOccurrence'] = getattr(best_occ, 'id', None)
        elif registration.payAtDoor and checkin_rule == 'O':
            this_eventreg.data['__checkInOccurrence'] = getattr(
                this_event.getNextOccurrence(
                    ensure_localtime(timezone.now()) - timedelta(minutes=45)
                ),
                'id',
                None
            )
    else:
        this_eventreg.dropIn = False
        this_eventreg.role = this_role
        if item_data.get('child_item', False):
            item.grossTotal = this_event.getBasePrice(payAtDoor=registration.payAtDoor)
            response['__displayTotal'] = item.grossTotal
        else:
            item.grossTotal = allocated_totals.get(
                this_event.id,
                this_event.getBasePrice(payAtDoor=registration.payAtDoor)
            )
            response['__displayTotal'] = sum(allocated_totals.values())
        item.data['_initial_total'] = allocated_totals.get(this_event.id, item.grossTotal)

    item.total = item.data.get('_initial_total', item.grossTotal)
    if isinstance(this_event, Series):
        item.taxRate = getConstant('registration__seriesSalesTaxRate') or 0
    else:
        item.taxRate = getConstant('registration__publicEventSalesTaxRate') or 0
    item.calculateTaxes()
    item.description = this_event.name

    # Check sold-out (only for newly created registrations).
    if (
        created_eventreg and this_event.soldOut and
        not request.user.has_perm('core.override_register_soldout')
    ):
        errors.append({
            'code': 'sold_out',
            'message': _('Event {} is sold out.'.format(this_event.id))
        })

    if (
        created_eventreg and
        this_role is not None and
        this_event.soldOutForRole(this_role, includeTemporaryRegs=True) and
        not request.user.has_perm('core.override_register_soldout')
    ):
        errors.append({
            'code': 'sold_out_role',
            'message': _('Event {} is sold out for role {}.'.format(this_event.id, this_role))
        })

    if errors:
        return {'status': 'failure', 'errors': errors}

    response['__relateditem_eventregistration'] = this_eventreg
    return {'status': 'success', 'response': response}


@receiver(collect_purchasable_items)
def event_purchasables(sender, **kwargs):
    qs = (
        Event.objects.prefetch_related(
            Prefetch('eventrole_set', queryset=EventRole.objects.filter(capacity__gt=0))
        )
    )
    return (qs, EventSerializer)


@receiver(email_confirmed)
def linkUserToMostRecentCustomer(sender, **kwargs):
    '''
    If a new primary email address has just been confirmed, check if the user
    associated with that email has an associated customer object yet.  If not,
    then look for the customer with that email address who most recently
    registered for something and that is not associated with another user.
    Automatically associate the User with with Customer, and if missing, fill in
    the user's name information with the Customer's name.  This way, when a new
    or existing customer creates a user account, they are seamlessly linked to
    their most recent existing registration at the time they verify their email
    address.
    '''
    email_address = kwargs.get('email_address', None)

    if not email_address or not email_address.primary or not email_address.verified:
        return

    user = email_address.user

    if not hasattr(user, 'customer'):
        last_reg = EventRegistration.objects.filter(
            customer__email=email_address.email,
            customer__user__isnull=True,
            registration__dateTime__isnull=False,
            registration__final=True
        ).order_by('-registration__dateTime').first()

        if last_reg:
            customer = last_reg.customer
            customer.user = user
            customer.save()

            if not user.first_name and not user.last_name:
                user.first_name = customer.first_name
                user.last_name = customer.last_name
                user.save()


@receiver(post_registration)
def linkCustomerToVerifiedUser(sender, **kwargs):
    """
    If a Registration is processed in which the associated Customer does not yet
    have a User, then check to see if the Customer's email address has been
    verified as belonging to a specific User, and if that User has an associated
    Customer.  If such a User is found, then associated this Customer with that
    User.  This way, if a new User verifies their email account before they have
    submitted any Registrations, their Customer account is seamlessly linked when
    they do complete their first Registration.
    """
    invoice = kwargs.get('invoice', None)
    eventregs = EventRegistration.objects.filter(
        invoiceItem__invoice=invoice, customer__isnull=False,
        customer__user__isnull=True
    )
    
    if not eventregs:
        return

    logger.debug('Checking for User for Customer with no associated registration.')

    for er in eventregs:
        customer = er.customer

        try:
            verified_email = EmailAddress.objects.get(
                email=customer.email,
                verified=True,
                primary=True,
                user__customer__isnull=True
            )

            logger.info("Found user %s to associate with customer %s.", verified_email.user.id, customer.id)

            customer.user = verified_email.user
            customer.save()

            if not customer.user.first_name and not customer.user.last_name:
                customer.user.first_name = customer.first_name
                customer.user.last_name = customer.last_name
                customer.user.save()
        except ObjectDoesNotExist:
            logger.info("No user found to associate with customer %s.", customer.id)
        except MultipleObjectsReturned:
            # This should never happen, as email should be unique in the db table account_emailaddress.
            # If it does, something's broken in the database or Django.
            errmsg = "Something's not right with the database: more than one entry found on the database for the email %s. \
                This duplicate key value violates unique constraint \"account_emailaddress_email_key\". \
                The email field should be unique for each account.\n"
            logger.exception(errmsg, customer.email)


@receiver(post_save, sender='core.EventOccurrence')
@receiver(post_delete, sender='core.EventOccurrence')
def reschedule_tasks_on_occurrence_change(sender, instance, **kwargs):
    """
    When an EventOccurrence is saved or deleted, the parent event's
    close task ETA may have changed (since it's based on startTime of
    the first occurrence). Trigger a reschedule on the parent event.
    """
    event = instance.event
    if event and event.pk:
        # Use .update() to trigger the scheduling logic without a full
        # model save cycle — but we do need scheduleRegistrationTasks()
        logger.debug(
            'EventOccurrence changed for event %s — rescheduling registration tasks.',
            event.pk
        )
        # Refresh from DB to get current occurrence times reflected
        event.refresh_from_db()
        event.scheduleRegistrationTasks()
