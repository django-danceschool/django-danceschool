from django.contrib.auth.views import redirect_to_login
from django.contrib.sites.models import Site
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.db.models import (
    Case, When, F, Q, IntegerField, ExpressionWrapper
)
from django.db.models.functions import ExtractWeekDay
from django.forms import ModelForm, ChoiceField, Media
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.template.loader import get_template, render_to_string
from django.template import Template, Context
from django.template.exceptions import TemplateDoesNotExist


from braces.views import GroupRequiredMixin
from urllib.parse import quote
from six import string_types
import re
from datetime import timedelta
import logging

from .constants import getConstant, REG_VALIDATION_STR
from .tasks import sendEmail
from .registries import plugin_templates_registry, model_templates_registry
from .helpers import getReturnPage
from .signals import (
    request_discounts, apply_addons, check_voucher
)


# Define logger for this file
logger = logging.getLogger(__name__)


class EmailRecipientMixin(object):

    def email_recipient(self, subject, content, **kwargs):
        '''
        This method allows for direct emailing of an object's recipient(s)
        (default or manually specified), with both object-specific context
        provided using the get_email_context() method.  This is used, for example,
        to email an individual registrant or the recipient of an individual invoice.
        '''

        email_kwargs = {}

        for list_arg in [
            'to', 'cc', 'bcc',
        ]:
            email_kwargs[list_arg] = kwargs.pop(list_arg, []) or []
            if isinstance(email_kwargs[list_arg], string_types):
                email_kwargs[list_arg] = [email_kwargs[list_arg], ]

        for none_arg in ['attachment_name', 'attachment']:
            email_kwargs[none_arg] = kwargs.pop(none_arg, None) or None

        # Ignore any passed HTML content unless explicitly told to send as HTML
        if kwargs.pop('send_html', False) and kwargs.get('html_message'):
            email_kwargs['html_content'] = render_to_string(
                'email/html_email_base.html',
                context={'html_content': kwargs.get('html_message'), 'subject': subject}
            )

        email_kwargs['from_name'] = kwargs.pop('from_name', getConstant('email__defaultEmailName')) or \
            getConstant('email__defaultEmailName')
        email_kwargs['from_address'] = kwargs.pop('from_name', getConstant('email__defaultEmailFrom')) or \
            getConstant('email__defaultEmailFrom')

        # Add the object's default recipients if they are provided
        default_recipients = self.get_default_recipients() or []
        if isinstance(default_recipients, string_types):
            default_recipients = [default_recipients, ]

        email_kwargs['bcc'] += default_recipients

        if not (email_kwargs['bcc'] or email_kwargs['cc'] or email_kwargs['to']):
            raise ValueError(_('Email must have a recipient.'))

        # In situations where there are no context
        # variables to be rendered, send a mass email
        has_tags = re.search(r'\{\{.+\}\}', content)
        if not has_tags:
            t = Template(content)
            rendered_content = t.render(Context(kwargs))
            sendEmail(subject, rendered_content, **email_kwargs)
            return

        # Otherwise, get the object-specific email context and email
        # each recipient
        template_context = self.get_email_context() or {}
        template_context.update(kwargs)

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub(
            r'\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}',
            '',
            content
        )
        t = Template(content)
        rendered_content = t.render(Context(template_context))

        if email_kwargs.get('html_content'):
            html_content = re.sub(
                r'\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}',
                '',
                email_kwargs.get('html_content')
            )
            t = Template(html_content)
            email_kwargs['html_content'] = t.render(Context(template_context))

        sendEmail(subject, rendered_content, **email_kwargs)

    def get_email_context(self, **kwargs):
        '''
        This method can be overridden in classes that inherit from this mixin
        so that additional object-specific context is provided to the email
        template.  This should return a dictionary.  By default, only general
        financial context variables are added to the dictionary, and kwargs are
        just passed directly.

        Note also that it is in general not a good idea for security reasons
        to pass model instances in the context here, since these methods can be
        accessed by logged in users who use the SendEmailView.  So, In the default
        models of this app, the values of fields and properties are passed
        directly instead.
        '''
        context = kwargs
        context.update({
            'currencyCode': getConstant('general__currencyCode'),
            'currencySymbol': getConstant('general__currencySymbol'),
            'businessName': getConstant('contact__businessName'),
            'site_url': getConstant('email__linkProtocol') + '://' + Site.objects.get_current().domain,
        })
        return context

    def get_default_recipients(self):
        '''
        This method should be overridden in each class that inherits from this
        mixin, so that the email addresses to whom the email should be sent are
        included on the BCC line.  This should return a list.
        '''
        return []


######################################
# Add general financial variables to the
# context where appropriate.
class FinancialContextMixin(object):
    '''
    This mixin just adds the currency code and symbol to the context
    '''

    def get_context_data(self, **kwargs):
        context = {
            'currencyCode': getConstant('general__currencyCode'),
            'currencySymbol': getConstant('general__currencySymbol'),
            'businessName': getConstant('contact__businessName'),
        }
        context.update(kwargs)
        return super().get_context_data(**context)


class StaffMemberObjectMixin(object):
    '''
    For class-based views involving instructor info, this ensures that
    the object being edited is always for the instructor's own information.
    '''

    def get_object(self, queryset=None):
        if hasattr(self.request.user, 'staffmember'):
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
        if hasattr(this_object, self.group_required_field):
            if hasattr(getattr(this_object, self.group_required_field), 'name'):
                return [getattr(this_object, self.group_required_field).name]
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
        if self.success_list_url:
            return '%s?redirect_url=%s' % (
                reverse('submissionRedirect'), quote(self.success_list_url)
            )
        else:
            # If no URL specified, then the redirect view will use the default
            # from the runtime preferences.
            return reverse('submissionRedirect')


class TemplateChoiceField(ChoiceField):

    def validate(self, value):
        '''
        Check for empty values, and for an existing template, but do not check if
        this is one of the initial choices provided.
        '''
        super(ChoiceField, self).validate(value)

        try:
            get_template(value)
        except TemplateDoesNotExist:
            raise ValidationError(_('%s is not a valid template.' % value))


class PluginTemplateMixin(object):
    '''
    This mixin is for plugin classes, to override the render_template with the
    one provided in the template field, and to allow for selectable choices with
    the option to add a new (validated) choice.
    '''

    def render(self, context, instance, placeholder):
        ''' Permits setting of the template in the plugin instance configuration '''
        if instance and instance.template:
            self.render_template = instance.template
        return super().render(context, instance, placeholder)

    def templateChoiceFormFactory(self, request, choices):
        class PluginTemplateChoiceForm(ModelForm):

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                # Handle passed parameters
                self.request = request
                all_choices = choices

                if self.instance and self.instance.template not in [x[0] for x in choices]:
                    all_choices = [(self.instance.template, self.instance.template)] + all_choices

                if self.request and self.request.user.has_perm('core.choose_custom_plugin_template'):
                    self.fields['template'] = TemplateChoiceField(choices=all_choices)
                else:
                    self.fields['template'] = ChoiceField(choices=all_choices)

            def _media(self):
                ''' Add Select2 custom behavior only if user has permissions to need it. '''
                if self.request and self.request.user.has_perm('core.choose_custom_plugin_template'):
                    return Media(
                        css={'all': ('autocomplete_light/select2.css',)},
                        js=(
                            'admin/js/vendor/jquery/jquery.min.js',
                            'admin/js/jquery.init.js',
                            'autocomplete_light/select2.js',
                            'js/select2_newtemplate.js',
                        )
                    )
                return Media()
            media = property(_media)

        return PluginTemplateChoiceForm

    def get_form(self, request, obj=None, **kwargs):
        kwargs['form'] = self.templateChoiceFormFactory(request, self.get_template_choices())
        return super().get_form(request, obj, **kwargs)

    def get_template_choices(self):
        # If templates are explicitly specified, use those
        if hasattr(self, 'template_choices') and self.template_choices:
            return self.template_choices

        # If templates are registered, use those
        registered = [
            x for x in plugin_templates_registry.values() if
            getattr(x, 'plugin', None) in [z.__name__ for z in self.__class__.__mro__]
        ]
        if registered:
            return [
                (x.template_name, getattr(x, 'description', None) or x.template_name)
                for x in registered
            ]

        # If just one template is specified, use that
        if getattr(self, 'render_template', None):
            return [(self.render_template, self.render_template), ]

        # No choices to report
        return []


class ModelTemplateMixin(object):
    '''
    This mixin is for models with a selectable custom template for individual
    page rendering.  It is primarily used by the Event model and its children
    such as PublicEvent and Series for custom event page templates.  The mixin
    is used to augment the admin classes for these model classes.
    '''

    def get_template_choices(self, model):
        # If templates are explicitly specified, use those
        if hasattr(self, 'template_choices') and self.template_choices:
            return self.template_choices

        # If templates are registered, use those.
        registered = [
            x for x in model_templates_registry.values() if
            issubclass(model, getattr(x, 'model', None))
        ]
        if registered:
            return [
                (x.template_name, getattr(x, 'description', None) or x.template_name)
                for x in registered
            ]

        # If just one template is specified, use that
        if getattr(self, 'render_template', None):
            return [(self.render_template, self.render_template), ]

        # No choices to report
        return []


class EventOrderMixin(object):
    '''
    Various registration pages require that Event querysets be ordered based on the value
    of the constant registration__orgRule (e.g. by session, by month, the combination of the two,
    or by weekday).  Rather than placing this ordering logic in Python, this mixin produces a SQL
    compliant order parameter that can be added as an annotation to any queryset of Events and then
    used to order that queryset.  Since there may be multiple ordering parameters, the function returns
    a tuple.  The first value of the tuple is an ordering parameter that ensures that NULL values
    are always sorted last along both dimensions.  It should always be used in ascending order.
    The second value of the tuple is the primary sort dimension, which can be used ascending or descending
    in the view.  When there is only one ordering parameter needed, the third value of the tuple is None,
    otherwise it passes the second parameter.
    '''

    def get_annotations(self):
        '''
        This method gets the annotations for the queryset.  Unlike get_ordering() below, it
        passes the actual Case() and F() objects that will be evaluated with the queryset, returned
        in a dictionary that is compatible with get_ordering().
        '''
        rule = getConstant('registration__orgRule')

        # Initialize with null values that get filled in based on the logic below.
        annotations = {
            'nullParam': Case(default_value=None, output_field=IntegerField()),
            'paramOne': Case(default_value=None, output_field=IntegerField()),
            'paramTwo': Case(default_value=None, output_field=IntegerField()),
        }

        if rule == 'SessionFirst':
            annotations.update({
                'nullParam': Case(
                    When(session__startTime__isnull=False, then=0),
                    When(month__isnull=False, then=1),
                    default_value=2,
                    output_field=IntegerField()
                ),
                'paramOne': F('session__startTime'),
                'paramTwo': ExpressionWrapper(12 * F('year') + F('month'), output_field=IntegerField()),
            })
        elif rule == 'SessionAlphaFirst':
            annotations.update({
                'nullParam': Case(
                    When(session__name__isnull=False, then=0),
                    When(month__isnull=False, then=1),
                    default_value=2,
                    output_field=IntegerField()
                ),
                'paramOne': F('session__name'),
                'paramTwo': ExpressionWrapper(12 * F('year') + F('month'), output_field=IntegerField()),
            })
        elif rule == 'Month':
            annotations.update({
                'nullParam': Case(
                    When(month__isnull=False, then=0),
                    default_value=1,
                    output_field=IntegerField()
                ),
                'paramOne': ExpressionWrapper(12*F('year') + F('month'), output_field=IntegerField()),
            })
        elif rule == 'Session':
            annotations.update({
                'nullParam': Case(
                    When(session__startTime__isnull=False, then=0),
                    default_value=1,
                    output_field=IntegerField()
                ),
                'paramOne': F('session__startTime'),
            })
        elif rule == 'SessionAlpha':
            annotations.update({
                'nullParam': Case(
                    When(session__name__isnull=False, then=0),
                    default_value=1,
                    output_field=IntegerField()
                ),
                'paramOne': F('session__name'),
            })
        elif rule == 'SessionMonth':
            annotations.update({
                'nullParam': Case(
                    When(Q(session__startTime__isnull=False) & Q(month__isnull=False), then=0),
                    When(Q(session__startTime__isnull=True) & Q(month__isnull=False), then=1),
                    When(Q(session__startTime__isnull=False) & Q(month__isnull=True), then=2),
                    default_value=3,
                    output_field=IntegerField()
                ),
                'paramOne': ExpressionWrapper(12 * F('year') + F('month'), output_field=IntegerField()),
                'paramTwo': F('session__startTime'),
            })
        elif rule == 'SessionAlphaMonth':
            annotations.update({
                'nullParam': Case(
                    When(Q(session__name__isnull=False) & Q(month__isnull=False), then=0),
                    When(Q(session__name__isnull=True) & Q(month__isnull=False), then=1),
                    When(Q(session__name__isnull=False) & Q(month__isnull=True), then=2),
                    default_value=3,
                    output_field=IntegerField()
                ),
                'paramOne': ExpressionWrapper(12*F('year') + F('month'), output_field=IntegerField()),
                'paramTwo': F('session__name'),
            })
        elif rule == 'Weekday':
            annotations.update({
                'nullParam': Case(
                    When(startTime__week_day__isnull=False, then=0),
                    default_value=1,
                    output_field=IntegerField()
                ),
                'paramOne': ExtractWeekDay('startTime'),
            })
        elif rule == 'MonthWeekday':
            annotations.update({
                'nullParam': Case(
                    When(Q(month__isnull=False) & Q(startTime__week_day__isnull=False), then=0),
                    default_value=1,
                    output_field=IntegerField()
                ),
                'paramOne': ExpressionWrapper(12*F('year') + F('month'), output_field=IntegerField()),
                'paramTwo': ExtractWeekDay('startTime'),
            })

        return annotations

    def get_ordering(self, reverseTime=False):
        '''
        This method provides the tuple for ordering of querysets.  However, this will only
        work if the annotations generated by the get_annotations() method above have been
        added to the queryset.  Otherwise, the use of this ordering tuple will fail because
        the appropriate column names will not exist to sort with.
        '''

        # Reverse ordering can be optionally specified in the view class definition.
        reverseTime = getattr(self, 'reverse_time_ordering', reverseTime)
        timeParameter = '-startTime' if reverseTime is True else 'startTime'
        return ('nullParam', 'paramOne', 'paramTwo', timeParameter)


class SiteHistoryMixin(object):
    '''
    This mixin provides convenience methods for updating session data to keep track of
    the logical place in the registration process (e.g. registration page, viewing of
    event registrations, etc.) that was last accessed, so that successful form submissions
    can automatically return to a logical place.
    '''

    def set_return_page(self, namedUrl, pageName='', **kwargs):
        expiry = timezone.now() + timedelta(minutes=getConstant('registration__sessionExpiryMinutes'))
        siteHistory = self.request.session.get('SITE_HISTORY', {})

        updates = {
            'returnPage': (namedUrl, kwargs),
            'returnPageName': str(pageName),
            'expiry': expiry.strftime('%Y-%m-%dT%H:%M:%S%z'),
        }

        if list(siteHistory.get('returnPage', [])) != list(updates['returnPage']):
            updates.update({
                'priorPage': siteHistory.get('returnPage', (None, {})),
                'priorPageName': siteHistory.get('returnPageName', ''),
            })

        siteHistory.update(updates)
        self.request.session['SITE_HISTORY'] = siteHistory

    def get_return_page(self, prior=False):
        ''' This is just a wrapper for the getReturnPage helper function. '''
        siteHistory = self.request.session.get('SITE_HISTORY', {})
        return getReturnPage(siteHistory, prior=prior)


class RegistrationAdjustmentsMixin(object):
    '''
    This mixin provides convenience methods for the standard request of discounts,
    vouchers, and addons that happens in each step of the registration process.
    These methods reference a Registration object, but they do not modify
    it; that should be done in the view itself.
    '''

    # This should be overriden by subclasses where the customer information has
    # been finalized so that customer-specific discounts and addons can be found.
    customers_final = False

    def getVoucher(
        self, voucherId, invoice, prior_adjustment=0, first_name=None, last_name=None, email=None
    ):
        '''
        This method looks for a voucher with the associated voucher ID, it checks
        for eligibility, and it returns an updated dictionary
        '''

        from danceschool.core.models import Customer

        first_name = first_name or invoice.firstName
        last_name = last_name or invoice.lastName
        email = email or invoice.email

        # This will only find a customer if all three are specified.
        customer = Customer.objects.filter(
            first_name=first_name,
            last_name=last_name,
            email=email
        ).first()

        voucher_response = check_voucher.send(
            sender=RegistrationAdjustmentsMixin, voucherId=voucherId,
            customer=customer, validateCustomer=(customer is not None),
            invoice=invoice
        )

        voucher_response = [x[1] for x in voucher_response if len(x) > 1 and x[1]]
        if (len(voucher_response) > 1):
            # This shouldn't happen
            logger.error('Received multiple voucher responses from signal handler.')
            return {}
        elif voucher_response:
            subtotal = invoice.total + prior_adjustment
            total = subtotal

            if (
                voucher_response[0].get('status', None) == 'valid' and
                voucher_response[0].get('available', 0) > 0
            ):
                if voucher_response[0].get('beforeTax') is False:
                    subtotal += invoice.taxes + invoice.adjustments

                total = max(
                    0, subtotal - voucher_response[0].get('available', 0)
                )

            return {
                'voucherId': voucher_response[0].get('id', None),
                'voucherName': voucher_response[0].get('name', None),
                'voucherAmount': subtotal - total,
                'beforeTax': voucher_response[0].get('beforeTax')
            }
        else:
            return {}

    def getDiscounts(self, invoice, registration=None, initial_price=None):
        '''
        This method takes a registration and an initial price, and it returns
        a tuple that contains all the information needed to process any
        applicable discounts.
        '''

        from danceschool.core.models import Registration

        if not registration:
            registration = Registration.objects.filter(invoice=invoice).first()
        if not initial_price and registration:
            initial_price = registration.grossTotal
        else:
            initial_price = invoice.grossTotal

        # The discounts app only applies first-time customer discounts in the
        # final stage, in case the customer information changes.  So, we need
        # to let it know if this mixin is attached to RegistrationSummaryView.
        sender = RegistrationAdjustmentsMixin

        # If the discounts app is enabled, then the return value to this signal
        # will contain information on the discounts to be applied, as well as
        # the total price of discount-ineligible items to be added to the
        # price.  These should be in the form of a named tuple such as the
        # DiscountApplication namedtuple defined in the discounts app, with
        # 'items' and 'ineligible_total' keys.
        discount_responses = request_discounts.send(
            sender=sender,
            registration=registration,
            invoice=invoice,
            customer_final=self.customers_final
        )
        discount_responses = [x[1] for x in discount_responses if len(x) > 1 and x[1]]

        # This signal handler is designed to handle a single non-null response,
        # and that response must be in the form of a list of namedtuples, each
        # with a with a code value, a net_price value, and a discount_amount value
        # (as with the DiscountInfo namedtuple provided by the DiscountCombo class). If more
        # than one response is received, then the one with the minumum net price is applied
        discount_codes = []
        discounted_total = initial_price
        total_discount_amount = 0

        try:
            if discount_responses:
                discount_responses.sort(
                    key=lambda k:
                    min(
                        [getattr(x, 'net_price', initial_price) for x in k.items] +
                        [initial_price]
                    ) if k and hasattr(k, 'items') else initial_price
                )
                discount_codes = getattr(discount_responses[0], 'items', [])
                if discount_codes:
                    discounted_total = min(
                        [getattr(x, 'net_price', initial_price) for x in discount_codes]
                    ) + getattr(discount_responses[0], 'ineligible_total', 0)
                    total_discount_amount = initial_price - discounted_total
        except (IndexError, TypeError) as e:
            logger.error('Error in applying discount responses: %s' % e)

        return (discount_codes, total_discount_amount)

    def getAddons(self, invoice, registration=None):
        '''
        Return a list of any free add-on items that should be applied.
        '''

        addon_responses = apply_addons.send(
            sender=RegistrationAdjustmentsMixin,
            invoice=invoice,
            registration=registration,
            customer_final=self.customers_final
        )
        addons = []
        for response in addon_responses:
            try:
                if response[1]:
                    addons += list(response[1])
            except (IndexError, TypeError) as e:
                logger.error('Error in applying addons: %s' % e)

        return addons


class ReferralInfoMixin(object):
    '''
    Gets marketing ids and voucher ids from the URL kwargs or HTTP GET parameters
    and add them to the session data.
    '''

    def get(self, request, *args, **kwargs):

        # Voucher IDs are used for the referral program.
        # Marketing IDs are used for tracking click-through registrations.
        # They are put directly into session data immediately.
        voucher_id = kwargs.pop('voucher_id', None)
        marketing_id = kwargs.pop('marketing_id', None)

        # GET parameters are also usable, but the URL pattern takes precedence.
        if not voucher_id:
            voucher_id = request.GET.get('referral', None)
        if not marketing_id:
            marketing_id = request.GET.get('id', None)

        # Ignore voucher and marketing IDs that contain disallowed characters.
        pattern = re.compile(r'^[a-zA-Z\-_0-9]+$')
        if (voucher_id and not pattern.match(voucher_id)):
            voucher_id = None
        if (marketing_id and not pattern.match(marketing_id)):
            marketing_id = None

        if marketing_id or voucher_id:
            ''' Put these things into the session data. '''
            regSession = self.request.session.get(REG_VALIDATION_STR, {})
            regSession['voucher_id'] = voucher_id or regSession.get('voucher_id', None)
            regSession['marketing_id'] = marketing_id or regSession.get('marketing_id', None)
            self.request.session[REG_VALIDATION_STR] = regSession

        return super().get(request, *args, **kwargs)
