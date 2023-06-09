from rest_framework import routers

from .views import (
    MerchItemViewSet, MerchOrderItemViewSet, MerchOrderViewSet
)

router = routers.DefaultRouter()
router.register(r'merch/merchitem', MerchItemViewSet)
router.register(r'merch/merchorderitem', MerchOrderItemViewSet)
router.register(r'merch/merchorder', MerchOrderViewSet)

# This app has only REST views, not public-facing HTML pages.
urlpatterns = []
