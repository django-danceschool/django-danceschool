from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from datetime import timedelta
from dynamic_preferences.registries import global_preferences_registry

from danceschool.core.models import DanceRole, DanceType, DanceTypeLevel, ClassDescription, PricingTier, Location, Instructor, Event, Series, EventStaffMember, EventOccurrence
from danceschool.core.constants import getConstant


class DefaultSchoolTestCase(TestCase):
    '''
    This class just sets up standard data for the school, and it can be
    inherited from, since many test classes in different apps may want to
    use this same test data.
    '''

    @classmethod
    def setUpTestData(cls):

        # Ensure that necessary constants are initialized and that all
        # needed categories are created within the database
        gp = global_preferences_registry.manager()
        gp.load_from_db()

        # Create Lead and Follow roles
        DanceRole.objects.create(name='Lead',order=1)
        DanceRole.objects.create(name='Follow',order=2)
        cls.defaultDanceRoles = DanceRole.objects.filter(name__in=['Lead','Follow'])
        cls.defaultDanceType = DanceType.objects.create(name='Lindy Hop',order=1)
        cls.defaultDanceType.roles = cls.defaultDanceRoles
        cls.defaultDanceType.save()

        # Create two levels for tests that involve different levels
        cls.levelOne = DanceTypeLevel.objects.create(name='Level 1', order=1, danceType=cls.defaultDanceType)
        cls.levelTwo = DanceTypeLevel.objects.create(name='Level 2', order=2, danceType=cls.defaultDanceType)

        # Create two ClassDescriptions for classes, one in each level
        cls.levelOneClassDescription = ClassDescription.objects.create(
            title='Test Level One Class',
            description='This is a test description',
            danceTypeLevel=cls.levelOne,
            slug='test-level-one',
        )
        cls.levelTwoClassDescription = ClassDescription.objects.create(
            title='Test Level Two Class',
            description='This is a test description',
            danceTypeLevel=cls.levelTwo,
            slug='test-level-two',
        )

        # Create a default PricingTier and a default Location
        cls.defaultPricing = PricingTier.objects.create(
            name='Default Pricing',
            onlinePrice=50,
            doorPrice=60,
            dropinPrice=10,
        )
        cls.defaultLocation = Location.objects.create(
            name='Default Location',
            status=Location.StatusChoices.active,
            address='This is a street address',
            city='Boston',
            state='MA',
            zip='02114',
            directions='These are directions to the default location.',
            defaultCapacity=50,
        )

        # Create a superuser and a non-staff user
        cls.superuser = User.objects.create_superuser(
            'admin',
            'admin@test.com',
            'pass',
            first_name='Frankie',
            last_name='Manning',
        )

        cls.nonStaffUser = User.objects.create_user(
            'regularuser',
            'user@domain.com',
            'pass',
            is_staff=False,
            first_name='New',
            last_name='Student',
        )

        # Make the superuser an Instructor
        cls.defaultInstructor = Instructor.objects.create(
            status=Instructor.InstructorStatus.roster,
            firstName='Frankie',
            lastName='Manning',
            userAccount=cls.superuser,
            publicEmail='admin@test.com',
            privateEmail='admin@test.com',
            bio='This is Frankie Manning.',
        )

    def create_series(self,**kwargs):
        """
        This method just creates a new series with the loaded class
        description that can be modified or used for various tests.
        """

        # Create one or more occurrences.  By default, the series
        # starts tomorrow, is a Level One Lindy Hop class with default
        # pricing and location, is enabled for registration, and is taught
        # by Frankie Manning.
        occurrences = max(kwargs.get('occurrences',1),1)
        startTime = kwargs.get('startTime', timezone.now() + timedelta(days=1))
        classDescription = kwargs.get('classDescription', self.levelOneClassDescription)
        pricingTier = kwargs.get('pricingTier', self.defaultPricing)
        location = kwargs.get('location', self.defaultLocation)
        status = kwargs.get('status', Event.RegStatus.enabled)
        instructors = kwargs.get('instructors', [self.defaultInstructor,])

        s = Series(
            classDescription=classDescription,
            pricingTier=pricingTier,
            location=location,
            status=status,
        )
        s.save()
        # Add an occurrence at the start Time
        # and if requested to set more than one occurrence, then
        # each additional occurrence is the day after the last one.
        for k in range(1,occurrences + 1):
            EventOccurrence.objects.create(
                event=s,
                startTime=startTime + timedelta(days=k - 1),
                endTime=startTime + timedelta(days=k - 1,hours=1)
            )
        # Add instructors (Frankie Manning by default)
        for i in instructors:
            seriesteacher = EventStaffMember.objects.create(
                event=s,
                category=getConstant('general__eventStaffCategoryInstructor'),
                staffMember=i,
            )
            seriesteacher.occurrences = s.eventoccurrence_set.all()
            seriesteacher.save()
        # Must save after adding event occurrences to ensure that
        # registration status is updated properly.
        s.save()
        return s

    def create_instructor(self,**kwargs):
        '''
        This method creates a new instructor (other than the default)
        for testing things like substitute teaching.
        '''
        status = kwargs.get('status', Instructor.InstructorStatus.roster)
        firstName = kwargs.get('firstName','Norma')
        lastName = kwargs.get('lastName','Miller')
        publicEmail = kwargs.get('publicEmail','norma@miller.com')
        privateEmail = kwargs.get('privateEmail', 'norma@miller.com')
        bio = kwargs.get('bio', 'This is Norma Miller.')
        userAccount = kwargs.get('userAccount', None)

        return Instructor.objects.create(
            status=status,
            firstName=firstName,
            lastName=lastName,
            userAccount=userAccount,
            publicEmail=publicEmail,
            privateEmail=privateEmail,
            bio=bio,
        )
