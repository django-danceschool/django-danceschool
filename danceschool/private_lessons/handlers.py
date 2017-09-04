from django.dispatch import receiver
from danceschool.core.signals import post_registration


@receiver(post_registration)
def finalizePrivateLessonRegistration(sender,**kwargs):
    '''
    Once a private lesson registration is finalized, mark the slots that were
    used to book the private lesson as booked and associate them with the final
    registration.  No need to notify students in this instance because they are
    already receiving a notification of their registration.
    '''

    finalReg = kwargs.pop('registration')

    for er in finalReg.eventregistration_set.filter(
        event__privatelessonevent__isnull=False
    ):
        er.event.finalizeBooking(eventRegistration=er,notifyStudent=False)
