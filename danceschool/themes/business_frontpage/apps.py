# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class BusinessFrontpageAppConfig(AppConfig):
    name = 'danceschool.themes.business_frontpage'
    verbose_name = _('Business Front Page Theme')

    def ready(self):
        ''' 
        Update the default placeholder configuration to set the default splash image and default title.
        '''
        from django.conf import settings

        if not isinstance(getattr(settings,'CMS_PLACEHOLDER_CONF',None),dict):
            settings.CMS_PLACEHOLDER_CONF = {}

        settings.CMS_PLACEHOLDER_CONF.update({
            'splash_image': {
                'name': 'Front Page Background Image',
                'limits': {
                    'global': 1,
                },
                'default_plugins':[
                    {
                        'plugin_type': 'TextPlugin',
                        'values':{
                            'body': 'https://via.placeholder.com/1920x400',
                        },
                    },
                ]
            },
            'splash_title': {
                'name': 'Front Page Title',
                'default_plugins':[
                    {
                        'plugin_type': 'TextPlugin',
                        'values': {
                            'body': 'Your Dance School Name Here',
                        }
                    }
                ]
            }
        })
