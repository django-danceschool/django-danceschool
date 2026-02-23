from rest_framework import serializers

from .models import MerchOrder, MerchItem, MerchOrderItem, MerchItemVariant


class MerchItemVariantSerializer(serializers.ModelSerializer):
    description = serializers.CharField(source='name')
    price = serializers.SerializerMethodField()
    quantity_available = serializers.IntegerField(source='currentInventory')
    model_class = serializers.CharField(default='MerchItemVariant')
    sold_out = serializers.BooleanField(source='soldOut')

    def get_price(self, obj):
        return obj.getPrice()

    class Meta:
        model = MerchItemVariant

        fields = [
            'sku', 'description', 'price', 'quantity_available', 'model_class',
            'id', 'sold_out'
        ]


class MerchItemSerializer(serializers.ModelSerializer):
    variants = MerchItemVariantSerializer(
        many=True, source='item_variant', read_only=True
    )

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
