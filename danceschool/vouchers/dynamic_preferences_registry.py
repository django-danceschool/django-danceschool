'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.forms import HiddenInput
from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, IntegerPreference, StringPreference, FloatPreference, Section
from dynamic_preferences.registries import global_preferences_registry

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
class EmailPromoCatID(IntegerPreference):
    section = vouchers
    name = 'emailPromoCategoryID'
    help_text = _('The ID of the created VoucherCategory for Email Promotions')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class GiftCertCatID(IntegerPreference):
    section = vouchers
    name = 'giftCertCategoryID'
    help_text = _('The ID of the created VoucherCategory for Purchased Gift Certificates')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class NonPurchasedGiftCertCatID(IntegerPreference):
    section = vouchers
    name = 'nonPurchasedGiftCertCategoryID'
    help_text = _('The ID of the created VoucherCategory for Non-Purchased (Promotional) Gift Certificates')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class GiftCertTemplateID(IntegerPreference):
    section = vouchers
    name = 'giftCertTemplateID'
    help_text = _('The ID of the created Email Template for Gift Certificates')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class GiftCertPDFTemplateID(IntegerPreference):
    section = vouchers
    name = 'giftCertPDFTemplateID'
    help_text = _('The ID of the created Email Template for Gift Certificates PDF Attachments')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


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
class ReferrerCatID(IntegerPreference):
    section = referrals
    name = 'referrerCategoryID'
    help_text = _('The ID of the created VoucherCategory for referrers')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class RefereeCatID(IntegerPreference):
    section = referrals
    name = 'refereeCategoryID'
    help_text = _('The ID of the created VoucherCategory for referees')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0
