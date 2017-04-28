from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q


class PrerequisitesAppConfig(AppConfig):
    name = 'danceschool.prerequisites'
    verbose_name = _('Class Requirements/Prerequisites')

    def ready(self):
        from danceschool.core.models import Series, Customer
        from .models import Requirement
        # This ensures that the signal receivers are loaded
        from . import handlers

        def getRequirements(series):
            return Requirement.objects.filter(Q(applicableLevel=series.classDescription.danceTypeLevel) | Q(applicableClass=series.classDescription)).exclude(enforcementMethod=Requirement.EnforcementChoice.none)

        def customerMeetsAllSeriesRequirements(series, customer, danceRole=None,registration=None):
            ''' Add a method to the Series class to check whether a specified customer meets all requirements for the Series. '''
            for req in series.getRequirements():
                if not req.customerMeetsRequirement(customer,danceRole=danceRole,registration=registration):
                    return False
            return True

        def meetsAllSeriesRequirements(customer, series, danceRole=None,registration=None):
            ''' Just reverse the arguments so this can be added to the Customer class, too. '''
            return customerMeetsAllSeriesRequirements(series, customer, danceRole, registration)

        Series.add_to_class('getRequirements',getRequirements)
        Series.add_to_class('customerMeetsAllRequirements',customerMeetsAllSeriesRequirements)
        Customer.add_to_class('meetsAllSeriesRequirements',meetsAllSeriesRequirements)
