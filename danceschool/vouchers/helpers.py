import uuid
from django.utils.translation import ugettext_lazy as _

from danceschool.core.models import DanceTypeLevel, ClassDescription
from danceschool.core.constants import getConstant

from .models import Voucher, VoucherCategory, ClassVoucher, CustomerVoucher, VoucherReferralDiscount, VoucherCredit, VoucherReferralDiscountUse


def generateUniqueVoucherId(prefix):
    uid = uuid.uuid4()
    result = prefix + uid.hex[0:8].upper()
    objs = Voucher.objects.filter(voucherId=result)

    while len(objs) > 0:
        result = prefix + uid.hex[0:8]
        objs = Voucher.objects.filter(voucherId=result)

    return result


def createReferreeVoucher(name,amountPerUse):
    voucherId = generateUniqueVoucherId(getConstant('referrals__voucherPrefix'))
    category = getConstant('referrals__refereeCategory')
    originalAmount = 1e9
    maxAmountPerUse = amountPerUse
    singleUse = False
    forFirstTimeCustomersOnly = True
    expirationDate = None
    disabled = False

    voucher = Voucher(
        voucherId=voucherId,name=name,
        category=category,
        originalAmount=originalAmount,
        maxAmountPerUse=maxAmountPerUse,
        singleUse=singleUse,
        forFirstTimeCustomersOnly=forFirstTimeCustomersOnly,
        expirationDate=expirationDate,
        disabled=disabled
    )
    voucher.save()

    # Find all beginner classes
    dts = DanceTypeLevel.objects.filter(name="Beginner",danceType__name="Lindy Hop")
    classes = ClassDescription.objects.filter(danceTypeLevel=dts.first())
    for c in classes:
        cv = ClassVoucher(voucher=voucher,classDescription=c)
        cv.save()
    return voucher


def createReferrerVoucher(customer):
    voucherId = generateUniqueVoucherId(getConstant('referrals__voucherPrefix'))
    category = getConstant('referrals__referrerCategory')
    originalAmount = 0
    maxAmountPerUse = None
    singleUse = False
    forFirstTimeCustomersOnly = False
    expirationDate = None
    disabled = False
    name = _("Referral Bonus for %s, %s" % (customer.fullName,customer.email))

    voucher = Voucher(
        voucherId=voucherId,name=name,
        category=category,
        originalAmount=originalAmount,
        maxAmountPerUse=maxAmountPerUse,
        singleUse=singleUse,
        forFirstTimeCustomersOnly=forFirstTimeCustomersOnly,
        expirationDate=expirationDate,
        disabled=disabled
    )
    voucher.save()

    cv = CustomerVoucher(customer=customer,voucher=voucher)
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
