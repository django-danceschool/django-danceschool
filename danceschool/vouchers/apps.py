# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig


class VoucherAppConfig(AppConfig):
    name = 'danceschool.vouchers'
    verbose_name = 'Voucher Functions'

    def ready(self):
        from danceschool.core.models import Customer
        from danceschool.core.constants import getConstant
        from .models import CustomerVoucher

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
                'voucher__category': getConstant('referrals__referrerCategory'),
            })
            return [cv.voucher for cv in cvs]

        Customer.add_to_class('getAvailableCredits',creditsAvailable)
        Customer.add_to_class('getVouchers',getCustomerVouchers)
        Customer.add_to_class('getReferralVouchers',getCustomerReferralVouchers)

        # This ensures that the signal receivers are loaded
        from . import handlers
