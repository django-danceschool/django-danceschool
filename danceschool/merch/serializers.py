from rest_framework import serializers

from .models import MerchOrder, MerchItem, MerchOrderItem, MerchItemVariant


class MerchItemVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchItemVariant
        fields = [
            'sku', 'fullName', 'name', 'price', 'currentInventory', 'soldOut' 
        ]


class MerchItemSerializer(serializers.ModelSerializer):
    variants = MerchItemVariantSerializer(many=True, read_only=True)

    class Meta:
        model = MerchItem
        fields = [
            'name', 'description', 'category', 'defaultPrice', 'salesTaxRate',
            'disabled', 'creationDate', 'soldOut', 'numVariants',
            'variants'
        ]


class MerchOrderItemSerializer(serializers.ModelSerializer):
    item = serializers.StringRelatedField()
    item_sku = serializers.SlugRelatedField(source='item', slug_field='sku', read_only=True)
    invoiceItem = serializers.StringRelatedField(read_only=True)
    order_creationDate = serializers.SlugRelatedField(source='order', slug_field='creationDate', read_only=True)

    class Meta:
        model = MerchOrderItem
        fields = [
            'item', 'item_sku', 'quantity', 'grossTotal', 'invoiceItem',
            'order_creationDate'
        ]


class MerchOrderSerializer(serializers.ModelSerializer):
    items = MerchOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = MerchOrder
        fields = [
            'invoice', 'grossTotal', 'status', 'creationDate', 'lastModified',
            'items'
        ]
