from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum, F, Case, When, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.apps import apps
from datetime import timedelta
import logging

from ..constants import getConstant
from ..helpers import getSiteUrl
from ..signals import post_registration
from ..mixins import EmailRecipientMixin
from .invoices import Invoice, InvoiceItem
from .event_base import Event
from .event_occurrences import EventOccurrence
from .customers import Customer
from .event_roles import DanceRole

logger = logging.getLogger(__name__)


class Registration(EmailRecipientMixin, models.Model):
    '''
    There is a single registration for an online transaction.
    A single Registration includes multiple classes, as well as events.
    '''

    final = models.BooleanField(_('Registration has been finalized'), default=False)

    howHeardAboutUs = models.TextField(
        _('How they heard about us'), default='', blank=True, null=True
    )
    payAtDoor = models.BooleanField(_('At-the-door registration'), default=False)

    comments = models.TextField(_('Comments'), default='', blank=True, null=True)

    invoice = models.OneToOneField(
        Invoice, verbose_name=_('Invoice'),
        related_name='registration',
        on_delete=models.CASCADE
    )

    dateTime = models.DateTimeField(blank=True, null=True, verbose_name=_('Registration date/time'))

    submissionUser = models.ForeignKey(
        User, verbose_name=_('registered by user'),
        related_name='submittedregistrations', null=True, blank=True,
        on_delete=models.SET_NULL
    )

    # This field allows hooked in registration-related procedures to hang on to
    # miscellaneous data for the duration of the registration process without
    # having to create models in another app.  By default (and for security
    # reasons), the registration system ignores any passed data that it does not
    # expect, so you will need to hook into the registration system to ensure
    # that any extra information that you want to use is not discarded.
    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    @property
    def invoiceDetails(self):
        '''
        Return aggregates that split out totals associated with this
        registration as well as other non-registration items
        '''

        return self.invoice.invoiceitem_set.annotate(
            from_reg=Case(
                When(eventRegistration__registration__id=self.id, then=Value(1.0)),
                default=Value(0.0), output_field=models.FloatField()
            ),
        ).aggregate(
            reg_grossTotal=Coalesce(Sum(F('grossTotal')*F('from_reg')), 0, output_field=models.FloatField()),
            reg_total=Coalesce(Sum(F('total')*F('from_reg')), 0, output_field=models.FloatField()),
            reg_adjustments=Coalesce(Sum(F('adjustments')*F('from_reg')), 0, output_field=models.FloatField()),
            reg_taxes=Coalesce(Sum(F('taxes')*F('from_reg')), 0, output_field=models.FloatField()),
            reg_fees=Coalesce(Sum(F('fees')*F('from_reg')), 0, output_field=models.FloatField()),
            other_grossTotal=Coalesce(Sum(F('grossTotal')*(1 - F('from_reg'))), 0, output_field=models.FloatField()),
            other_total=Coalesce(Sum(F('total')*(1 - F('from_reg'))), 0, output_field=models.FloatField()),
            other_adjustments=Coalesce(Sum(F('adjustments')*(1 - F('from_reg'))), 0, output_field=models.FloatField()),
            other_taxes=Coalesce(Sum(F('taxes')*(1 - F('from_reg'))), 0, output_field=models.FloatField()),
            other_fees=Coalesce(Sum(F('fees')*(1 - F('from_reg'))), 0, output_field=models.FloatField()),
            grossTotal=Coalesce(Sum(F('grossTotal')), 0, output_field=models.FloatField()),
            total=Coalesce(Sum(F('total')), 0, output_field=models.FloatField()),
            adjustments=Coalesce(Sum(F('adjustments')), 0, output_field=models.FloatField()),
            taxes=Coalesce(Sum(F('taxes')), 0, output_field=models.FloatField()),
            fees=Coalesce(Sum(F('fees')), 0, output_field=models.FloatField()),
        )

    @property
    def discounted(self):
        details = self.invoiceDetails
        return details['reg_grossTotal'] != details['reg_total']
    discounted.fget.short_description = _('Is discounted')

    @property
    def grossTotal(self):
        '''
        Return just the portion of the invoice grossTotal associated with this
        registration.
        '''
        details = self.invoiceDetails
        return details['reg_grossTotal']
    grossTotal.fget.short_description = _('Total before discounts')

    @property
    def total(self):
        '''
        Return just the portion of the invoice total associated with this
        registration.
        '''
        details = self.invoiceDetails
        return details['reg_total']
    total.fget.short_description = _('Total billed amount')

    @property
    def adjustments(self):
        '''
        Return just the portion of the invoice adjustments associated with this
        registration.
        '''
        details = self.invoiceDetails
        return details['reg_adjustments']
    adjustments.fget.short_description = _('Refunds/adjustments')

    @property
    def taxes(self):
        '''
        Return just the portion of the invoice adjustments associated with this
        registration.
        '''
        details = self.invoiceDetails
        return details['reg_adjustments']
    taxes.fget.short_description = _('Taxes')

    @property
    def fees(self):
        '''
        Return just the portion of the invoice fees associated with this
        registration.
        '''
        details = self.invoiceDetails
        return details['reg_fees']
    fees.fget.short_description = _('Processing fees')

    @property
    def firstStartTime(self):
        return min([x.event.startTime for x in self.eventregistration_set.all()])
    firstStartTime.fget.short_description = _('First event starts')

    @property
    def firstSeriesStartTime(self):
        return min([
            x.event.startTime for x in
            self.eventregistration_set.filter(event__series__isnull=False)
        ])
    firstSeriesStartTime.fget.short_description = _('First class series starts')

    @property
    def lastEndTime(self):
        return max([x.event.endTime for x in self.eventregistration_set.all()])
    lastEndTime.fget.short_description = _('Last event ends')

    @property
    def lastSeriesEndTime(self):
        return max([
            x.event.endTime for x in
            self.eventregistration_set.filter(event__series__isnull=False)
        ])
    lastSeriesEndTime.fget.short_description = _('Last class series ends')

    @property
    def warningFlag(self):
        '''
        When viewing individual event registrations, there are a large number of potential
        issues that can arise that may warrant scrutiny. This property just checks all of
        these conditions and indicates if anything is amiss so that the template need not
        check each of these conditions individually repeatedly.
        '''
        if not hasattr(self, 'invoice'):
            return True

        if apps.is_installed('danceschool.financial'):
            '''
            If the financial app is installed, then we can also check additional
            properties set by that app to ensure that there are no inconsistencies
            '''
            if self.invoice.revenueNotYetReceived != 0 or self.invoice.revenueMismatch:
                return True
        return (
            self.invoice.itemTotalMismatch or self.invoice.unpaid or
            self.invoice.outstandingBalance != 0
        )
    warningFlag.fget.short_description = _('Issue with event registration')

    @property
    def refundFlag(self):
        if (
            not hasattr(self, 'invoice') or
            self.invoice.adjustments != 0 or
            (apps.is_installed('danceschool.financial') and self.invoice.revenueRefundsReported != 0)
        ):
            return True
        return False
    refundFlag.fget.short_description = _('Transaction was partially refunded')

    @property
    def url(self):
        if self.id:
            return reverse('admin:core_registration_change', args=[self.id, ])
    url.fget.short_description = _('Reg. Admin URL')

    def getTimeOfClassesRemaining(self, numClasses=0):
        '''
        For checking things like prerequisites, it's useful to check if a
        requirement is 'almost' met
        '''
        occurrences = EventOccurrence.objects.filter(
            cancelled=False,
            event__in=[
                x.event for x in self.eventregistration_set.filter(
                    event__series__isnull=False
                )
            ],
        ).order_by('-endTime')
        if occurrences.count() > numClasses:
            return occurrences[numClasses].endTime
        else:
            return occurrences.last().startTime

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [
            x.customer.email for x in self.eventregistration_set.filter(
                cancelled=False,
                customer__isnull=False,
            )
        ]

    def get_email_context(self, from_invoice=True, **kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super().get_email_context(**kwargs)
        if not from_invoice:
            context.update(self.invoice.get_email_context())

        context.update({
            'checkin_url': '%s%s' % (
                getSiteUrl(),
                reverse(
                    'customer_checkin_validated',
                    args=(self.invoice.id, self.invoice.validationString)
                ),
            ),
            'qrcode_url': '%s%s' % (
                getSiteUrl(),
                reverse(
                    'customer_qrcode_validated',
                    args=(self.invoice.id, self.invoice.validationString)
                ),
            ),
            'registrationComments': self.comments,
            'registrationHowHeardAboutUs': self.howHeardAboutUs,
        })
        return context

    def link_invoice(self, update=True, save=True, **kwargs):
        '''
        If an invoice does not already exist for this registration,
        then create one.  If an update is requested, then ensure that all
        details of the invoice match the registration.
        Return the linked invoice.
        '''

        submissionUser = kwargs.pop('submissionUser', None)
        collectedByUser = kwargs.pop('collectedByUser', None)
        status = kwargs.pop('status', None)
        expirationDate = kwargs.pop('expirationDate', None)
        default_expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))


        if not getattr(self, 'invoice', None):

            invoice_kwargs = {
                'firstName': kwargs.pop('firstName', None),
                'lastName': kwargs.pop('lastName', None),
                'email': kwargs.pop('email', None),
                'grossTotal': kwargs.pop('grossTotal', 0),
                'total': kwargs.pop('total', 0),
                'taxes': kwargs.pop('taxes', 0),
                'submissionUser': submissionUser,
                'collectedByUser': collectedByUser,
                'buyerPaysSalesTax': getConstant('registration__buyerPaysSalesTax'),
                'data': kwargs,
            }

            if (
                (not status or status == Invoice.PaymentStatus.preliminary) and
                (not self.final)
            ):
                invoice_kwargs.update({
                    'status': Invoice.PaymentStatus.preliminary,
                    'expirationDate': expirationDate or default_expiry
                })
            elif not status:
                invoice_kwargs.update({
                    'status': Invoice.PaymentStatus.unpaid,
                })

            new_invoice = Invoice(**invoice_kwargs)
            new_invoice.save()
            self.invoice = new_invoice
        elif update:
            needs_update = False

            invoice_details = self.invoiceDetails

            for key in ['firstName', 'lastName', 'email']:
                if kwargs.get(key, None) and getattr(self.invoice, key) != kwargs.get(key):
                    setattr(self.invoice, key, kwargs.get(key))
                    needs_update = True

            if status and status != self.invoice.status:
                self.invoice.status = status
                needs_update = True
            if (
                kwargs.get('grossTotal', None) and kwargs.get('total', None) and (
                    self.invoice.grossTotal != (
                        kwargs.get('grossTotal') +
                        invoice_details.get('other_grossTotal',0)
                    ) or
                    self.invoice.total != (
                        kwargs.get('total') +
                        invoice_details.get('other_total', 0)
                    )
                )
            ):
                self.invoice.grossTotal = kwargs.get('grossTotal') + invoice_details.get('other_grossTotal', 0)
                self.invoice.total = kwargs.get('total') + invoice_details.get('other_total', 0)
                needs_update = True

            if (
                expirationDate and expirationDate != self.invoice.expirationDate
                and self.invoice.status == Invoice.PaymentStatus.preliminary
            ):
                self.invoice.expirationDate = expirationDate
                needs_update = True
            elif self.invoice.status != Invoice.PaymentStatus.preliminary:
                self.invoice.expirationDate = None
                needs_update = True

            if needs_update and save:
                self.invoice.save()

        return self.invoice

    def finalize(self, **kwargs):
        '''
        This method is called when the payment process has been completed and a registration
        is ready to be finalized.  It also fires the post-registration signal
        '''
        if self.final:
            return self

        dateTime = kwargs.pop('dateTime', timezone.now())

        self.final = True
        self.save()
        logger.debug('Finalized registration {}'.format(self.id))

        # Check EventRegistration data for indicators that this person should be
        # checked into an EventOccurrence or an Event, or that we should track
        # them as having dropped into a specific occurrence.
        for er in self.eventregistration_set.all():
            checkInOccurrence = er.data.pop('__checkInOccurrence', None)
            dropInOccurrences = er.data.pop('__dropInOccurrences', None)
            checkInEvent = er.data.pop('__checkInEvent', None)

            if isinstance(dropInOccurrences, list):
                to_apply = EventOccurrence.objects.filter(
                    event=er.event, id__in=dropInOccurrences
                )
                for this_occ in to_apply:
                    er.occurrences.add(this_occ)

            if checkInEvent or checkInOccurrence:
                from .event_checkins import EventCheckIn
                checkInType = 'O' if checkInOccurrence else 'E'
                EventCheckIn.objects.create(
                    event=er.event, checkInType=checkInType,
                    occurrence=EventOccurrence.objects.filter(id=checkInOccurrence).first(),
                    eventRegistration=er, cancelled=False,
                    firstName=getattr(er.customer, 'firstName', None),
                    lastName=getattr(er.customer, 'lastName', None),
                    submissionUser=er.registration.submissionUser
                )

            if (
                checkInOccurrence is not None or
                dropInOccurrences is not None or
                checkInEvent is not None
            ):
                er.save()

        # This signal can, for example, be caught by the discounts app to keep
        # track of any discounts that were applied
        post_registration.send(
            sender=Registration,
            invoice=self.invoice,
            registration=self
        )

        # Return the finalized registration
        return self

    def save(self, *args, **kwargs):
        '''
        Before saving this registration, ensure that an associated invoice
        exists.  If an invoice already exists, then update the invoice if
        anything requires updating.
        '''
        link_kwargs = {
            'submissionUser': kwargs.pop('submissionUser', None),
            'collectedByUser': kwargs.pop('collectedByUser', None),
            'status': kwargs.pop('status', None),
            'expirationDate': kwargs.pop('expirationDate', None),
            'update': kwargs.pop('updateInvoice', True),
        }

        self.invoice = self.link_invoice(**link_kwargs)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.dateTime and getattr(self.invoice, 'fullName', None):
            return '%s #%s: %s, %s' % (
                _('Registration'), self.id, self.invoice.fullName,
                self.dateTime.strftime('%b. %Y')
            )
        elif self.dateTime or getattr(self.invoice, 'fullName', None):
            x = self.dateTime or getattr(self.invoice, 'fullName', '')
            return '%s #%s: %s' % (_('Registration'), self.id, x)
        else:
            return '%s #%s' % (_('Registration'), self.id)

    class Meta:
        ordering = ('-dateTime',)
        verbose_name = _('Registration')
        verbose_name_plural = _('Registrations')

        permissions = (
            (
                'view_registration_summary',
                _('Can access the series-level registration summary view')
            ),
            ('checkin_customers', _('Can check-in customers using the summary view')),
            ('accept_door_payments', _('Can process door payments in the registration system')),
            ('register_dropins', _('Can register students for drop-ins.')),
            (
                'override_register_closed',
                _('Can register students for series/events that are closed for registration by the public')
            ),
            (
                'override_register_soldout',
                _('Can register students for series/events that are officially sold out')
            ),
            (
                'override_register_dropins',
                _(
                    'Can register students for drop-ins even if the series ' +
                    'does not allow drop-in registration.'
                )
            ),
            (
                'ajax_registration',
                _('Can register using the Ajax registration view (needed for the door register)')
            ),
        )


class EventRegistration(EmailRecipientMixin, models.Model):
    '''
    An EventRegistration is associated with a Registration and records
    a registration for a single event.
    '''

    registration = models.ForeignKey(
        Registration, verbose_name=_('Registration'), on_delete=models.CASCADE
    )

    invoiceItem = models.OneToOneField(
        InvoiceItem, verbose_name=_('Invoice item'),
        related_name='eventRegistration',
        on_delete=models.CASCADE
    )

    event = models.ForeignKey(Event, verbose_name=_('Event'), on_delete=models.CASCADE)
    occurrences = models.ManyToManyField(
        EventOccurrence, blank=True,
        verbose_name=_('Applicable event occurrences (for drop-ins only)')
    )

    customer = models.ForeignKey(
        Customer, verbose_name=_('Customer'), null=True, on_delete=models.SET_NULL
    )

    role = models.ForeignKey(
        DanceRole, null=True, blank=True, verbose_name=_('Dance role'), on_delete=models.SET_NULL
    )

    dropIn = models.BooleanField(
        _('Drop-in registration'), default=False,
        help_text=_('If true, this is a drop-in registration.')
    )

    cancelled = models.BooleanField(
        _('Cancelled'), default=False,
        help_text=_(
            'Mark as cancelled so that this registration is not counted in ' +
            'student/attendee counts.'
        )
    )

    student = models.BooleanField(_('Eligible for student discount'), default=False)

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    @property
    def discounted(self):
        return (
            getattr(self.invoiceItem, 'grossTotal', 0) !=
            getattr(self.invoiceItem, 'total', 0)
        )
    discounted.fget.short_description = _('Is discounted')

    @property
    def warningFlag(self):
        '''
        When viewing individual event registrations, there are a large number of potential
        issues that can arise that may warrant scrutiny. This property just checks all of
        these conditions and indicates if anything is amiss so that the template need not
        check each of these conditions individually repeatedly.
        '''
        if not hasattr(self, 'invoiceItem'):
            return True
        if apps.is_installed('danceschool.financial'):
            '''
            If the financial app is installed, then we can also check additional
            properties set by that app to ensure that there are no inconsistencies
            '''
            if self.invoiceItem.revenueNotYetReceived != 0 or self.invoiceItem.revenueMismatch:
                return True
        return (
            self.invoiceItem.invoice.unpaid or self.invoiceItem.invoice.outstandingBalance != 0
        )
    warningFlag.fget.short_description = _('Issue with event registration')

    @property
    def refundFlag(self):
        if (
            not hasattr(self, 'invoiceItem') or
            self.invoiceItem.invoice.adjustments != 0 or
            (
                apps.is_installed('danceschool.financial') and
                self.invoiceItem.revenueRefundsReported != 0
            )
        ):
            return True
        return False
    refundFlag.fget.short_description = _('Transaction was partially refunded')

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        this_email = getattr(self.customer, 'email', None)
        return [this_email, ] if this_email else []

    def get_email_context(self, **kwargs):
        ''' Overrides EmailRecipientMixin '''

        includeName = kwargs.pop('includeName', True)
        includeEvent = kwargs.pop('includeEvent', True)
        context = super().get_email_context(**kwargs)

        context.update({
            'dropIn': self.dropIn,
            'role': getattr(self.role, 'name', None),
        })

        if includeName:
            context.update({
                'first_name': self.firstName,
                'last_name': self.lastName,
            })

        if includeEvent:
            context['event'] = self.event.get_email_context()

        return context

    def checkedIn(self, occurrence=None, date=None, checkInType='O'):
        '''
        Returns an indicator of whether this EventRegistration has been checked
        in, either for a specified EventOccurrence,
        '''
        filters = Q(cancelled=False) & Q(checkInType=checkInType)

        if occurrence and checkInType == 'O':
            filters &= Q(occurrence=occurrence)
        elif date and checkInType == 'O':
            filters &= Q(occurrence=self.event.getNextOccurrenceForDate(date=date))

        return self.eventcheckin_set.filter(filters).exists()

    def link_invoice_item(self, **kwargs):
        '''
        If an invoice item does not already exist for this event registration,
        then create one.  Return the linked invoice item.
        '''
        from .event_types import Series

        invoice = getattr(self.registration, 'invoice', None)

        if not isinstance(invoice, Invoice):
            raise ValidationError(_(
                'Cannot link invoice item for event registration: ' +
                'No associated registration, or registration has no invoice.'
            ))
        elif (
            getattr(self, 'invoiceItem', None) and
            getattr(self.invoiceItem, 'invoice', None) != invoice
        ):
            raise ValidationError(
                _('Existing invoice item not associated with passed invoice.')
            )

        grossTotal = kwargs.pop('grossTotal', None)
        total = kwargs.pop('total', None)

        if not getattr(self, 'invoiceItem', None):

            if grossTotal is None:
                grossTotal = self.event.getBasePrice(**kwargs)
            if total is None:
                total = grossTotal

            if isinstance(self.event, Series):
                _tax_rate = getConstant('registration__seriesSalesTaxRate') or 0
            else:
                _tax_rate = getConstant('registration__publicEventSalesTaxRate') or 0

            new_item = InvoiceItem(
                invoice=invoice, fees=0, grossTotal=grossTotal, total=total,
                taxRate=_tax_rate
            )

            # Attach the new invoice item to its parent if the event registration
            # id associated with the parent has been passed.
            parent_id = kwargs.pop('parent_id', None)
            if parent_id:
                new_item.parent_item = EventRegistration.objects.get(id=parent_id).invoiceItem

            # If there are no items but already fees, apply those
            # fees to this item.
            if invoice.grossTotal == 0 and invoice.fees:
                new_item.fees = invoice.fees

            # The Invoice's updateTotals method needs to be able to revert the invoice
            # and its items back to a 'clean' state in order to re-apply discounts
            # and avoid applying them twice through back button behavior, etc.
            # It looks for this initial_total key, and if it finds it, then it uses
            # that as the reset point. Otherwise, it automatically uses the grossTotal
            # line as the reset point.
            if total != grossTotal:
                new_item.data['_initial_total'] = total

            new_item.calculateTaxes()
            new_item.save(updateInvoiceTotals=False)
            self.invoiceItem = new_item

        return self.invoiceItem

    def save(self, *args, **kwargs):
        '''
        Before saving, create an invoice item for this registration if one does
        not already exist.  To avoid duplicate calls to link_invoice_item(),
        eligible kwargs used by that method can be passed as save method kwargs.
        '''
        link_kwargs = {
            'grossTotal': kwargs.pop('grossTotal', None),
            'total': kwargs.pop('total', None),
            'parent_id': kwargs.pop('parent_id', None),
            'payAtDoor': kwargs.pop('payAtDoor', False),
            'dropIns': kwargs.pop('dropIns', 0),
        }

        self.invoiceItem = self.link_invoice_item(**link_kwargs)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        '''
        Only allow EventRegistrations to be deleted if the Registration is not
        final and the invoice allows items to be edited.  If so, then also
        delete the associated InvoiceItem to this EventRegistration.  Otherwise,
        set the status to cancelled, but do not delete.
        '''
        if (
            getattr(self.registration, 'final', False) or not
            self.invoiceItem.invoice.itemsEditable
        ):
            self.cancelled = True
            self.save()
        else:
            invoiceItem = self.invoiceItem
            super().delete(*args, **kwargs)
            if invoiceItem:
                invoiceItem.delete()

    def __str__(self):
        return str(self.customer) + " " + str(self.event)

    class Meta:
        verbose_name = _('Event registration')
        verbose_name_plural = _('Event registrations')
