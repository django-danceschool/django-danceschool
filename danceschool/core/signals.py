from django.dispatch import Signal

# Fires during the clean process of the StudentInfoView form, allowing hooked in
# apps to validate the form data and raise ValidationErrors or send warnings
# (messages) to the user by adding them to the request.
# providing_args=['instance', 'formData', 'request', 'registration', 'invoice']
check_student_info = Signal()

# Fires after the student info form has been validated and the temporary Registration record
# has been updated to reflect the submitted information from this form.  Since this signal is
# fired before price adjustments from vouchers and discounts are incorporated into the registration,
# this signal can be used to modify the temporary Registration itself (be sure to save changes),
# and it can be used to make related changes in other apps (such as creating VoucherUse
# records in the vouchers app
# providing_args=['registration', ]
post_student_info = Signal()

# Fires at the point in handling an Ajax shopping cart where additional
# (non-registration) items may be added or removed from the cart.  The POST
# data is passed to the signal, and it should return a dictionary that can be
# passed to the Ajax shopping cart.  Examples of potential uses include merchandise.
# The order_type flag is a check for the handler that ensures that it is working
# with the correct type of information.
# providing_args=['items_data', 'orders_data', 'invoice']
process_cart_items = Signal()

# Fires at the point when automatically-applied discounts may be applied to
# a preliminary registration.  Any handler that attaches to this signal should
# return an object that describes the discount (in the case of the discounts app,)
# a DiscountCombo object, as well as the discounted price to be applied to the _entire_
# cart, in tuple form as (object, discounted_price).
# providing_args=['registration']
request_discounts = Signal()

# Fires in the AjaxClassRegistrationView to check the validity of a voucher code
# if it is passed.  Unlike the vouchers handler for check_student_info, the vouchers
# app handler for this signal does not raise ValidationErrors, but instead returns
# a JSON object that indicates if the voucher is invalid as well as the max.
# amount that it can be used for.
# providing_args=['registration', 'voucherId', 'customer', 'validateCustomer']
check_voucher = Signal()

# Fires after a discount has been actually applied, so that a hooked in discounts
# app can make a record of the discount having been applied.  Note that the core
# app by default records the discounted price of a registration, net of all discounts
# and also of all voucher uses, but it does not itself record information on the
# discounts or vouchers actually applied.
# providing_args=['registration', 'discount', 'discount_amount']
apply_discount = Signal()

# Fires at the point when free add-on items may be applied to
# a preliminary registration.  Add-ons are simply descriptive, they do not link
# to a registration or any other object at present.
# Any handler that attaches to this signal should return a list with the names of
# the addons.
# providing_args=['registration']
apply_addons = Signal()

# Fires when vouchers or any other direct price adjustments are ready to be applied.
# Any handler that attaches to this signal should return a name/description of the
# adjustment as well as the amount of the adjustment, in tuple form as (name, amount).
# providing_args=['registration', 'invoice', 'initial_price']
apply_price_adjustments = Signal()

# Fires after a Registration is created.
# providing_args=['registration', ]
post_registration = Signal()

# Fires whenever an invoice is finalized.
# providing_args=['invoice',]
invoice_finalized = Signal()

# Fires whenever an invoice is cancelled.
# providing_args=['invoice',]
invoice_cancelled = Signal()

# Fires on the customer profile page to collect customer information from other apps
# without overriding the CustomerStatsView.
# providing_args=['customer', ]
get_customer_data = Signal()

# Fires when viewing prior EventRegistrations to collect information from other apps
# such as discounts or vouchers that were applied to the Registrations.
# providing_args=['eventregistrations', ]
get_eventregistration_data = Signal()
