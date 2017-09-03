from django.dispatch import receiver
from danceschool.core.signals import post_registration

from .models import InstructorAvailabilitySlot


@receiver(post_registration)
def updateSlotExpiration(sender,**kwargs):
    '''
    Once a private lesson registration is finalized, mark the slots that were
    used to book the private lesson as booked and associate them with the final
    registration.
    '''

    finalReg = kwargs.pop('registration')
    tr = finalReg.temporaryRegistration

    for er in finalReg.eventregistration_set.filter(
        event__privatelessonevent__isnull=False
    ):
        ter = tr.temporaryeventregistration_set.get(
            event=er.event,
        )
        ter.privateLessonsSlots.all().update(
            status=InstructorAvailabilitySlot.SlotStatus.booked,
            eventRegistration=er,
        )
