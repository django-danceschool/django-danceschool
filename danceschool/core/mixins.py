from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist, ImproperlyConfigured, ValidationError
from django.core.urlresolvers import reverse
from django.forms import ModelForm, ChoiceField, Media
from django.utils.translation import ugettext_lazy as _
from django.template.loader import get_template

from braces.views import GroupRequiredMixin
from cms.models import Page

from .constants import getConstant


######################################
# Add general financial variables to the
# context where appropriate.
class FinancialContextMixin(object):
    '''
    This mixin just adds the currency code and symbol to the context
    '''

    def get_context_data(self,**kwargs):
        context = {
            'currencyCode': getConstant('general__currencyCode'),
            'currencySymbol': getConstant('general__currencySymbol'),
        }
        context.update(kwargs)
        return super(FinancialContextMixin,self).get_context_data(**context)


class StaffMemberObjectMixin(object):
    '''
    For class-based views involving instructor info, this ensures that
    the object being edited is always for the instructor's own information.
    '''

    def get_object(self, queryset=None):
        if hasattr(self.request.user,'staffmember'):
            return self.request.user.staffmember
        else:
            return None


class GroupRequiredByFieldMixin(GroupRequiredMixin):
    '''
    This subclass of the GroupRequiredMixin checks if a specified model field
    identifies a group that is required.  If so, then require this group.  If
    not, then no permissions are required.  This can be used for thing like survey
    responses that are optionally restricted.
    '''
    group_required_field = ''

    def get_group_required(self):
        ''' Get the group_required value from the object '''
        this_object = self.model_object
        if hasattr(this_object,self.group_required_field):
            if hasattr(getattr(this_object,self.group_required_field),'name'):
                return [getattr(this_object,self.group_required_field).name]
        return ['']

    def check_membership(self, groups):
        ''' Allows for objects with no required groups '''
        if not groups or groups == ['']:
            return True
        if self.request.user.is_superuser:
            return True
        user_groups = self.request.user.groups.values_list("name", flat=True)
        return set(groups).intersection(set(user_groups))

    def dispatch(self, request, *args, **kwargs):
        '''
        This override of dispatch ensures that if no group is required, then
        the request still goes through without being logged in.
        '''
        self.request = request
        in_group = False
        required_group = self.get_group_required()
        if not required_group or required_group == ['']:
            in_group = True
        elif self.request.user.is_authenticated():
            in_group = self.check_membership(required_group)

        if not in_group:
            if self.raise_exception:
                raise PermissionDenied
            else:
                return redirect_to_login(
                    request.get_full_path(),
                    self.get_login_url(),
                    self.get_redirect_field_name())
        return super(GroupRequiredMixin, self).dispatch(
            request, *args, **kwargs)


class AdminSuccessURLMixin(object):
    '''
    Many admin forms should redirect to return to the Page specified in the global settings.
    This mixin is similar to the SuccessURLRedirectListMixin in django-braces.  If a
    success_list_url is specified, it reverses that URL and returns the result.  But,
    if a success_list_url is not specified, then it returns the default admin success form
    Page as specified in settings.
    '''

    success_list_url = None  # Default the success url to none

    def get_success_url(self):
        # Return the reversed success url.
        if self.success_list_url is None:
            try:
                return Page.objects.get(pk=getConstant('general__defaultAdminSuccessPage')).get_absolute_url(settings.LANGUAGE_CODE)
            except ObjectDoesNotExist:
                raise ImproperlyConfigured(
                    "%(cls)s is missing a success_list_url "
                    "name to reverse and redirect to. Define "
                    "%(cls)s.success_list_url or override "
                    "%(cls)s.get_success_url()"
                    "." % {"cls": self.__class__.__name__})
        return reverse(self.success_list_url)


class TemplateChoiceField(ChoiceField):

    def validate(self,value):
        '''
        Check for empty values, and for an existing template, but do not check if
        this is one of the initial choices provided.
        '''
        super(ChoiceField,self).validate(value)

        try:
            get_template(value)
        except:
            raise ValidationError(_('%s is not a valid template.' % value))


class PluginTemplateMixin(object):
    '''
    This mixin is for plugin classes, to override the render_template with the one provided in the template field,
    and to allow for selectable choices with the option to add a new (validated) choice.
    '''

    def render(self, context, instance, placeholder):
        ''' Permits setting of the template in the plugin instance configuration '''
        if instance and instance.template:
            self.render_template = instance.template
        return super(PluginTemplateMixin,self).render(context,instance,placeholder)

    def templateChoiceFormFactory(self,request,choices):
        class PluginTemplateChoiceForm(ModelForm):

            def __init__(self,*args,**kwargs):
                super(PluginTemplateChoiceForm, self).__init__(*args, **kwargs)

                # Handle passed parameters
                self.request = request
                all_choices = choices

                if self.instance and self.instance.template not in [x[0] for x in choices]:
                    all_choices = [(self.instance.template,self.instance.template)] + all_choices

                if self.request and self.request.user.has_perm('core.choose_custom_plugin_template'):
                    self.fields['template'] = TemplateChoiceField(choices=all_choices)
                else:
                    self.fields['template'] = ChoiceField(choices=all_choices)

            def _media(self):
                ''' Add Select2 custom behavior only if user has permissions to need it. '''
                if self.request and self.request.user.has_perm('core.choose_custom_plugin_template'):
                    return Media(
                        css={'all':('css/select2.min.css',)},
                        js=('js/select2.min.js','js/select2_newtemplate.js')
                    )
                return Media()
            media = property(_media)

        return PluginTemplateChoiceForm

    def get_form(self, request, obj=None, **kwargs):
        kwargs['form'] = self.templateChoiceFormFactory(request,self.get_template_choices())
        return super(PluginTemplateMixin, self).get_form(request, obj, **kwargs)

    def get_template_choices(self):
        if hasattr(self,'template_choices') and self.template_choices:
            return self.template_choices
        elif self.render_template:
            return [(self.render_template,self.render_template),]
        return []
