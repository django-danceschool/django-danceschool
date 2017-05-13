from django.dispatch import receiver

from allauth.account.signals import email_confirmed
from allauth.account.models import EmailAddress
import logging

from .signals import post_registration
from .models import Registration


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(email_confirmed)
def linkUserToMostRecentCustomer(sender,**kwargs):
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
    email_address = kwargs.get('email_address',None)

    if not email_address or not email_address.primary or not email_address.verified:
        return

    user = email_address.user

    if not hasattr(user, 'customer'):
        last_reg = Registration.objects.filter(
            customer__email=email_address.email,
            customer__user__isnull=True,
            dateTime__isnull=False
        ).order_by('-dateTime').first()

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
    '''
    If a Registration is processed in which the associated Customer does not yet
    have a User, then check to see if the Customer's email address has been
    verified as belonging to a specific User, and if that User has an associated
    Customer.  If such a User is found, then associated this Customer with that
    User.  This way, if a new User verifies their email account before they have
    submitted any Registrations, their Customer account is seamlessly linked when
    they do complete their first Registration.
    '''
    registration = kwargs.get('registration',None)

    if not registration or (hasattr(registration.customer,'user') and registration.customer.user):
        return

    logger.debug('Checking for User for Customer with no associated registration.')

    customer = registration.customer

    verified_email = EmailAddress.objects.filter(
        email=customer.email,
        verified=True,
        primary=True,
        user__customer__isnull=True
    )

    if verified_email:
        logger.info('Found user %s to associate with customer %s' % (verified_email.user.id, customer.id))

        customer.user = verified_email.user
        customer.save()

        if not customer.user.first_name and not customer.user.last_name:
            customer.user.first_name = customer.first_name
            customer.user.last_name = customer.last_name
            customer.user.save()
