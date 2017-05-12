# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from danceschool.core.utils.sys import isPreliminaryRun


class VoucherAppConfig(AppConfig):
    name = 'danceschool.vouchers'
    verbose_name = 'Voucher Functions'

    def ready(self):
        from django.db import connection
        from danceschool.core.models import Customer
        from danceschool.core.constants import getConstant, updateConstant
        from .models import CustomerVoucher
        # This ensures that the signal receivers are loaded
        from . import handlers

        def creditsAvailable(customer):
            cvs = CustomerVoucher.objects.filter(customer=customer)
            amount = 0
            for cv in cvs:
                amount += cv.voucher.amountLeft

            return amount

        def getCustomerVouchers(customer):
            cvs = CustomerVoucher.objects.filter(customer=customer)
            return [cv.voucher for cv in cvs]

        def getCustomerReferralVouchers(customer):
            cvs = CustomerVoucher.objects.filter(**{
                'customer': customer,
                'voucher__category__id': getConstant('referrals__referrerCategoryID'),
            })
            return [cv.voucher for cv in cvs]

        Customer.add_to_class('getAvailableCredits',creditsAvailable)
        Customer.add_to_class('getVouchers',getCustomerVouchers)
        Customer.add_to_class('getReferralVouchers',getCustomerReferralVouchers)

        if 'vouchers_vouchercategory' in connection.introspection.table_names() and not isPreliminaryRun():
            VoucherCategory = self.get_model('VoucherCategory')

            new_cat_list = [
                (_('Referral Vouchers'), 'referrals__referrerCategoryID'),
                (_('Referee Vouchers'), 'referrals__refereeCategoryID'),
                (_('Email Promotion'), 'vouchers__emailPromoCategoryID'),
                (_('Purchased Gift Certificate'),'vouchers__giftCertCategoryID'),
                (_('Non-Purchased Gift Certificate'),'vouchers__nonPurchasedGiftCertCategoryID'),
            ]

            for cat in new_cat_list:
                if (getConstant(cat[1]) or 0) <= 0:
                    new_cat, created = VoucherCategory.objects.get_or_create(name=cat[0])
                    # Update constant and fail silently
                    updateConstant(cat[1],new_cat.id,True)

        if 'core_emailtemplate' in connection.introspection.table_names() and not isPreliminaryRun():
            from danceschool.core.models import EmailTemplate, get_defaultEmailName, get_defaultEmailFrom

            if (getConstant('vouchers__giftCertTemplateID') or 0) <= 0:
                new_template, created = EmailTemplate.objects.get_or_create(
                    name=_('Gift Certificate Purchase Confirmation Email'),
                    defaults={
                        'subject': _('Gift Certificate Purchase Confirmation'),
                        'content': '',
                        'defaultFromAddress': get_defaultEmailFrom(),
                        'defaultFromName': get_defaultEmailName(),
                        'defaultCC': '',
                        'hideFromForm': True,}
                )
                # Update constant and fail silently
                updateConstant('vouchers__giftCertTemplateID',new_template.id,True)

            if (getConstant('vouchers__giftCertPDFTemplateID') or 0) <= 0:
                new_template, created = EmailTemplate.objects.get_or_create(
                    name=_('Gift Certificate Purchase PDF Text'),
                    defaults={
                        'subject': _('You\'ve Been Given the Gift of Dance!'),
                        'content': _('Insert HTML here.'),
                        'defaultFromAddress': get_defaultEmailFrom(),
                        'defaultFromName': get_defaultEmailName(),
                        'defaultCC': '',
                        'hideFromForm': True,}
                )
                # Update constant and fail silently
                updateConstant('vouchers__giftCertPDFTemplateID',new_template.id,True)
