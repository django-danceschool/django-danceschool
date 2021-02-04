from django.utils.translation import gettext_lazy as _
from django.middleware.csrf import get_token

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from collections import OrderedDict

from danceschool.core.mixins import PluginTemplateMixin

from .models import DoorRegisterMerchPluginModel, MerchItem


class DoorRegisterMerchPlugin(PluginTemplateMixin, CMSPluginBase):
    model = DoorRegisterMerchPluginModel
    name = _('Register: Merchandise')
    cache = False
    module = _('Door Register')
    render_template = 'merch/register/register_merch.html'

    fieldsets = (
        (None, {
            'fields': (
                'title', 'categories', 'separateVariants', 'displaySoldOut',
                'requireFullRegistration', 'paymentMethods',
            )
        }),
        (_('Display Options'), {
            'classes': ('collapse',),
            'fields': ('template', 'cssClasses'),
        }),
    )
    
    def populateOptions(
        self, instance, paymentMethods=[], requireFullRegistration=False, counter=0
    ):
        ''' Populate the option data for each separate merchandise item. '''
        
        if not paymentMethods:
            paymentMethods = [
                {
                    'name': None,
                    'requireFullRegistration': False,
                    'autoSubmit': False,
                },
            ]

        choices = []

        if isinstance(instance, MerchItem):
            choice_basis = instance.item_variant.all()
        else:
            choice_basis = [instance,]

        soldOutString = '({})'.format(_('Sold out')) if instance.soldOut else ''

        for method in paymentMethods:
            this_requireFull = requireFullRegistration or method['requireFullRegistration']

            for choice in choice_basis:
                choiceId = 'merchitem_{}_{}_{}'.format(choice.item.id, choice.id, counter)

                this_label = '{} {} {}'.format(
                    choice.fullName or '',
                    method['name'] or '',
                    soldOutString or '',
                ).strip()

                choices.append({
                    'label': this_label,
                    'price': choice.getPrice(),
                    'paymentMethod': method['name'],
                    'requireFullRegistration': this_requireFull,
                    'autoSubmit': method['autoSubmit'],
                    'choiceId': choiceId,
                    'itemId': choice.item.id,
                    'variantId': choice.id,
                })
                counter += 1

        return choices, counter

    def render(self, context, instance, placeholder):
        context = super().render(context, instance, placeholder)

        # Ensure that the CSRF protection cookie is set for all lists of merchandise.
        # Useful for things like buttons that go directly into the registration process.
        get_token(context.get('request'))

        listing = instance.getMerch()

        # Create an ordered dictionary of choices with all the information needed
        # for the page to render and Ajax processing to occur.
        register_choices = OrderedDict()

        # Construct a list of payment methods and associated registration rules
        # for the choices in this plugin.  If no payment methods are specified,
        # the addChoices() method will use a default.
        paymentMethods = [
            {
                'name': x.name,
                'requireFullRegistration': x.requireFullRegistration,
                'autoSubmit': x.allowAutoSubmit,
            } for x in instance.paymentMethods.all()
        ]

        choice_counter = 0
        register_choices = {}

        # Each event gets its own list of choices.
        for item in listing:
            if instance.separateVariants:
                for variant in item.item_variant.all():
                    these_options, choice_counter = self.populateOptions(variant, paymentMethods, choice_counter) 
                    register_choices['merchitemvariant_{}'.format(variant.id)] = {
                        'fullName': variant.fullName,
                        'options': these_options,
                    }
            else:
                these_options, choice_counter = self.populateOptions(item, paymentMethods, choice_counter)
                register_choices['merchitem_{}'.format(item.id)] = {
                    'fullName': item.fullName,
                    'options': these_options,
                }

        context.update({
            'item_list': listing,
            'register_choices': register_choices,
        })
        return context


plugin_pool.register_plugin(DoorRegisterMerchPlugin)
