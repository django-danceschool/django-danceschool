from django.contrib import admin

from .models import Register, RegisterPaymentMethod


@admin.register(Register)
class RegisterAdmin(admin.ModelAdmin):
    list_display = ['title', 'enabled', ]
    list_editable = ['enabled', ]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(RegisterPaymentMethod)
class RegisterPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'requireFullRegistration', ]
    list_editable = ['requireFullRegistration', ]
