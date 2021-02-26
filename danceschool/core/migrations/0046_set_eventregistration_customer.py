from django.conf import settings
from django.db import migrations
from django.db.models import Q, F, Case, When, IntegerField, Sum
from django.db.models.functions import Coalesce


def set_eventregistration_customer(apps, schema_editor):
    '''
    EventRegistrations that do not yet have a Customer associated with them are
    associated with one if possible.  This is in preparation for removing the
    customer, firstName, lastName, email, phone, and student fields from
    Registration.
    '''
    EventRegistration = apps.get_model("core", "EventRegistration")
    Customer = apps.get_model("core", "Customer")
    db_alias = schema_editor.connection.alias

    to_update = EventRegistration.objects.using(db_alias).filter(
        customer__isnull=True
    ).select_related(
        'registration', 'registration__customer', 'registration__invoice',
    ).order_by('registration__dateTime')

    for er in to_update:
        customer = None

        if er.registration.customer:
            customer = er.registration.customer
        elif (
            er.registration.firstName and er.registration.lastName and
            er.registration.email
        ):
            customer, created = Customer.objects.using(db_alias).update_or_create(
                first_name=er.registration.firstName,
                last_name=er.registration.lastName,
                email=er.registration.email,
                defaults={'phone': er.registration.phone}
            )
        elif (
            er.registration.invoice.firstName and
            er.registration.invoice.lastName and er.registration.invoice.email        
        ):
            customer, created = Customer.objects.using(db_alias).get_or_create(
                first_name=er.registration.invoice.firstName,
                last_name=er.registration.invoice.lastName,
                email=er.registration.invoice.email,
            )

        if customer:
            er.customer = customer
            er.save()


def reverse_eventregistration_customer(apps, schema_editor):
    '''
    Registrations that have a customer or contact information are given the
    information from the Invoice.  We cannot reliably recover this information
    from the EventRegistrations associated with the Registration because there
    may be multiple customers linked to this Registration in that way.
    '''
    Registration = apps.get_model("core", "Registration")
    Customer = apps.get_model("core", "Customer")
    db_alias = schema_editor.connection.alias

    filters = (
        Q(customer__isnull=True) | (
            Q(firstName__isnull=True) & Q(lastName__isnull=True) & Q(email__isnull=True)
        )
    ) & (
        Q(invoice__firstName__isnull=False) | Q(invoice__lastName__isnull=False) |
        Q(invoice__email__isnull=False)
    )

    to_update = Registration.objects.using(db_alias).filter(filters).select_related('invoice')

    for reg in to_update:
        if not (reg.firstName or reg.lastName or reg.email):
            reg.firstName = reg.invoice.firstName
            reg.lastName = reg.invoice.lastName
            reg.email = reg.invoice.email

        if reg.firstName and reg.lastName and reg.email:
            customer, created = Customer.objects.using(db_alias).get_or_create(
                first_name=reg.firstName,
                last_name=reg.lastName,
                email=reg.email,
            )
            reg.customer = customer
        reg.save()


def set_eventregistration_student(apps, schema_editor):
    '''
    EventRegistrations should have their student status set by the status of
    their parent registration for the migration.
    '''
    EventRegistration = apps.get_model("core", "EventRegistration")
    db_alias = schema_editor.connection.alias

    ers = EventRegistration.objects.using(db_alias).annotate(
        regStudent=F('registration__student')
    )
    for er in ers:
        if er.student != er.regStudent:
            er.student = er.regStudent
            er.save()


def reverse_eventregistration_student(apps, schema_editor):
    '''
    Set the student status for registrations to True if all associated
    EventRegistrations agree that it is True.
    '''
    Registration = apps.get_model("core", "Registration")
    db_alias = schema_editor.connection.alias

    Registration.objects.using(db_alias).annotate(
        studentTrue=Coalesce(Sum(Case(
            When(Q(eventregistration__student=True), then=1),
            default=0, output_field=IntegerField()
        )), 0),
        studentFalse=Coalesce(Sum(Case(
            When(Q(eventregistration__student=True), then=1),
            default=0, output_field=IntegerField()
        )), 0),
    ).filter(studentTrue__gt=0, studentFalse=0).update(student=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_eventregistration_student'),
    ]

    operations = [
        migrations.RunPython(set_eventregistration_customer, reverse_eventregistration_customer),
        migrations.RunPython(set_eventregistration_student, reverse_eventregistration_student),
    ]
