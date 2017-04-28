from django.dispatch import Signal

# Define a custom signal that fires whenever an invoice is created and sent (e.g. to hook in Paypal)
refund_requested = Signal(providing_args=['registration','refundType','refundAmount'])
