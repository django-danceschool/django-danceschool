from django.db import models
from django.db.models import Value, Count
from django.utils.translation import gettext_lazy as _

from math import ceil
import logging
import json

from cms.models.pluginmodel import CMSPlugin
from cms.models.fields import PlaceholderField

from danceschool.core.models import (
    Event, PublicEvent, Series, RegisterEventLimitedModel
)

# Define logger for this file
logger = logging.getLogger(__name__)


class Register(models.Model):
    '''
    An organization may require more than one at-the-door register page, depending on its needs.
    Each instance of this model provides a separate CMS placeholder for an at-the-door register.
    '''

    title = models.CharField(
        _('Register title'),
        help_text=_(
            'Since there may be more than one at-the-door registration page, give each one a title '
        ),
        max_length=200,
    )

    slug = models.SlugField(
        _('Slug'),
        max_length=50,
        help_text=_('Register pages are accessed by a URL based on this slug.'),
    )

    enabled = models.BooleanField(
        _('Enable this register page'), default=True, blank=True
    )

    placeholder = PlaceholderField('register_placeholder')

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _('At-the-door register')
        verbose_name_plural = _('At-the-door registers')
        ordering = ('title',)


class RegisterPaymentMethod(models.Model):
    '''
    At the door, it is often desirable to have separate buttons for different potential
    payment methods, and different registration logic for each (e.g. cash vs. credit).
    Each instance of the RegisterEventPluginModel can optionally specify the
    particular instances of this model (payment methods) that have separate buttons.
    '''

    name = models.CharField(_('Method name'), max_length=50)

    requireFullRegistration = models.BooleanField(
        _('Is full registration (name and email) always required for this method?'),
        default=False,
        help_text=_(
            'If checked, then whenever this payment method is used, the ' +
            'student information form will be required. The full registration ' +
            'process may also be required by a particular register plugin ' +
            'or registration choice.'
        )
    )

    allowAutoSubmit = models.BooleanField(
        _('Auto-submission'),
        default=False,
        help_text=_(
            'If the payatdoor app is enabled, this setting can be used to ' +
            'permit automatic recording of non-electronic door payments to ' +
            'speed the registration process. ' +
            'For auto-submission to work, the name of this payment method ' +
            'must match the name of a payment method in the setting ' +
            'ATTHEDOOR_PAYMENTMETHOD_CHOICES for the payatdoor app. ' +
            'Valid defaults are Cash and Check.'
        ),
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Payment method')
        verbose_name_plural = _('Payment methods')
        ordering = ('name',)


class RegisterEventPluginModel(RegisterEventLimitedModel):
    '''
    This model is typically used to configure upcoming event listings, but it can
    be customized to a variety of purposes using custom templates, etc.
    '''

    title = models.CharField(
        _('Custom list title'), max_length=250, default=_('Upcoming Events'),
        blank=True
    )

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to surrounding &lt;div&gt;')
    )
    template = models.CharField(_('Plugin template'), max_length=250, null=True, blank=True)

    requireFullRegistration = models.BooleanField(
        _('Require full registration'), blank=True, default=True,
        help_text=_(
            'If checked, then the user will be sent to the second page of the ' +
            'registration process to provide name and email. Particular payment ' +
            'methods may also require the full registration process.'
        )
    )

    paymentMethods = models.ManyToManyField(
        RegisterPaymentMethod,
        verbose_name=_('Payment Methods'),
        help_text=_(
            'If you would like separate buttons for individual payment methods, ' +
            'then select them here.  If left blank, a single button will be shown ' +
            'and no payment method will be specified.'
        ),
        blank=True,
    )

    def copy_relations(self, oldinstance):
        super().copy_relations(oldinstance)

        # Delete existing choice instances to avoid duplicates, then duplicate
        # choice instances from the old plugin instance.  Following Django CMS
        # documentation.
        self.registereventpluginchoice_set.all().delete()

        for choice in oldinstance.registereventpluginchoice_set.all():
            choice.pk = None
            choice.eventPlugin = self
            choice.save()

    def get_short_description(self):
        desc = self.title or ''
        choices = getattr(self.get_plugin_class(), 'template_choices', [])
        choice_name = [x[1] for x in choices if x[0] == self.template]
        if choice_name:
            if desc:
                desc += ': %s' % choice_name[0]
            else:
                desc = choice_name[0]
        elif self.template:
            if desc:
                desc += ': %s' % self.template
            else:
                desc = self.template
        return desc or self.id

    def save(self, *args, **kwargs):
        '''
        New plugin instances have, by default, the standard registration buttons
        broken out by role and nothing else.
        '''

        # cms.api.add_plugin() assigns the PK via set_base_attr() before
        # calling save(), so checking ``not self.pk`` alone is not reliable.
        # We also check whether any choices already exist so that ordinary
        # re-saves of existing instances do not create spurious duplicates.
        needs_default_choice = not self.registereventpluginchoice_set.exists() if self.pk else True
        super().save(*args, **kwargs)
        if needs_default_choice:
            RegisterEventPluginChoice.objects.create(
                eventPlugin=self,
            )

    class Meta:
        permissions = (
            (
                'choose_custom_plugin_template',
                _('Can enter a custom plugin template for plugins with selectable template.')
            ),
        )


class RegisterGuestSearchPluginModel(RegisterEventLimitedModel):
    '''
    For checking in guests, we need to limit the set of events that they
    may be checked into.  This doesn't need anything more than general event
    limitations.
    '''
    pass


class PublicRegisterNavPluginModel(CMSPlugin):
    '''
    Model for the public register navigation bar plugin.  The plugin renders
    a sticky Bootstrap navbar whose links are populated by JavaScript after
    page load by reading the data-section-title attributes of
    .public-register-section elements (produced by PublicRegisterEventPlugin).

    No sections are stored here; this is purely a display/UX plugin.
    '''

    title = models.CharField(
        _('Navbar brand text'), max_length=200, blank=True, default='',
        help_text=_(
            'Optional text displayed at the left edge of the navbar. '
            'Leave blank to show navigation links only.'
        )
    )

    def __str__(self):
        return self.title or str(_('Public register navigation bar'))

    class Meta:
        verbose_name = _('Public register navigation bar')
        verbose_name_plural = _('Public register navigation bars')


class PublicRegisterEventPluginModel(RegisterEventLimitedModel):
    '''
    CMS plugin model for the public-facing registration page.  Like
    RegisterEventPluginModel, it provides filterable event listings, but
    without at-the-door-specific options (payment methods,
    requireFullRegistration, autoCheckIn).

    Unlike RegisterEventPluginModel it does not expose at-the-door-specific
    options (payment methods, requireFullRegistration, autoCheckIn).
    registrationOpenLimit is exposed in the admin and defaults to 'O' so that
    staff can optionally create a section that surfaces closed/ongoing events.
    '''

    title = models.CharField(
        _('Section title'), max_length=250, default=_('Upcoming Events'), blank=True
    )

    cssClasses = models.CharField(
        _('Custom CSS classes'), max_length=250, null=True, blank=True,
        help_text=_('Classes are applied to the surrounding &lt;div&gt;')
    )

    template = models.CharField(
        _('Plugin template'), max_length=250, null=True, blank=True
    )

    def copy_relations(self, oldinstance):
        super().copy_relations(oldinstance)
        self.publicregistereventpluginchoice_set.all().delete()
        for choice in oldinstance.publicregistereventpluginchoice_set.all():
            choice.pk = None
            choice.eventPlugin = self
            choice.save()

    def get_short_description(self):
        return self.title or self.id

    def save(self, *args, **kwargs):
        needs_default_choice = (
            not self.publicregistereventpluginchoice_set.exists() if self.pk else True
        )
        super().save(*args, **kwargs)
        if needs_default_choice:
            PublicRegisterEventPluginChoice.objects.create(eventPlugin=self)

    class Meta:
        permissions = (
            (
                'choose_custom_public_plugin_template',
                _('Can enter a custom plugin template for public register plugins.')
            ),
        )


class PublicRegisterEventPluginChoice(models.Model):
    '''
    Configuration for how PublicRegisterEventPluginModel renders registration
    inputs.  Each instance produces a labelled number input per available role
    (or a single "General admission" input when no roles are defined).

    The data JSONField is stored server-side only and is never sent to the
    browser, so it cannot be tampered with by users.  It will be attached to
    the resulting EventRegistration by a signal handler (to be implemented).
    '''

    SOLDOUT_CHOICES = [
        ('D', _('Display with sold-out label')),
        ('H', _('Hide sold-out choices')),
    ]

    eventPlugin = models.ForeignKey(
        PublicRegisterEventPluginModel,
        verbose_name=_('Plugin'),
        on_delete=models.CASCADE,
    )

    optionLabel = models.CharField(
        _('Label prefix'), max_length=100, blank=True, default='',
        help_text=_(
            'Optional prefix shown before the role name, e.g. "Sign up as". '
            'Leave blank to show only the role name.'
        )
    )

    soldOutRule = models.CharField(
        _('Rule for sold-out choices'), max_length=1, default='D',
        choices=SOLDOUT_CHOICES,
    )

    data = models.JSONField(
        _('Additional data attached to registrations'), default=dict, blank=True,
        help_text=_(
            'Custom JSON stored with each registration produced by this choice. '
            'This value is kept server-side and is never transmitted through '
            'the browser, so it cannot be modified by users.'
        )
    )

    order = models.PositiveSmallIntegerField(default=0, blank=False, null=False)

    def addChoices(self, event):
        '''
        Return a list of choice dicts for the given event — one entry per
        available role, or a single "General admission" entry when the event
        has no roles defined.  Each dict carries only the attributes needed
        to render a number input and, at checkout time, to construct a
        CartView item.  The data field is deliberately excluded from the
        output so it is never exposed to the client.

        Registration counts and sold-out status are computed here in two
        queries (one for EventRole records, one for registration counts) to
        avoid N+1 queries when the template renders multiple roles.
        '''
        choices = []

        # --- Step 1: build roles_data with capacity in 1–2 queries -----------
        # Fetch all EventRole records for this event at once.
        event_roles = list(
            event.eventrole_set.filter(capacity__gt=0).select_related('role')
        )

        if event_roles:
            roles_data = [
                {
                    'name': er.role.name,
                    'id': er.role.id,
                    'capacity': er.capacity,
                }
                for er in event_roles
            ]
        elif isinstance(event, Series):
            # Fall back to DanceType roles with evenly-divided capacity.
            try:
                dtype_roles = list(
                    event.classDescription.danceTypeLevel.danceType.roles.all()
                )
            except Exception:
                dtype_roles = []
            if dtype_roles:
                per_role_cap = ceil(event.capacity / len(dtype_roles))
                roles_data = [
                    {'name': r.name, 'id': r.id, 'capacity': per_role_cap}
                    for r in dtype_roles
                ]
            else:
                roles_data = []
        else:
            roles_data = []

        # --- Step 2: fetch registration counts in a single query -------------
        if roles_data:
            count_rows = event.eventregistration_set.filter(
                cancelled=False, dropIn=False, registration__final=True
            ).values('role_id').annotate(count=Count('id'))
            count_map = {row['role_id']: row['count'] for row in count_rows}
        else:
            # General admission — count all non-cancelled, non-drop-in regs.
            roles_data = [{'name': None, 'id': None, 'capacity': event.capacity}]
            count_map = {None: event.eventregistration_set.filter(
                cancelled=False, dropIn=False, registration__final=True
            ).count()}

        # --- Step 3: build choice dicts --------------------------------------
        for i, role in enumerate(roles_data):
            num_registered = count_map.get(role['id'], 0)
            capacity = role['capacity'] or 0
            sold_out = num_registered >= capacity

            if sold_out and self.soldOutRule == 'H':
                continue

            label = ' '.join(filter(None, [
                self.optionLabel,
                role['name'] or str(_('General admission')),
            ]))

            choices.append({
                'label': label,
                'price': event.pricingTier.onlinePrice if event.pricingTier else 0,
                'roleName': role['name'],
                'roleId': role['id'],
                'numRegistered': num_registered,
                'capacity': capacity,
                'soldOut': sold_out,
                'choiceId': 'pubchoice_{}_{}_{}'.format(event.id, self.id, i),
            })

        return choices

    class Meta:
        ordering = ['order']


class RegisterEventPluginChoice(models.Model):
    '''
    Individual register sections may have custom rules for the types and display
    of options that they permit.  This sortable model holds rules for the type
    of additional options that are enabled within each instance of
    RegisterEventPluginModel.
    '''
    OPTION_TYPE_CHOICES = [
        ('G', _('Standard registration')),
        ('D', _('Register as a drop-in')),
        ('S', _('Register with student designation')),
    ]
    OPTION_LOCATION_CHOICES = [
        ('P', _('Primary choice')),
        ('A', _('Additional choice')),
    ]
    OPEN_CHOICES = [
        ('O', _('Open for registration only')),
        ('C', _('Closed for registration only')),
        ('B', _('Both open and closed events')),
    ]
    SOLDOUT_CHOICES = [
        ('D', _('Display with label')),
        ('A', _('Move to additional choice drop-down')),
        ('H', _('Hide sold out choices')),
    ]

    eventPlugin = models.ForeignKey(
        RegisterEventPluginModel,
        verbose_name=_('Plugin'),
        on_delete=models.CASCADE,
    )

    optionType = models.CharField(
        _('Option type'), max_length=1, choices=OPTION_TYPE_CHOICES,
        default='G',
    )

    optionLabel = models.CharField(
        _('Override option label'), max_length=100, null=True, blank=True,
        help_text=_('Leave blank for default labeling to be applied.')
    )

    optionLocation = models.CharField(
        _('Option location'), max_length=1, choices=OPTION_LOCATION_CHOICES,
        default='P',
        help_text=_(
            'By default, primary choices receive their own button, while ' +
            'additional choices are included in a drop-down menu.'
        )
    )

    byRole = models.BooleanField(
        _('Separate choices for each role'), blank=True, default=True,
        help_text=_(
            'If disabled, then this option will not be broken out by role. ' +
            'It is not recommended to do this except for drop-in ' +
            'registrations, because the default registration workflow does ' +
            'not allow for later selection of roles.'
        )
    )

    byPaymentMethod = models.BooleanField(
        _('Separate choices for each payment method'), blank=True, default=False,
        help_text=_(
            'If enabled, then this option will be broken out by the payment ' +
            'methods specified for this plugin. If no payment methods are ' +
            'specified, then this choice will have no effect. It is useful to ' +
            'enable this option when different payment methods require ' +
            'different registration logic.'
        )
    )

    requireFullRegistration = models.BooleanField(
        _('Require full registration'), blank=True, default=True,
        help_text=_(
            'If checked, then the user will be sent to the second page of the ' +
            'registration process to provide name and email. Particular payment ' +
            'methods or plugins may also require the full registration process ' +
            'and can override this option.'
        )
    )

    registrationOpenDisplay = models.CharField(
        _('Display if open/closed for registration only'), max_length=1,
        choices=OPEN_CHOICES, default='B'
    )

    soldOutRule = models.CharField(
        _('Rule for sold out choices'), max_length=1, default='D',
        choices=SOLDOUT_CHOICES,
    )

    voucherId = models.CharField(
        _('Optional voucher code to be added simultaneously'),
        max_length=100, null=True, blank=True
    )

    data = models.JSONField(
        _('Additional data passed with registration'), default=dict, blank=True,
        help_text=_(
            'This may be used for passing specific information about this ' +
            'event registration for statistical or other custom purposes.'
        )
    )

    order = models.PositiveSmallIntegerField(default=0, blank=False, null=False)

    def getDefaultLabel(self):
        if self.optionLabel:
            return self.optionLabel
        elif self.optionType == 'D':
            return _('Drop-in')
        elif self.optionType == 'S':
            return _('Student')
        elif self.voucherId:
            return _('Register with voucher {}'.format(self.voucherId))
        return _('Register')

    def addChoices(self, event, requireFullRegistration=True, paymentMethods=None):
        '''
        This method handles the logic of creating one or more choices (i.e. buttons)
        associated with this instance for a particular event.  The exact number
        of choices and the passed attributes in each will depend on the options
        for this instance.  The method returns a list of primary and additional
        options that are collected by the plugin's render() method and sent to
        the template for display.
        '''
        primary_options = []
        additional_options = []

        # No need to continue if the event open status does not match the choice
        # requirements.
        if (
            (event.registrationOpen is False and self.registrationOpenDisplay == "O") or
            (event.registrationOpen is True and self.registrationOpenDisplay == "C")
        ):
            return (primary_options, additional_options)

        # Create generic payment method if we don't have or need specific
        # payment methods.
        if not paymentMethods or not self.byPaymentMethod:
            paymentMethods = [
                {
                    'name': None,
                    'requireFullRegistration': False,
                    'autoSubmit': False,
                },
            ]
        roles = [
            {
                'name': x.name,
                'id': x.id,
                'soldOut': event.soldOutForRole(x),
            } for x in event.availableRoles
        ]
        if not roles or not self.byRole:
            roles = [{'name': None, 'id': None, 'soldOut': event.soldOut}, ]

        # Used to populate the unique choice ID
        choice_counter = 0

        for role in roles:
            if role['soldOut'] and self.soldOutRule == 'H':
                continue

            for method in paymentMethods:

                requireFullRegistration = (
                    self.requireFullRegistration or
                    method['requireFullRegistration'] or
                    requireFullRegistration
                )

                soldOutString = '({})'.format(_('Sold out')) if role['soldOut'] else ''

                this_label = '{} {} {} {}'.format(
                    self.getDefaultLabel() or '',
                    role['name'] or '',
                    method['name'] or '',
                    soldOutString or '',
                ).strip()

                this_choice = {
                        'label': this_label,
                        'price': event.pricingTier.doorPrice,
                        'roleName': role['name'],
                        'roleId': role['id'],
                        'paymentMethod': method['name'],
                        'requireFullRegistration': requireFullRegistration,
                        'autoSubmit': method['autoSubmit'],
                        'choiceId': 'eventchoice_{}_{}_{}'.format(
                            event.id, self.id, choice_counter
                        )
                }

                # Add additional data needed for vouchers, drop-ins, students,
                # and comped registrations
                if self.optionType == 'D':
                    this_choice.update({
                        'dropIn': True, 'price': event.pricingTier.dropinPrice,
                        'dropInOccurrence': getattr(event, 'thisOccurrence', None),
                    })
                if self.voucherId:
                    this_choice.update({'voucherId': self.voucherId})
                if self.optionType == 'S':
                    this_choice.update({'student': True})
                if self.eventPlugin.autoCheckIn in ['S', 'E']:
                    this_choice.update({
                        'checkInOccurrence': getattr(event, 'thisOccurrence', None)
                    })

                # Add additional data passed via the JSON field.  This is encoded as
                # JSON since the output will be added as a data attribute by a template.
                if self.data:
                    this_choice.update({'data': json.dumps(self.data)})

                # Sold out options that should be hidden haven't gotten this far,
                # so everything else is placed appropriately here.
                if (self.optionLocation == 'P' and not (
                    role['soldOut'] and self.soldOutRule == 'A'
                )):
                    primary_options.append(this_choice)
                    choice_counter += 1
                else:
                    additional_options.append(this_choice)
                    choice_counter += 1

        return (primary_options, additional_options)

    class Meta(object):
        ordering = ['order', ]
