'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _
from django.db import connection
from django.template.loader import get_template

from dynamic_preferences.types import BooleanPreference, StringPreference, FloatPreference, ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.models import EmailTemplate, get_defaultEmailName, get_defaultEmailFrom
from .models import VoucherCategory


# we create some section objects to link related preferences together

vouchers = Section('vouchers',_('Vouchers/Gift Certificates'))
referrals = Section('referrals',_('Referral Program'))


##############################
# General Vouchers/Gift Cert Preferences
#
@global_preferences_registry.register
class VouchersEnabled(BooleanPreference):
    section = vouchers
    name = 'enableVouchers'
    verbose_name = _('Enable Vouchers')
    help_text = _('If checked, then voucher functionality will be enabled.')
    default = True


@global_preferences_registry.register
class GiftCertificatesEnabled(BooleanPreference):
    section = vouchers
    name = 'enableGiftCertificates'
    verbose_name = _('Enable Gift Certificates')
    help_text = _('If checked, then gift certificate functionality will be enabled.')
    default = True


@global_preferences_registry.register
class GiftCertificatesPDFEnabled(BooleanPreference):
    section = vouchers
    name = 'enableGiftCertificatePDF'
    verbose_name = _('Enable Gift Certificate PDF Attachments')
    help_text = _('If checked, then gift certificate emails will come with an attached PDF that can be printed and presented as a gift, based on the special EmailTemplate.')
    default = True


@global_preferences_registry.register
class EmailPromoCat(ModelChoicePreference):
    section = vouchers
    name = 'emailPromoCategory'
    verbose_name = _('Voucher Category for email promotions')
    model = VoucherCategory
    queryset = VoucherCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return VoucherCategory.objects.get_or_create(name=_('Email Promotion'))[0]


@global_preferences_registry.register
class GiftCertCat(ModelChoicePreference):
    section = vouchers
    name = 'giftCertCategory'
    verbose_name = _('Voucher Category for Purchased Gift Certificates')
    model = VoucherCategory
    queryset = VoucherCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return VoucherCategory.objects.get_or_create(name=_('Purchased Gift Certificate'))[0]


@global_preferences_registry.register
class NonPurchasedGiftCertCatID(ModelChoicePreference):
    section = vouchers
    name = 'nonPurchasedGiftCertCategory'
    verbose_name = _('Voucher Category for Non-Purchased (Promotional) Gift Certificates')
    model = VoucherCategory
    queryset = VoucherCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return VoucherCategory.objects.get_or_create(name=_('Non-Purchased Gift Certificate'))[0]


@global_preferences_registry.register
class GiftCertTemplate(ModelChoicePreference):
    section = vouchers
    name = 'giftCertTemplate'
    verbose_name = _('Email Template for Gift Certificates')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():

        initial_template = get_template('email/gift_certificate_confirmation.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Gift Certificate Purchase Confirmation Email'),
            defaults={
                'subject': _('Gift Certificate Purchase Confirmation'),
                'content': content,
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]


@global_preferences_registry.register
class GiftCertPDFTemplate(ModelChoicePreference):
    section = vouchers
    name = 'giftCertPDFTemplate'
    verbose_name = _('Email Template for Gift Certificate PDF Attachments')
    model = EmailTemplate
    queryset = EmailTemplate.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():

        initial_template = get_template('email/gift_certificate_attachment.html')
        with open(initial_template.origin.name,'r') as infile:
            content = infile.read()
            infile.close()

        return EmailTemplate.objects.get_or_create(
            name=_('Gift Certificate Purchase PDF Text'),
            defaults={
                'subject': _('You\'ve Been Given the Gift of Dance!'),
                'content': content,
                'defaultFromAddress': get_defaultEmailFrom(),
                'defaultFromName': get_defaultEmailName(),
                'defaultCC': '',
                'hideFromForm': True,
            }
        )[0]


##############################
# Referral Program Preferences
#
@global_preferences_registry.register
class ReferralProgramEnabled(BooleanPreference):
    section = referrals
    name = 'enableReferralProgram'
    verbose_name = _('Enable Referral Program')
    help_text = _('If checked, then each customer will automatically have a referral code generated that they can use to get friends discounts.')
    default = False


@global_preferences_registry.register
class RefereeAmount(FloatPreference):
    section = referrals
    name = 'refereeDiscount'
    verbose_name = _('Discount to Referees')
    help_text = _('Discount given to individuals who provide a referral code.  In default currency.')
    default = 0.0


@global_preferences_registry.register
class ReferrerAmount(FloatPreference):
    section = referrals
    name = 'referrerDiscount'
    verbose_name = _('Discount to Referrers')
    help_text = _('Discount given to students who refer other students via referral code.  In default currency.')
    default = 0.0


@global_preferences_registry.register
class VoucherPrefix(StringPreference):
    section = referrals
    name = 'voucherPrefix'
    verbose_name = _('Prefix applied to all referral voucher codes.')
    default = 'REF'


@global_preferences_registry.register
class ReferrerCat(ModelChoicePreference):
    section = referrals
    name = 'referrerCategory'
    help_text = _('The Voucher Category for referrer vouchers')
    model = VoucherCategory
    queryset = VoucherCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return VoucherCategory.objects.get_or_create(name=_('Referral Vouchers'))[0]


@global_preferences_registry.register
class RefereeCat(ModelChoicePreference):
    section = referrals
    name = 'refereeCategory'
    help_text = _('The Voucher Category for referee vouchers')
    model = VoucherCategory
    queryset = VoucherCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return VoucherCategory.objects.get_or_create(name=_('Referee Vouchers'))[0]
