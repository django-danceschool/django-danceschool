from django import template
from django.db.models.query import QuerySet
from django.core.exceptions import ObjectDoesNotExist

from calendar import month_name, day_name
from polymorphic.query import PolymorphicQuerySet
import re

from danceschool.core.models import Event, DanceRole, Instructor, Location
from danceschool.core.constants import getConstant

# This is needed to register all the tags
register = template.Library()


@register.filter
def readable_month(month):
    try:
        return month_name[month]
    except (TypeError,IndexError):
        return None


@register.filter
def urlencodename(string):
    return string.replace('-','_').replace(' ','+')


@register.filter
def urldecodename(string):
    return string.replace('_','-').replace('+',' ')


@register.simple_tag
def readable_weekday(weekday):
    try:
        return day_name[weekday]
    except (TypeError,IndexError):
        return None


@register.simple_tag
def getSchoolName():
    '''
    For easily retrieving the school name without overriding templates,
    such as in the default navbar template.
    '''
    return getConstant('contact__businessName')


@register.filter(name='has_group')
def has_group(user, group_name):
    '''
    This allows specification group-based permissions in templates.
    In most instances, creating model-based permissions and giving
    them to the desired group is preferable.
    '''
    if user.groups.filter(name=group_name).exists():
        return True
    return False


@register.filter
def get_item(dictionary, key):
    '''
    This allows us to get a specific key from a dictionary, where
    the key can be a variable name.
    '''
    return dictionary.get(key)


@register.simple_tag
def get_item_by_key(passed_list, key, value):
    '''
    This one allows us to get one or more items from a list of
    dictionaries based on the value of a specified key, where
    both the key and the value can be variable names.  Does
    not work with None or null string passed values.
    '''

    if value in [None,'']:
        return

    if type(passed_list) in [QuerySet, PolymorphicQuerySet]:
        sub_list = passed_list.filter(**{key: value})
    else:
        sub_list = [x for x in passed_list if x.get(key) == value]

    if len(sub_list) == 1:
        return sub_list[0]
    return sub_list


@register.simple_tag
def get_field_for_object(field_type,field_id, form):
    '''
    This tag allows one to get a specific series or event form field
    in registration views.
    '''
    field_name = field_type + '_' + str(field_id)
    return form.__getitem__(field_name)


@register.filter
def template_exists(template_name):
    '''
    Determine if a given template exists so that it can be loaded
    if so, or a default alternative can be used if not.
    '''
    try:
        template.loader.get_template(template_name)
        return True
    except template.TemplateDoesNotExist:
        return False


@register.simple_tag
def numRegisteredForRole(event,role):
    '''
    This tag allows one to access the number of registrations
    for any dance role.
    '''
    if not isinstance(event,Event) or not isinstance(role,DanceRole):
        return None
    return event.numRegisteredForRole(role)


@register.simple_tag
def numRegisteredForRoleName(event,roleName):
    '''
    This tag allows one to access the number of registrations
    for any dance role using only the role's name.
    '''
    if not isinstance(event,Event):
        return None

    try:
        role = DanceRole.objects.get(name=roleName)
    except ObjectDoesNotExist:
        return None

    return event.numRegisteredForRole(role)


@register.filter
def getStatusValue(obj,value):
    '''
    Several model fields use the DjangoChoices app for cleaner
    enum-type value storage of status variables.  This gets the label for a passed value
    associated with one of these fields.
    '''
    if isinstance(obj,Event):
        choice_dict = Event.RegStatus.values
    elif isinstance(obj,Instructor):
        choice_dict = Instructor.InstructorStatus.values
    elif isinstance(obj,Location):
        choice_dict = Location.StatusChoices.values
    else:
        return None

    # All these classes store choice information in the status field.
    return choice_dict.get(obj.status) or obj.status


@register.filter
def camelSpace(obj):
    ''' Add spaces in camelCase words '''
    return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', obj)
