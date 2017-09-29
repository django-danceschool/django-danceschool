from persisting_theory import Registry


class PluginTemplateBase(object):
    ''' The base class for registering custom plugin templates. '''

    # The name of the template to use
    template_name = ''

    # The plugin class for which this is a template.
    plugin = None

    # An optional description of the template (used in the dropdown)
    description = ''


class PluginTemplatesRegistry(Registry):
    '''
    Several plugins in this project allow the use of selectable templates
    (e.g. for different types of statistics, different ways of displaying
    instructors or upcoming series, etc.).  This registry keep track of the
    list of template options that is presented when configuring each plugin.
    While a user with the 'core.choose_custom_plugin_template' permission
    can always set an entirely custom template file, it is recommended to
    register your customer templates by defining a class in your app's
    cms_plugins.py that inherits from
    danceschool.core.registries.PluginTemplateBase, defining the
    template_name and plugin properties, then registering your class by
    decorating it with @plugin_templates_registry.register.
    '''

    # the package where the registry will try to find callbacks in each app
    look_into = "cms_plugins"


plugin_templates_registry = PluginTemplatesRegistry()
