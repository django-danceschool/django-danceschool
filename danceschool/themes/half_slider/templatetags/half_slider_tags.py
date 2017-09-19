from django import template

from danceschool.core.constants import getConstant


# This is needed to register all the tags
register = template.Library()


@register.simple_tag
def getThemeImageUrl(tag):
    return getattr(getConstant('theme__%s' % str(tag)),'url',None)
