from django.dispatch import Signal

# Fires when collecting the set of purchasable items for a register page or
# for shopping cart processing.
collect_purchasable_items = Signal(
    ''' ['request', 'payAtDoor', 'date'] '''
)

# Fires during RegistrationContactForm.__init__() to allow other apps to
# inject additional fields into the mid-section of the form (below
# agreeToPolicies).  Each connected handler should return either None or a
# list of (field_name, field, layout_element) tuples, where field is a
# Django form field instance and layout_element is a crispy-forms layout
# object.  All returned fields are added to the form and their layout
# elements are appended inside the mid-section card.
collect_student_info_fields = Signal(
    ''' ['instance', 'request', 'eventRegs', 'registration', 'invoice'] '''
)

# Fires during the clean process of the StudentInfoView form or the
# MultiRegCustomerNameForm, allowing hooked in apps to validate the form data
# and raise ValidationErrors or send warnings (messages) to the user by adding
# them to the request.
check_student_info = Signal(
    ''' ['instance', 'data', 'request', 'eventRegs', 'registration', 'invoice'] '''
)

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
request_discounts = Signal(
    ''' ['invoice', 'registration', 'customer_final', 'voucher_code'] '''
)

# Fires to check the validity of a voucher code if it is passed.  Unlike the
# vouchers handler for check_student_info, the vouchers app handler for this
# signal does not raise ValidationErrors, but instead returns a JSON object that
# indicates if the voucher is invalid as well as the max. amount that it can be
# used for.
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

# Fires so that items related to invoices can be created or updated at the same
# time as the invoice.
get_invoice_related = Signal(''' ['invoice', 'post_data', 'prior_response', 'request'] ''')
get_cart_invoice_related = Signal(''' ['invoice', 'item_data', 'payAtDoor', 'request'] ''')
get_invoice_item_related = Signal(''' ['item', 'item_data', 'post_data', 'prior_response', 'request'] ''')
get_cart_invoice_item_related = Signal(''' ['item', 'item_data', 'cart_data', 'prior_response', 'purchasable_registry', 'request'] ''')

# Fires whenever an invoice is finalized.
invoice_finalized = Signal(''' ['invoice'] ''')

# Fires whenever an invoice is cancelled.
invoice_cancelled = Signal(''' ['invoice'] ''')

# Fires on the customer profile page and elsewhere to collect customer or
# person-level information from other apps without overriding the CustomerStatsView.
get_person_data = Signal(
    ''' ['customer', 'first_name', 'last_name', 'email', 'staff_member', 'names'] '''
)

# Fires when viewing prior EventRegistrations to collect information from other apps
# such as discounts or vouchers that were applied to the Registrations.
get_eventregistration_data = Signal(''' ['eventregistrations'] ''')

# Fires when viewing the list of registrations by event in
# views.EventRegistrationSummaryView to get other names that may be checked in,
# such as guest list names.  
get_additional_event_names = Signal(''' ['event'] ''')

# Fires from EventRegistrationSummaryView.get_context_data() so that other
# apps can contribute extra header statistics (label/value pairs) to be
# rendered in the summary <dl> above the registration table. Each handler
# should return either an empty list or a list of dicts shaped
# {'label': str, 'value': str_or_int}.
get_registration_summary_header_stats = Signal(
    ''' ['event', 'registrations'] '''
)
