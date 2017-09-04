from django.contrib import admin

from .models import InstructorPrivateLessonDetails, InstructorAvailabilitySlot

from danceschool.core.models import Instructor


class InstructorPrivateLessonDetailsInline(admin.TabularInline):
    model = InstructorPrivateLessonDetails
    extra = 0

    # Prevents adding new voucher uses without going through
    # the standard registration process
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstructorAvailabilitySlot)
class InstructorAvailabilitySlotAdmin(admin.ModelAdmin):
    exclude = []


admin.site._registry[Instructor].inlines.insert(0,InstructorPrivateLessonDetailsInline)
