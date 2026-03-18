"""
Tests for danceschool.prerequisites.

PrerequisiteAcknowledgementTest
--------------------------------
Verifies that when a series has a requirement with enforcementMethod='A'
(acknowledgement), the mandatory acknowledge_prerequisites checkbox is injected
into RegistrationContactForm and therefore appears on the student-info page.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from danceschool.core.constants import REG_VALIDATION_STR
from danceschool.core.models import (
    Invoice, InvoiceItem, Registration, EventRegistration,
)
from danceschool.core.utils.tests import DefaultSchoolTestCase

from .models import Requirement


class PrerequisiteAcknowledgementTest(DefaultSchoolTestCase):
    """
    Server-side rendering test: an acknowledgement-enforcement requirement
    must cause the acknowledge_prerequisites checkbox to appear in the
    student-info form.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.requirement = Requirement.objects.create(
            name='Must have danced before',
            applicableLevel=cls.levelOne,
            enforcementMethod=Requirement.EnforcementChoice.acknowledgement,
        )

    def _make_registration(self):
        """
        Create a minimal preliminary Invoice + Registration + EventRegistration
        for a series at levelOne, set the required session keys, and return
        (invoice, registration).
        """
        expiry = timezone.now() + timedelta(hours=1)

        invoice = Invoice.objects.create(
            status=Invoice.PaymentStatus.preliminary,
            expirationDate=expiry,
        )
        invoice_item = InvoiceItem.objects.create(invoice=invoice, grossTotal=50)

        registration = Registration.objects.create(invoice=invoice)

        series = self.create_series()
        EventRegistration.objects.create(
            registration=registration,
            invoiceItem=invoice_item,
            event=series,
        )

        session = self.client.session
        session[REG_VALIDATION_STR] = {
            'invoice_id': str(invoice.id),
            'invoice_expiry': expiry.isoformat(),
        }
        session.save()

        return invoice, registration

    # -- Tests ----------------------------------------------------------------

    def test_acknowledgement_checkbox_present(self):
        """
        The acknowledge_prerequisites field must appear on the student-info
        page when a series has an acknowledgement-enforcement requirement.
        """
        self._make_registration()
        response = self.client.get(reverse('getStudentInfo'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'acknowledge_prerequisites')

    def test_acknowledgement_checkbox_shows_requirement_name(self):
        """
        The tooltip on the checkbox must include the requirement name so the
        customer knows what they are agreeing to.
        """
        self._make_registration()
        response = self.client.get(reverse('getStudentInfo'))
        self.assertContains(response, 'Must have danced before')

    def test_no_checkbox_without_acknowledgement_requirement(self):
        """
        When the series has no acknowledgement requirement, the checkbox must
        not appear.
        """
        # Temporarily change enforcement to 'warning' so no ack checkbox fires.
        self.requirement.enforcementMethod = Requirement.EnforcementChoice.warning
        self.requirement.save()
        try:
            self._make_registration()
            response = self.client.get(reverse('getStudentInfo'))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'acknowledge_prerequisites')
        finally:
            self.requirement.enforcementMethod = Requirement.EnforcementChoice.acknowledgement
            self.requirement.save()
