from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from .filters import MerchItemFilter, MerchOrderItemFilter, MerchOrderFilter
from .models import MerchItem, MerchOrderItem, MerchOrder
from .serializers import (
    MerchItemSerializer, MerchOrderItemSerializer, MerchOrderSerializer
)

from danceschool.core.mixins import (
     BrowsableRestMixin, CSVRestMixin
)
from danceschool.core.permissions import (
    DjangoModelPermissions, CoreExportPermission
)


class MerchItemPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000
    ordering = 'name'


class MerchOrderItemPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000
    ordering = ('-order__creationDate', 'item__name')


class MerchOrderPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000
    ordering = '-creationDate'


class MerchItemViewSet(BrowsableRestMixin, CSVRestMixin, viewsets.ModelViewSet):
    queryset = MerchItem.objects.all().order_by('name')
    serializer_class = MerchItemSerializer
    permission_classes = [DjangoModelPermissions&CoreExportPermission]
    filterset_class = MerchItemFilter
    pagination_class = MerchItemPagination


class MerchOrderItemViewSet(BrowsableRestMixin, CSVRestMixin, viewsets.ReadOnlyModelViewSet):
    queryset = MerchOrderItem.objects.all().order_by('-order__creationDate', 'item__name')
    serializer_class = MerchOrderItemSerializer
    permission_classes = [DjangoModelPermissions&CoreExportPermission]
    filterset_class = MerchOrderItemFilter
    pagination_class = MerchOrderItemPagination


class MerchOrderViewSet(BrowsableRestMixin, CSVRestMixin, viewsets.ReadOnlyModelViewSet):
    queryset = MerchOrder.objects.all().order_by('-lastModified', '-creationDate')
    serializer_class = MerchOrderSerializer
    permission_classes = [DjangoModelPermissions&CoreExportPermission]
    filterset_class = MerchOrderFilter
    pagination_class = MerchOrderPagination
