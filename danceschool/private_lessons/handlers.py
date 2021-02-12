from django.dispatch import receiver
from danceschool.core.signals import post_registration
from danceschool.core.models import Registration


@receiver(post_registration)
def finalizePrivateLessonRegistration(sender, **kwargs):
    '''
    Once a private lesson registration is finalized, mark the slots that were
    used to book the private lesson as booked and associate them with the final
    registration.  No need to notify students in this instance because they are
    already receiving a notification of their registration.
    '''

    invoice = kwargs.get('invoice', None)
    registration = Registration.objects.filter(invoice=invoice).first()

    if not invoice or not registration:
        return

    for er in registration.eventregistration_set.filter(
        event__privatelessonevent__isnull=False
    ):
        er.event.finalizeBooking(eventRegistration=er, notifyStudent=False)
