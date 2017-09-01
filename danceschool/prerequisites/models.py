from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError

from djchoices import DjangoChoices, ChoiceItem

from danceschool.core.models import Customer, ClassDescription, DanceTypeLevel, DanceRole, Registration, TemporaryRegistration, EventRegistration


class Requirement(models.Model):
    '''
    Requirements apply to either a ClassDescription (i.e. a specific class), or to a DanceTypeLevel (i.e. a specific level).
    They typically consist of one or more items, though if a Requirement has no items, then the only way it can be met is for
    a Customer to have explicitly met the requirement through a CustomerRequirement object.
    '''
    class BooleanChoice(DjangoChoices):
        booleanAnd = ChoiceItem('&',_('Must meet all requirement items'))
        booleanOr = ChoiceItem('|',_('Must meet one or more requirement items'))
        booleanNot = ChoiceItem('!',_('Must not meet any requirement items'))

    class EnforcementChoice(DjangoChoices):
        none = ChoiceItem('N',_('Enforcement disabled'))
        warning = ChoiceItem('W',_('Allow registration with warning'))
        error = ChoiceItem('E',_('Raise error and do not allow registration'))

    name = models.CharField(_('Requirement name/description'),max_length=300,help_text=_('If a customer does not meet the requirement for a series, then this description will be used to explain the issue (e.g. \'Must have taken Lindy 1 to take Lindy 2\').'))

    applicableClass = models.ForeignKey(ClassDescription,verbose_name=_('Applies to class'),null=True,blank=True)
    applicableLevel = models.ForeignKey(DanceTypeLevel,verbose_name=_('Applies to dance type/level'),null=True,blank=True)

    booleanRule = models.CharField(
        max_length=3,choices=BooleanChoice.choices,default=BooleanChoice.booleanAnd,
        verbose_name=_('How many items of this requirement must be met'),
        help_text=_('If you select an option other than \'Must meet all requirements\', then you can still enforce multiple requirements by adding another Requirement item.'))
    enforcementMethod = models.CharField(_('Enforcement method'),max_length=1,choices=EnforcementChoice.choices,default=EnforcementChoice.warning)

    applicableRole = models.ForeignKey(DanceRole,verbose_name=_('Applies only to role (optional)'),help_text=_('Most requirements apply identically to all dance roles.  If this requirement does not, then specify the role to which it applies here.'),null=True,blank=True)
    roleEnforced = models.BooleanField(_('Same dance role enforced'),default=False,help_text=_('If checked, then in order to meet the requirement, the customer must have met all individual requirements in the same dance role, and that must be the dance role for which they are registering.'))

    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last modified date'),auto_now=True)

    @property
    def enabled(self):
        return self.enforcementMethod != self.EnforcementChoice.none
    enabled.fget.short_description = _('Enabled')

    def customerMeetsRequirement(self, customer, danceRole=None, registration=None):
        '''
        This method checks whether a given customer meets a given set of requirements.
        '''

        cust_reqs = self.customerrequirement_set.filter(customer=customer,met=True)
        if customer:
            cust_priors = customer.eventregistration_set.filter(event__series__isnull=False)
        else:
            cust_priors = EventRegistration.objects.none()

        # If there's an explicit object stating that this customer meets the requirement, then we're done.
        if self.roleEnforced and danceRole and cust_reqs.filter(role=danceRole).exists():
            return True
        elif not self.roleEnforced and cust_reqs.exists():
            return True
        elif self.roleEnforced and not danceRole:
            return False

        # Go through each item for this requirement and see if the customer meets that item
        for item in self.requirementitem_set.all():
            filter_dict = {}
            if item.requiredLevel:
                filter_dict['event__series__classDescription__danceTypeLevel'] = item.requiredLevel
            if item.requiredClass:
                filter_dict['event__series__classDescription'] = item.requiredClass
            if self.roleEnforced:
                filter_dict['role'] = danceRole

            current_matches = 0
            overlap_matches = 0
            nonconcurrent_filter = {'event__endTime__lte': timezone.now()}

            if registration:

                if isinstance(registration,Registration):
                    current_matches = registration.eventregistration_set.filter(**filter_dict).count()
                elif isinstance(registration,TemporaryRegistration):
                    current_matches = registration.temporaryeventregistration_set.filter(**filter_dict).count()

                nonconcurrent_filter = {'event__endTime__lte': registration.firstSeriesStartTime}
                overlap_matches = cust_priors.filter(**filter_dict).exclude(**nonconcurrent_filter).filter(
                    event__startTime__lte=registration.lastSeriesEndTime,
                ).count()

            priors_matches = cust_priors.filter(**filter_dict).filter(**nonconcurrent_filter).count()

            # The number of matches depends on the concurrency rule for this item
            if item.concurrentRule == item.ConcurrencyRule.prohibited:
                matches = priors_matches
            elif item.concurrentRule == item.ConcurrencyRule.allowOneOverlapClass:
                matches = priors_matches + \
                    cust_priors.filter(**filter_dict).exclude(**nonconcurrent_filter).filter(
                        event__startTime__lte=registration.getTimeOfClassesRemaining(1)
                    ).count()
            elif item.concurrentRule == item.ConcurrencyRule.allowTwoOverlapClasses:
                matches = priors_matches + \
                    cust_priors.filter(**filter_dict).exclude(**nonconcurrent_filter).filter(
                        event__startTime__lte=registration.getTimeOfClassesRemaining(2)
                    ).count()
            elif item.concurrentRule == item.ConcurrencyRule.allowed:
                matches = priors_matches + overlap_matches + \
                    (current_matches if isinstance(registration,TemporaryRegistration) else 0)
            elif item.concurrentRule == item.ConcurrencyRule.required:
                matches = overlap_matches + current_matches

            if matches >= item.quantity:
                # If this is an 'or' or a 'not' requirement, then we are done
                if self.booleanRule == self.BooleanChoice.booleanOr:
                    return True
                if self.booleanRule == self.BooleanChoice.booleanNot:
                    return False
            else:
                # If this is an 'and' requirement and we didn't meet, then we are done
                if self.booleanRule == self.BooleanChoice.booleanAnd:
                    return False

        # If we got this far, then either all 'and' requirements were met, or all 'or' and 'not' requirements were not met
        if self.booleanRule == self.BooleanChoice.booleanOr or self.requirementitem_set.count() == 0:
            return False
        return True

    def clean(self):
        if self.applicableClass and self.applicableLevel:
            raise ValidationError(_('Requirement must be for a specific class or for a dance level; it cannot be for both.'))
        if not self.applicableClass and not self.applicableLevel:
            raise ValidationError(_('Requirement must apply to either a specific class or to a dance level.'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Class requirement')
        verbose_name = _('Class requirements')
        permissions = (
            ('ignore_requirements',_('Can register users for series regardless of any prerequisites or requirements')),
        )


class RequirementItem(models.Model):
    ''' Each component of a requirement is one of these '''

    requirement = models.ForeignKey(Requirement,verbose_name=_('Requirement'),null=True)

    class ConcurrencyRule(DjangoChoices):
        prohibited = ChoiceItem('P',_('Must have previously taken'))
        allowOneOverlapClass = ChoiceItem('1',_('May register/begin with one class remaining'))
        allowTwoOverlapClasses = ChoiceItem('1',_('May register/begin with two classes remaining'))
        allowed = ChoiceItem('A',_('Concurrent registration allowed'))
        required = ChoiceItem('R',_('Concurrent registration required'))

    quantity = models.PositiveSmallIntegerField(_('Quantity'),default=1)
    requiredLevel = models.ForeignKey(DanceTypeLevel,null=True,blank=True,verbose_name=_('Required Dance type/level'))
    requiredClass = models.ForeignKey(ClassDescription,null=True,blank=True,verbose_name=_('Required class'))

    concurrentRule = models.CharField(_('Concurrency Rule'),max_length=1,choices=ConcurrencyRule.choices,default=ConcurrencyRule.prohibited)

    def clean(self):
        if self.requiredLevel and self.requiredClass:
            raise ValidationError(_('Requirement item cannot specify both a level and a class.'))
        if not self.requiredLevel and not self.requiredClass:
            raise ValidationError(_('Either a level or a class must be required.'))

    class Meta:
        verbose_name = _('Requirement item')
        verbose_name_plural = _('Requirement items')


class CustomerRequirement(models.Model):
    '''
    This class allows for override of requirements on a per-customer basis.
    '''
    customer = models.ForeignKey(Customer,verbose_name=_('Customer'))
    requirement = models.ForeignKey(Requirement,verbose_name=_('Requirement'))
    role = models.ForeignKey(DanceRole,null=True,blank=True,verbose_name=_('Dance role'),help_text=_('Role must be specified only for requirements for which roles are enforced.'))

    met = models.BooleanField(_('Meets Requirement'),default=True,help_text=_('If unchecked, then the customer explicitly does not meet the requirement, regardless of whether they meet its parameters.'))
    comments = models.TextField(_('Comments/Notes'),null=True,blank=True)

    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last modified date'),auto_now=True)

    def clean(self):
        if self.requirement.roleEnforced and not self.role:
            raise ValidationError(_('Since roles are enforced for this requirement, you must specify the customer\'s dance role.'))

    class Meta:
        unique_together = ('customer','requirement','role')
        verbose_name = _('Customer-level requirement record')
        verbose_name_plural = _('Customer-level requirement records')
