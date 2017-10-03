from django.core.management.base import BaseCommand
from django.utils import timezone

from danceschool.private_events.models import EventReminder
from danceschool.private_events.tasks import sendReminderEmailToUser


class Command(BaseCommand):
    help = 'Send reminder emails associated with private events'

    def handle(self, *args, **options):

        reminders_needed = EventReminder.objects.filter(**{
            'time__lte': timezone.now(),
            'completed':False,
            'notifyList__isnull': False})
        if reminders_needed:
            self.stdout.write('Preparing to send reminder emails.')
            for note in reminders_needed:
                for user in note.notifyList.all():
                    sent = sendReminderEmailToUser(user,note)
                    if sent:
                        # Mark reminder as sent so it won't be sent twice.
                        note.completed = True
                        note.save()
                    else:
                        self.stdout.write(self.style.ERROR("Unable to send email to user: " + user.first_name + ' ' + user.last_name + ' at ' + user.email))
        else:
            self.stdout.write("No notifications to send!")
