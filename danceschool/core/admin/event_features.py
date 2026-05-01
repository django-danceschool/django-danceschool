from django.contrib import admin
from django.forms import ModelForm, ChoiceField
from django.utils.translation import gettext_lazy as _

from cms.admin.placeholderadmin import FrontendEditableAdminMixin
from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter

from ..models import ClassDescription, DanceType, DanceTypeLevel, Series
from ..constants import getConstant
from ..mixins import ModelTemplateMixin


class ClassDescriptionAdminForm(ModelTemplateMixin, ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Allow the user to choose from the registered template choices.
        self.fields['template'] = ChoiceField(
            choices=self.get_template_choices(Series), required=True,
            initial=getConstant('general__defaultSeriesPageTemplate')
        )

    class Meta:
        model = ClassDescription
        exclude = []


@admin.register(ClassDescription)
class ClassDescriptionAdmin(FrontendEditableAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'danceTypeLevel', ]
    list_filter = (('danceTypeLevel', RelatedDropdownFilter),)
    search_fields = ('title', 'description',)
    prepopulated_fields = {"slug": ("title", )}
    form = ClassDescriptionAdminForm


# These admin classes are registered but need nothing additional
admin.site.register(DanceType)
admin.site.register(DanceTypeLevel)
