# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from django.template.loader import get_template
from .utils.sys import isPreliminaryRun


class CoreAppConfig(AppConfig):
    name = 'danceschool.core'
    verbose_name = _('Core School Functions')

    def ready(self):
        from django.db import connection
        from .constants import getConstant, updateConstant

        # Ensure that signal handlers are loaded
        from . import handlers

        if 'core_emailtemplate' in connection.introspection.table_names() and not isPreliminaryRun():

            EmailTemplate = self.get_model('EmailTemplate')

            success_template_id = getConstant('email__registrationSuccessTemplateID') or 0
            invoice_template_id = getConstant('email__invoiceTemplateID') or 0

            if success_template_id <= 0:
                initial_template = get_template('email/registration_success.html')
                with open(initial_template.origin.name,'r') as infile:
                    content = infile.read()
                    infile.close()

                new_success_template, created = EmailTemplate.objects.get_or_create(
                    name=_('Registration Confirmation Email'),
                    defaults={

                        'subject':_('Registration Confirmation'),
                        'content': content or '',
                        'defaultCC': '',
                        'hideFromForm': True,}
                )
                # Update constant and fail silently
                updateConstant('email__registrationSuccessTemplateID', new_success_template.id, True)

            if invoice_template_id <= 0:
                initial_template = get_template('email/invoice_initial.html')
                with open(initial_template.origin.name,'r') as infile:
                    content = infile.read()
                    infile.close()

                new_invoice_template, created = EmailTemplate.objects.get_or_create(
                    name=_('Registration Invoice Email'),
                    defaults={
                        'subject': _('Registration Invoice'),
                        'content': content or '',
                        'defaultCC': '',
                        'hideFromForm': True,}
                )
                # Update constant and fail silently
                updateConstant('email__invoiceTemplateID',new_invoice_template.id,True)

        if 'core_eventstaffcategory' in connection.introspection.table_names() and not isPreliminaryRun():
            EventStaffCategory = self.get_model('EventStaffCategory')

            # Name, preference key, and defaultRate
            new_staff_cats = [
                (_('Class Instruction'),'general__eventStaffCategoryInstructorID',0),
                (_('Assistant Class Instruction'),'general__eventStaffCategoryAssistantID',0),
                (_('Substitute Teaching'),'general__eventStaffCategorySubstituteID',0),
                (_('Other Staff'),'general__eventStaffCategoryOtherID',0),
            ]

            for cat in new_staff_cats:
                if (getConstant(cat[1]) or 0) <= 0:
                    new_cat, created = EventStaffCategory.objects.get_or_create(
                        name=cat[0],
                        defaults={'defaultRate': cat[2]},
                    )
                    # Update constant and fail silently
                    updateConstant(cat[1],new_cat.id,True)
