from django.dispatch import Signal

# Fires during the clean process of the StudentInfoView form, allowing hooked in apps to validate
# the form data and raise ValidationErrors or send warnings (messages) to the user by adding them to the
# request.
check_student_info = Signal(providing_args=['instance','formData','request','registration'])

# Fires after the student info form has been validated and the TemporaryRegistration record
# has been updated to reflect the submitted information from this form.  Since this signal is
# fired before price adjustments from vouchers and discounts are incorporated into the registration,
# this signal can be used to modify the TemporaryRegistration itself (be sure to save changes),
# and it can be used to make related changes in other apps (such as creating TemporaryVoucherUse)
# records in the VoucherUse app
post_student_info = Signal(providing_args=['registration',])

# Fires at the point when automatically-applied discounts may be applied to
# a preliminary registration.  Any handler that attaches to this signal should
# return an object that describes the discount (in the case of the discounts app,)
# a DiscountCombo object, as well as the discounted price to be applied to the _entire_
# cart, in tuple form as (object, discounted_price).
request_discounts = Signal(providing_args=['registration'])

# Fires after a discount has been actually applied, so that a hooked in discounts
# app can make a record of the discount having been applied.  Note that the core
# app by default records the discounted price of a registration, net of all discounts
# and also of all voucher uses, but it does not itself record information on the
# discounts or vouchers actually applied.
apply_discount = Signal(providing_args=['registration', 'discount','discount_amount'])

# Fires at the point when free add-on items may be applied to
# a preliminary registration.  Add-ons are simply descriptive, they do not link
# to a registration or any other object at present.
# Any handler that attaches to this signal should return a list with the names of
# the addons.
apply_addons = Signal(providing_args=['registration'])

# Fires when vouchers or any other direct price adjustments are ready to be applied.
# Any handler that attaches to this signal should return a name/description of the
# adjustment as well as the amount of the adjustment, in tuple form as (name,amount).
apply_price_adjustments = Signal(providing_args=['registration','initial_price'])

# Fires after a Registration is created.
post_registration = Signal(providing_args=['registration',])

# Fires on the customer profile page to collect customer information from other apps
# without overriding the CustomerStatsView.
get_customer_data = Signal(providing_args=['customer',])
