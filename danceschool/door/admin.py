from django.contrib import admin

from .models import DoorRegister, DoorRegisterPaymentMethod


@admin.register(DoorRegister)
class DoorRegisterAdmin(admin.ModelAdmin):
    list_display = ['title', 'enabled', ]
    list_editable = ['enabled', ]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(DoorRegisterPaymentMethod)
class DoorRegisterAdmin(admin.ModelAdmin):
    list_display = ['name', 'requireFullRegistration', ]
    list_editable = ['requireFullRegistration', ]
