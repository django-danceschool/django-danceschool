from django.dispatch import Signal

# Fires during the clean process of the StudentInfoView form, allowing hooked in
# apps to validate the form data and raise ValidationErrors or send warnings
# (messages) to the user by adding them to the request.
check_student_info = Signal(''' ['instance', 'formData', 'request', 'registration', 'invoice'] ''')

# Fires after the student info form has been validated and the temporary Registration record
# has been updated to reflect the submitted information from this form.  Since this signal is
# fired before price adjustments from vouchers and discounts are incorporated into the registration,
# this signal can be used to modify the temporary Registration itself (be sure to save changes),
# and it can be used to make related changes in other apps (such as creating VoucherUse
# records in the vouchers app
post_student_info = Signal(''' ['invoice', 'registration'] ''')

# Fires at the point when automatically-applied discounts may be applied to
# a preliminary registration.  Any handler that attaches to this signal should
# return an object that describes the discount (in the case of the discounts app,)
# a DiscountCombo object, as well as the discounted price to be applied to the _entire_
# cart, in tuple form as (object, discounted_price).
request_discounts = Signal(''' ['invoice', 'registration'] ''')

# Fires in the AjaxClassRegistrationView to check the validity of a voucher code
# if it is passed.  Unlike the vouchers handler for check_student_info, the vouchers
# app handler for this signal does not raise ValidationErrors, but instead returns
# a JSON object that indicates if the voucher is invalid as well as the max.
# amount that it can be used for.
check_voucher = Signal(
    ''' ['invoice', 'registration', 'voucherId', 'customer', 'validateCustomer'] '''
)

# Fires after a discount has been actually applied, so that a hooked in discounts
# app can make a record of the discount having been applied.  Note that the core
# app by default records the discounted price of a registration, net of all discounts
# and also of all voucher uses, but it does not itself record information on the
# discounts or vouchers actually applied.
apply_discount = Signal(
    ''' ['invoice', 'registration', 'discount', 'discount_amount'] '''
)

# Fires at the point when free add-on items may be applied to
# a preliminary registration.  Add-ons are simply descriptive, they do not link
# to a registration or any other object at present.
# Any handler that attaches to this signal should return a list with the names of
# the addons.
apply_addons = Signal(''' ['invoice', 'registration'] ''')

# Fires when vouchers or any other direct price adjustments are ready to be applied.
# Any handler that attaches to this signal should return a name/description of the
# adjustment as well as the amount of the adjustment, in tuple form as (name, amount).
apply_price_adjustments = Signal(
    ''' ['invoice', 'registration', 'invoice', 'initial_price'] '''
)

# Fires after a Registration is created.
post_registration = Signal(''' ['invoice', registration'] ''')

# Fires in AjaxClassRegistrationView so that items related to invoices can be
# created or updated at the same time as the invoice.
get_invoice_related = Signal(''' ['invoice', 'post_data', 'prior_response', 'request'] ''')
get_invoice_item_related = Signal(''' ['item', 'item_data', 'post_data', 'prior_response', 'request'] ''')

# Fires whenever an invoice is finalized.
invoice_finalized = Signal(''' ['invoice'] ''')

# Fires whenever an invoice is cancelled.
invoice_cancelled = Signal(''' ['invoice'] ''')

# Fires on the customer profile page to collect customer information from other apps
# without overriding the CustomerStatsView.
get_customer_data = Signal(''' ['customer'] ''')

# Fires when viewing prior EventRegistrations to collect information from other apps
# such as discounts or vouchers that were applied to the Registrations.
get_eventregistration_data = Signal(''' ['eventregistrations'] ''')
