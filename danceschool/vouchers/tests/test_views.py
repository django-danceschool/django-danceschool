from unittest import mock

from django.template import Context, Template
from django.template.loader import get_template
from django.urls import reverse

from danceschool.core.constants import PAYMENT_VALIDATION_STR, updateConstant
from danceschool.core.models import Invoice

from ..models import Voucher, VoucherCategory
from .base import BaseVouchersTest


# Emails are sent by a method of this class, which is replaced in these tests
# so that the arguments that are passed to it can be checked.
EMAIL_METHOD = 'danceschool.core.mixins.EmailRecipientMixin.email_recipient'


class GiftCertificatePurchaseTest(BaseVouchersTest):
    '''
    Once a gift certificate has been paid for, the purchaser fills in a form,
    and a voucher for the amount paid is created and emailed.
    '''

    def setUp(self):
        self.invoice = Invoice.objects.create(
            grossTotal=25, total=25, amountPaid=25,
            status=Invoice.PaymentStatus.paid,
        )
        session = self.client.session
        session[PAYMENT_VALIDATION_STR] = {
            'invoiceID': str(self.invoice.id),
            'amount': 25,
            'successUrl': '/done/',
        }
        session.save()

    def test_gift_certificate_is_created_and_emailed(self):
        with mock.patch(EMAIL_METHOD) as email:
            response = self.client.post(reverse('customizeGiftCertificate'), {
                'emailTo': 'recipient@example.com',
                'emailType': 'R',
                'recipientName': 'Lucky Recipient',
                'fromName': 'Generous Purchaser',
                'message': 'Enjoy your classes!',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/done/')

        voucher = Voucher.objects.get()
        self.assertTrue(voucher.voucherId.startswith('GC_'))
        self.assertEqual(voucher.originalAmount, 25)
        self.assertEqual(voucher.amountLeft, 25)
        self.assertFalse(voucher.singleUse)
        self.assertIsNone(voucher.expirationDate)

        self.assertEqual(email.call_count, 1)
        email_kwargs = email.call_args.kwargs
        self.assertEqual(email_kwargs['to'], 'recipient@example.com')
        self.assertEqual(email_kwargs['certificateCode'], voucher.voucherId)
        self.assertEqual(email_kwargs['certificateAmount'], 25)
        self.assertEqual(email_kwargs['certificateMessage'], 'Enjoy your classes!')
        self.assertEqual(email_kwargs['recipientName'], 'Lucky Recipient')

        # The form cannot be submitted again to create a second voucher.
        self.assertNotIn(PAYMENT_VALIDATION_STR, self.client.session)
        response = self.client.post(reverse('customizeGiftCertificate'), {
            'emailTo': 'recipient@example.com', 'emailType': 'R',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Voucher.objects.count(), 1)

    def submit(self):
        with mock.patch(EMAIL_METHOD) as email:
            self.client.post(reverse('customizeGiftCertificate'), {
                'emailTo': 'recipient@example.com', 'emailType': 'R',
                'message': 'Enjoy your classes!',
            })
        self.assertEqual(email.call_count, 1)
        return email.call_args.kwargs

    def test_pdf_is_attached_when_enabled(self):
        updateConstant('vouchers__enableGiftCertificatePDF', True)
        email_kwargs = self.submit()

        self.assertEqual(email_kwargs['attachment_name'], 'gift_certificate.pdf')
        self.assertTrue(email_kwargs['attachment'].startswith(b'%PDF'))

    def test_pdf_is_not_attached_when_disabled(self):
        updateConstant('vouchers__enableGiftCertificatePDF', False)
        try:
            email_kwargs = self.submit()
        finally:
            updateConstant('vouchers__enableGiftCertificatePDF', True)

        self.assertIsNone(email_kwargs['attachment'])
        self.assertIsNone(email_kwargs['attachment_name'])
        self.assertEqual(Voucher.objects.count(), 1)

    def test_default_templates_use_variables_that_are_passed(self):
        '''
        The default text of the confirmation email and of the PDF uses the
        names of the variables that the view passes to them.
        '''
        context = Context({
            'emailType': 'R', 'recipientName': 'Lucky Recipient',
            'certificateMessage': 'Enjoy your classes!',
            'certificateCode': 'GC_CODE', 'certificateAmount': 25,
        })
        for name in [
            'email/gift_certificate_confirmation.html',
            'email/gift_certificate_attachment.html',
        ]:
            with open(get_template(name).origin.name) as infile:
                rendered = Template(infile.read()).render(context)
            self.assertIn('Dear Lucky Recipient', rendered, msg=name)
            self.assertIn('Enjoy your classes!', rendered, msg=name)
            self.assertIn('GC_CODE', rendered, msg=name)

    def test_email_address_is_required(self):
        with mock.patch(EMAIL_METHOD) as email:
            response = self.client.post(reverse('customizeGiftCertificate'), {
                'emailType': 'R',
            })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data['form'].errors.get('emailTo'))
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(email.called)

    def test_gift_certificate_can_be_used_as_voucher(self):
        with mock.patch(EMAIL_METHOD):
            self.client.post(reverse('customizeGiftCertificate'), {
                'emailTo': 'recipient@example.com', 'emailType': 'R',
            })
        voucher = Voucher.objects.get()
        updateConstant('vouchers__enableVouchers', True)
        series = self.create_series()

        self.new_session()
        response = self.checkout(series, code=voucher.voucherId)

        self.assertVoucherApplied(response, voucher, 25)


class VoucherGenerationViewTest(BaseVouchersTest):
    ''' Staff can quickly create a voucher, and optionally email it. '''

    def setUp(self):
        self.url = reverse('generateVoucher')
        self.category = VoucherCategory.objects.create(name='Promotions')

    def post_data(self, **kwargs):
        data = {
            'voucherId': 'GENERATED', 'description': 'A Generated Voucher',
            'amount': 15, 'category': self.category.id,
        }
        data.update(kwargs)
        return data

    def test_permission_is_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        # A user without the permission is turned away (with a redirect or a
        # refusal, depending on the site's settings), and nothing is created.
        self.client.force_login(self.nonStaffUser)
        response = self.client.post(self.url, self.post_data())
        self.assertIn(response.status_code, [302, 403])
        self.assertFalse(Voucher.objects.exists())

    def test_form_can_be_filled_in_from_link(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            self.url + '?prefix=PROMO_&amount=15&name=Spring-Promotion&category=%s' % (
                self.category.id
            )
        )
        initial = response.context_data['form'].initial

        self.assertEqual(response.status_code, 200)
        self.assertTrue(initial['voucherId'].startswith('PROMO_'))
        self.assertEqual(len(initial['voucherId']), len('PROMO_') + 10)
        self.assertEqual(initial['description'], 'Spring Promotion')
        self.assertEqual(initial['amount'], 15)
        self.assertEqual(initial['category'], self.category)

    def test_voucher_is_created_without_email(self):
        self.client.force_login(self.superuser)
        with mock.patch(EMAIL_METHOD) as email:
            response = self.client.post(self.url, self.post_data())

        self.assertEqual(response.status_code, 302)
        voucher = Voucher.objects.get()
        self.assertEqual(voucher.voucherId, 'GENERATED')
        self.assertEqual(voucher.name, 'A Generated Voucher')
        self.assertEqual(voucher.originalAmount, 15)
        self.assertEqual(voucher.category, self.category)
        self.assertFalse(email.called)

    def test_voucher_is_created_and_emailed(self):
        self.client.force_login(self.superuser)
        with mock.patch(EMAIL_METHOD) as email:
            response = self.client.post(self.url, self.post_data(
                emailTo='recipient@example.com', recipientName='Lucky Recipient',
            ))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Voucher.objects.get().voucherId, 'GENERATED')
        self.assertEqual(email.call_count, 1)
        email_kwargs = email.call_args.kwargs
        self.assertEqual(email_kwargs['to'], 'recipient@example.com')
        self.assertEqual(email_kwargs['certificateCode'], 'GENERATED')
        self.assertEqual(email_kwargs['certificateAmount'], 15)

    def test_existing_voucher_code_is_refused(self):
        self.create_voucher(voucherId='GENERATED')
        self.client.force_login(self.superuser)

        response = self.client.post(self.url, self.post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data['form'].errors.get('voucherId'))
        self.assertEqual(Voucher.objects.count(), 1)


class VoucherAdminTest(BaseVouchersTest):

    def setUp(self):
        self.voucher = self.create_voucher()
        self.client.force_login(self.superuser)
        self.url = reverse('admin:vouchers_voucher_changelist')

    def test_changelist(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.voucher.voucherId)

    def test_disable_and_enable_actions(self):
        self.client.post(self.url, {
            'action': 'disableVoucher', '_selected_action': [self.voucher.pk],
        }, follow=True)
        self.assertTrue(Voucher.objects.get(pk=self.voucher.pk).disabled)

        self.client.post(self.url, {
            'action': 'enableVoucher', '_selected_action': [self.voucher.pk],
        }, follow=True)
        self.assertFalse(Voucher.objects.get(pk=self.voucher.pk).disabled)


class VoucherStatsTest(BaseVouchersTest):
    '''
    The statistics on the use of vouchers only count vouchers used for
    registrations that have been finalized.
    '''

    def setUp(self):
        updateConstant('vouchers__enableVouchers', True)
        self.voucher = self.create_voucher(originalAmount=100, maxAmountPerUse=10)
        self.series = self.create_series(
            classDescription=self.levelOneClassDescription
        )
        self.other_series = self.create_series(
            classDescription=self.levelTwoClassDescription
        )

    def get_json(self, url_name):
        self.new_session()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_stats_require_staff(self):
        for url_name in ['popularVouchersJSON', 'voucherFrequencyJSON']:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)

    def test_unpaid_registration_is_not_counted(self):
        self.checkout(self.series, code=self.voucher.voucherId)

        self.assertEqual(self.get_json('popularVouchersJSON'), [])
        self.assertEqual(self.get_json('voucherFrequencyJSON'), [])

    def test_paid_registrations_are_counted(self):
        # One registration with a voucher, and one without.
        self.checkout(self.series, code=self.voucher.voucherId)
        self.pay()
        self.new_session()
        self.checkout(
            self.other_series, name=('Another', 'Customer'), email='another@customer.com'
        )
        self.pay()

        self.assertEqual(
            self.get_json('popularVouchersJSON'),
            [{
                'name': self.voucher.name, 'counter': 1,
                'voucherId': self.voucher.voucherId,
            }]
        )
        self.assertEqual(
            self.get_json('voucherFrequencyJSON'),
            [{'vouchers': 0, 'count': 1}, {'vouchers': 1, 'count': 1}]
        )
