import uuid
from django.utils.translation import gettext_lazy as _

from danceschool.core.models import DanceTypeLevel, ClassDescription
from danceschool.core.constants import getConstant

from .models import (
    Voucher, CustomerVoucher, VoucherReferralDiscount, VoucherCredit,
    VoucherReferralDiscountUse
)


def generateUniqueVoucherId(prefix):
    uid = uuid.uuid4()
    result = prefix + uid.hex[0:8].upper()
    objs = Voucher.objects.filter(voucherId=result)

    while len(objs) > 0:
        result = prefix + uid.hex[0:8]
        objs = Voucher.objects.filter(voucherId=result)

    return result


def createReferreeVoucher(name, amountPerUse):

    voucher = Voucher(
        voucherId=generateUniqueVoucherId(getConstant('referrals__voucherPrefix')),
        name=name,
        category=getConstant('referrals__refereeCategory'),
        originalAmount=1e9,
        maxAmountPerUse=amountPerUse,
        singleUse=False,
        forFirstTimeCustomersOnly=True,
        expirationDate=None,
        disabled=False,
        beforeTax=True,
    )
    voucher.save()
    return voucher


def createReferrerVoucher(customer):
    voucher = Voucher(
        voucherId=generateUniqueVoucherId(getConstant('referrals__voucherPrefix')),
        name=_("Referral Bonus for %s, %s" % (customer.fullName, customer.email)),
        category=getConstant('referrals__referrerCategory'),
        originalAmount=0,
        maxAmountPerUse=None,
        singleUse=False,
        forFirstTimeCustomersOnly=False,
        expirationDate=None,
        disabled=False,
        beforeTax=False,
    )
    voucher.save()

    cv = CustomerVoucher(customer=customer, voucher=voucher)
    cv.save()

    return voucher


def referralVoucherExists(customer):

    for cv in CustomerVoucher.objects.filter(customer=customer):
        vrd = VoucherReferralDiscount.objects.filter(referrerVoucher=cv.voucher).first()
        if vrd:
            return vrd


def ensureReferralVouchersExist(customer):
    # is there a referral voucher for this person?
    # Find all CustomerVouchers for this person
    vrd = referralVoucherExists(customer)

    referreeDiscount = getConstant('referrals__refereeDiscount')
    referrerDiscount = getConstant('referrals__referrerDiscount')

    if vrd:
        vrd.amount = referrerDiscount
        vrd.save()

        vrd.referreeVoucher.maxAmountPerUse = referreeDiscount
        vrd.referreeVoucher.save()
    else:
        name = _('Referral: %s' % customer.fullName)

        # create the referree voucher
        referreeVoucher = createReferreeVoucher(name, referreeDiscount)

        # create the referrer voucher
        referrerVoucher = createReferrerVoucher(customer)

        # create the thing that ties them together
        vrd = VoucherReferralDiscount.objects.get_or_create(
            referrerVoucher=referrerVoucher,
            referreeVoucher=referreeVoucher,
            referrerBonus=referrerDiscount
        )

    return vrd


def awardReferrers(voucherUse):
    rds = VoucherReferralDiscount.objects.filter(referreeVoucher=voucherUse.voucher)

    for rd in rds:
        vc = VoucherCredit(
            voucher=rd.referrerVoucher,
            amount=rd.referrerBonus,
            description=_("Referral from " + str(rd.referreeVoucher)),
        )
        vc.save()
        vrdu = VoucherReferralDiscountUse(
            voucherReferralDiscount=rd,
            voucherUse=voucherUse,
            voucherCredit=vc
        )
        vrdu.save()
