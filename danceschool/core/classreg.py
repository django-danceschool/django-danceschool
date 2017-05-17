from django.core.urlresolvers import reverse
from django.conf import settings
from django.http import HttpResponseServerError, HttpResponseRedirect
from django.views.generic import FormView
from django.utils.translation import ugettext_lazy as _

from datetime import datetime
import json
from braces.views import UserFormKwargsMixin
from cms.models import Page
import logging
from allauth.account.forms import LoginForm, SignupForm

from .helpers import emailErrorMessage
from .models import Event, Registration, EventRegistration, TemporaryRegistration, TemporaryEventRegistration, EmailTemplate, DanceRole, Customer
from .forms import RegistrationContactForm, DoorAmountForm
from .constants import getConstant, REG_VALIDATION_STR
from .emails import renderEmail
from .signals import invoice_sent, pre_temporary_registration, post_temporary_registration, request_discounts, apply_discount, apply_addons, apply_price_adjustments, post_registration, get_payment_context
from .mixins import FinancialContextMixin


# Define logger for this file
logger = logging.getLogger(__name__)


def createTemporaryRegistration(request):

    # first get reg info
    regSession = request.session.get(REG_VALIDATION_STR,{})
    formData = regSession.pop('infoFormData',{})
    if not regSession or not formData:
        return HttpResponseServerError(_("Error: No registration information provided."))

    pre_temporary_registration.send(sender=createTemporaryRegistration,data=regSession)

    firstName = formData.pop("firstName")
    lastName = formData.pop("lastName")
    email = formData.pop("email")
    phone = formData.pop("phone",None)
    student = formData.pop("student",False)
    comments = formData.pop("comments",None)
    howHeardAboutUs = formData.pop('howHeardAboutUs',None)

    payAtDoor = regSession.get('payAtDoor',False)
    marketing_id = regSession.get('marketing_id',None)

    # Include the submission use if the user is authenticated
    if request.user.is_authenticated:
        submissionUser = request.user
    else:
        submissionUser = None

    # get the list of events for which to create registrations
    eventids = regSession['regInfo'].get('events',None)
    eventset = Event.objects.filter(id__in=eventids.keys())

    # create registration
    reg = TemporaryRegistration(firstName=firstName,lastName=lastName,
                                email=email,howHeardAboutUs=howHeardAboutUs,
                                student=student,comments=comments,submissionUser=submissionUser,
                                phone=phone,payAtDoor=payAtDoor,dateTime=datetime.now())

    # Automatically place the marketing ID and any other information that was submitted in the student
    # form into the JSON data. If a handler of the pre_temporary_registration signal does not desire
    # this behavior, then it should pop the appropriate key from the session data.
    regExtraData = {}
    if marketing_id:
        regExtraData['marketing_id'] = marketing_id
    regExtraData.update(formData)

    if regExtraData:
        reg.data = regExtraData

    # Construct the list of TemporaryEventRegistration objects to be saved.
    eventRegs = []
    grossPrice = 0

    for event_id,regvalue in eventids.items():
        event = eventset.get(id=event_id)

        dropInList = [int(k.split("_")[-1]) for k,v in regvalue.items() if k.startswith('dropin_') and v is True]

        # The 'register' key is required to be passed.
        registered = regvalue.get('register',False)
        if not registered:
            continue

        # If a valid role is specified then it is passed along.
        this_role_id = regvalue.get('role',None)
        this_role = None
        if this_role_id:
            try:
                this_role = DanceRole.objects.get(id=this_role_id)
            except:
                pass

        logger.debug('Creating temporary event registration for:' + str(event_id))
        if len(dropInList) > 0:
            tr = TemporaryEventRegistration(dropIn=True, price=event.getBasePrice(dropIns=len(dropInList)), event=event)
        else:
            tr = TemporaryEventRegistration(price=event.getBasePrice(isStudent=student,payAtDoor=payAtDoor), event=event, role=this_role)

        # If it's possible to store additional data and such data exist, then store them.
        tr.data = regvalue

        eventRegs.append(tr)
        grossPrice += tr.price

    # If we got this far with no issues, then save
    reg.priceWithDiscount = grossPrice
    reg.save()
    for er in eventRegs:
        er.registration = reg
        er.save()

    # This signal allows (for example) vouchers to be applied
    post_temporary_registration.send(
        sender=createTemporaryRegistration,
        data=regSession,
        registration=reg,
    )

    return reg


def processPayment(mc_gross,mc_fee,payment_status,reg,checkAmount=True,paidOnline=True,submissionUser=None,collectedByUser=None,invoiceNumber=None):
    '''
    Process a payment (Paypal or cash) and proceed to sending the confirmation email.
    '''
    epsilon = .01

    logger.info('Processing payment and creating registration objects.')

    # if the prices don't match, email an error message
    if abs(reg.priceWithDiscount - float(mc_gross)) > epsilon and checkAmount:
        emailErrorMessage(_('payment mismatch'),
                          _('Payments didnt match for reg %s, received: %s, expected: %s' % (reg.id, mc_gross, reg.priceWithDiscount)))
        return

    # make sure the payment is completed and record the payment
    if payment_status == "Completed":

        customer, created = Customer.objects.get_or_create(first_name=reg.firstName,last_name=reg.lastName,email=reg.email,defaults={'phone': reg.phone})

        realreg = Registration(customer=customer,
                               comments=reg.comments,howHeardAboutUs=reg.howHeardAboutUs,
                               student=reg.student,processingFee=mc_fee,amountPaid=mc_gross,
                               priceWithDiscount=reg.priceWithDiscount,
                               paidOnline=paidOnline,
                               dateTime=reg.dateTime,
                               submissionUser=submissionUser or reg.submissionUser,
                               collectedByUser=collectedByUser,
                               temporaryRegistration=reg,
                               invoiceNumber=invoiceNumber,
                               data=reg.data,
                               )

        realreg.save()
        logger.debug('Created registration with id: ' + str(realreg.id))

        for er in reg.temporaryeventregistration_set.all():
            logger.debug('Creating eventreg for event: ' + str(er.event.id))
            realer = EventRegistration(registration=realreg,event=er.event,
                                       customer=customer,role=er.role,
                                       price=er.price,
                                       dropIn=er.dropIn,
                                       data=er.data
                                       )
            realer.save()

        # This signal can, for example, be caught by the vouchers app to keep track of any vouchers
        # that were applied
        post_registration.send(
            sender=processPayment,
            registration=realreg
        )

        if getConstant('email__disableSiteEmails'):
            logger.info('Sending of confirmation emails is disabled.')
        else:
            logger.info('Sending confirmation email.')
            template = EmailTemplate.objects.get(id=getConstant('email__registrationSuccessTemplateID'))

            renderEmail(
                subject=template.subject,
                content=template.content,
                from_address=template.defaultFromAddress,
                from_name=template.defaultFromName,
                cc=template.defaultCC,
                registrations=[realreg,],
            )


def submitInvoice(payerEmail,invoiceNumber,tr,itemList=[],discountAmount=0,amountDue=None):
    '''
    Send an invoice to a student requesting payment.
    '''

    logger.info('Creating and sending invoice.')

    if not amountDue:
        amountDue = tr.priceWithDiscount

    invoice_sent.send(
        sender=tr,
        payerEmail=payerEmail,
        invoiceNumber=invoiceNumber,
        itemList=itemList,
        discountAmount=discountAmount,
        amountDue=amountDue,
    )
    logger.debug('Invoice signal fired.')

    if getConstant('email__disableSiteEmails'):
        logger.info('Sending of confirmation email is disabled.')
        return

    logger.info('Sending confirmation email.')
    template = EmailTemplate.objects.get(id=getConstant('email__invoiceTemplateID'))

    renderEmail(
        subject=template.subject,
        content=template.content,
        from_address=template.defaultFromAddress,
        from_name=template.defaultFromName,
        to=payerEmail,
        cc=template.defaultCC,
        temporaryregistrations=[tr,],
        amountDue=amountDue,
        discountAmount=discountAmount,
    )
    logger.debug('Confirmation email sent.')


# ###################################################
# Views


class RegistrationSummaryView(UserFormKwargsMixin, FinancialContextMixin, FormView):
    template_name = 'core/registration_summary.html'
    form_class = DoorAmountForm

    def get(self,request,*args,**kwargs):
        regSession = self.request.session[REG_VALIDATION_STR]
        existing_reg_id = regSession.get('createdRegId',None)

        if existing_reg_id:
            reg = TemporaryRegistration.objects.get(id=existing_reg_id)
        else:
            reg = createTemporaryRegistration(request)
            regSession['createdRegId'] = reg.id

        initial_price = sum(
            [x.event.getBasePrice(isStudent=reg.student,payAtDoor=reg.payAtDoor) for x in reg.temporaryeventregistration_set.exclude(dropIn=True)] +
            [x.price for x in reg.temporaryeventregistration_set.filter(dropIn=True)]
        )

        # If the discounts app is enabled, then the return value to this signal
        # will contain any initial discounts that need to be applied (prior to)
        # the application of any discounts
        discount_responses = request_discounts.send(
            sender=RegistrationSummaryView,
            registration=reg,
        )

        # Although there will typically only be one handler that responds to
        # the apply_discounts signal firing, to be safe, we will always look
        # for and apply the minimum price anyway, to avoid exception issues.
        try:
            discount_responses.sort(key=lambda k: k[1][1])
            discount_code, discounted_total = discount_responses[0][1]
            discount_amount = max(initial_price - discounted_total, 0)
        except:
            discount_code = None
            discounted_total = initial_price
            discount_amount = 0

        if discount_code:
            apply_discount.send(
                sender=RegistrationSummaryView,
                discount=discount_code,
                discount_amount=discount_amount,
                registration=reg,
            )

        # Get any free add-on items that should be applied
        addon_responses = apply_addons.send(
            sender=RegistrationSummaryView,
            registration=reg
        )
        addons = []
        for response in addon_responses:
            try:
                addons += list(addon_responses[1])
            except:
                pass

        # The return value to this signal should contain any adjustments that
        # need to be made to the price (e.g. from vouchers if the voucher app
        # is installed)
        adjustment_responses = apply_price_adjustments.send(
            sender=RegistrationSummaryView,
            registration=reg,
            initial_price=discounted_total
        )

        adjustment_list = []
        adjustment_amount = 0

        for response in adjustment_responses:
            adjustment_list += response[1][0]
            adjustment_amount += response[1][1]

        # Save the discounted price to the database
        total = discounted_total - adjustment_amount
        reg.priceWithDiscount = total
        reg.save()

        # Update the session key to keep track of this registration
        regSession = request.session[REG_VALIDATION_STR]
        regSession["temp_reg_id"] = reg.id
        if discount_code:
            regSession['discount_code_id'] = discount_code.pk
            regSession['discount_code_name'] = discount_code.name
        regSession['discount_amount'] = discount_amount
        regSession['addons'] = addons
        regSession['voucher_names'] = adjustment_list
        regSession['total_voucher_amount'] = adjustment_amount
        request.session[REG_VALIDATION_STR] = regSession

        return super(RegistrationSummaryView,self).get(request,*args,**kwargs)

    def get_context_data(self,**kwargs):
        ''' Pass the initial kwargs, then update with the needed registration info. '''
        context_data = super(RegistrationSummaryView,self).get_context_data(**kwargs)

        regSession = self.request.session[REG_VALIDATION_STR]
        reg_id = regSession["temp_reg_id"]
        reg = TemporaryRegistration.objects.get(id=reg_id)

        discount_code_id = regSession.get('discount_code_id',None)
        discount_code_name = regSession.get('discount_code_name',None)
        discount_amount = regSession.get('discount_amount',0)
        voucher_names = regSession.get('voucher_names',[])
        total_voucher_amount = regSession.get('total_voucher_amount',0)
        addons = regSession.get('addons',[])

        payment_context = get_payment_context.send(
            sender=RegistrationSummaryView,
            registration=reg,
        )
        payment_context_dict = {}
        for x in payment_context:
            if not isinstance(x[1],dict) or 'processor' not in x[1].keys():
                continue
            payment_context_dict[x[1].pop('processor',None)] = x[1]

        if reg.priceWithDiscount == 0:
            processPayment(0,0,'Completed',reg,False,False,invoiceNumber='FREEREGISTRATION_%s_%s' % (reg.id, reg.dateTime.strftime('%Y%m%d%H%M%S')))
            isFree = True
        else:
            isFree = False

        context_data.update({
            'registration': reg,
            "netPrice": reg.priceWithDiscount,
            "addonItems": addons,
            "discount_code_id": discount_code_id,
            "discount_code_name": discount_code_name,
            "discount_code_amount": discount_amount,
            "voucher_names": voucher_names,
            "total_voucher_amount": total_voucher_amount,
            "total_discount_amount": discount_amount + total_voucher_amount,
            "currencyCode": getConstant('general__currencyCode'),
            'payment_context': payment_context_dict,
            'payAtDoor': reg.payAtDoor,
            'is_free': isFree,
        })

        if self.request.user:
            door_permission = self.request.user.has_perm('core.accept_door_payments')
            invoice_permission = self.request.user.has_perm('core.send_invoices')

            if door_permission or invoice_permission:
                context_data['form'] = DoorAmountForm(
                    user=self.request.user,
                    invoiceNumber='registration_%s' % reg.id,
                    doorPortion=door_permission,
                    invoicePortion=invoice_permission,
                    payerEmail=reg.email,
                    itemList=payment_context_dict.get('Paypal',{}).get('invoiceItems'),
                    discountAmount=payment_context_dict.get('Paypal',{}).get('discount_amount_cart'),
                )

        return context_data

    def form_valid(self,form):
        regSession = self.request.session[REG_VALIDATION_STR]
        reg_id = regSession["temp_reg_id"]
        tr = TemporaryRegistration.objects.get(id=reg_id)

        if form.cleaned_data.get('paid'):
            logger.debug('Form is marked paid. Preparing to process payment.')

            amount = form.cleaned_data["amountPaid"]
            submissionUser = form.cleaned_data['submissionUser']
            receivedBy = form.cleaned_data['receivedBy']

            # process payment
            processPayment(
                amount,0,'Completed',
                tr,False,False,
                submissionUser=submissionUser,
                collectedByUser=receivedBy,
                invoiceNumber='CASHPAYMENT_%s_%s' % (tr.id, tr.dateTime.strftime('%Y%m%d%H%M%S'))
            )
        elif form.cleaned_data.get('invoiceSent'):
            clean_itemList = form.cleaned_data.get('itemList') or ''

            payerEmail = form.cleaned_data['payerEmail']
            invoiceNumber = form.cleaned_data['invoiceNumber']
            itemList = json.loads(clean_itemList.replace('&quot;','"'))
            discountAmount = form.cleaned_data['discountAmount']

            submitInvoice(payerEmail,invoiceNumber,tr,itemList,discountAmount)

        return HttpResponseRedirect(Page.objects.get(pk=getConstant('registration__doorRegistrationSuccessPage')).get_absolute_url(settings.LANGUAGE_CODE))


class StudentInfoView(FormView):
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
        ''' Require session data to be set to proceed, otherwise go back to step 1 '''
        if REG_VALIDATION_STR not in request.session:
            return HttpResponseRedirect(reverse('registration'))
        return super(StudentInfoView,self).dispatch(request,*args,**kwargs)

    def get_context_data(self, **kwargs):
        context_data = super(StudentInfoView,self).get_context_data(**kwargs)

        context_data.update({
            'regInfo': self.request.session[REG_VALIDATION_STR].get('regInfo',{}),
            'payAtDoor': self.request.session[REG_VALIDATION_STR].get('payAtDoor',False),
            'currencySymbol': getConstant('general__currencySymbol'),
        })

        # Add the Series, Event, and DanceRole objects to the context data based on what was submitted
        # through the form.
        subtotal = 0

        for k,v in context_data['regInfo'].get('events',{}).items():
            event = Event.objects.prefetch_related('pricingTier').get(id=k)

            dropin_keys = [x for x in v.keys() if x.startswith('dropin_')]
            if dropin_keys:
                name = _('DROP IN: %s' % event.name)
                base_price = event.getBasePrice(dropIns=len(dropin_keys))
            else:
                name = event.name
                base_price = event.getBasePrice(payAtDoor=context_data['payAtDoor'])

            subtotal += base_price

            if v.get('role'):
                role_name = DanceRole.objects.get(id=v.get('role')).name
            else:
                role_name = None

            context_data['regInfo']['events'][k].update({
                'name': name,
                'role_name': role_name,
                'base_price': base_price,
            })

        context_data['subtotal'] = subtotal

        if context_data['payAtDoor'] or self.request.user.is_authenticated or not getConstant('registration__allowAjaxSignin'):
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
        kwargs = super(StudentInfoView, self).get_form_kwargs(**kwargs)
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        return reverse('showRegSummary')

    def form_valid(self,form):
        '''
        Even if this form is valid, the handlers for this form may have added messages
        to the request.  In that case, then the page should be handled as if the form
        were invalid.  Otherwise, update the session data with the form data and then
        move to the next view
        '''
        self.request.session[REG_VALIDATION_STR].update({'infoFormData': form.cleaned_data, 'createdRegId': None})
        self.request.session.modified = True
        return HttpResponseRedirect(self.get_success_url())  # Redirect after POST
