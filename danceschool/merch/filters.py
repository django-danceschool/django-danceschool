from django_filters import rest_framework as rest_filters
from django_filters import CharFilter, DateFromToRangeFilter

from .models import MerchItem, MerchOrderItem, MerchOrder


class MerchItemFilter(rest_filters.FilterSet):
    description = CharFilter(lookup_expr='icontains')
    creationDate = DateFromToRangeFilter()

    class Meta:
        model = MerchItem
        fields = [
            'description', 'category', 'defaultPrice', 'creationDate'
        ]


class MerchOrderItemFilter(rest_filters.FilterSet):
    item = CharFilter(lookup_expr='icontains')
    item_sku = CharFilter(lookup_expr='icontains')
    order_creationDate = DateFromToRangeFilter()

    class Meta:
        model = MerchOrderItem
        fields = [
            'item', 'item_sku', 'quantity', 'order_creationDate'
        ]

class MerchOrderFilter(rest_filters.FilterSet):
    creationDate = DateFromToRangeFilter()
    lastModified = DateFromToRangeFilter()

    class Meta:
        model = MerchOrder
        fields = [
            'invoice', 'status', 'creationDate', 'lastModified'
        ]
