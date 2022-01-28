from persisting_theory import Registry


class TemplateBase(object):
    '''
    The base class for registering templates in registries, subclassed as
    needed for template registries, etc.    
    '''

    # The name of the template to use
    template_name = ''

    # An optional description of the template
    description = ''


class PluginTemplateBase(TemplateBase):
    ''' The base class for registering custom plugin templates. '''

    # The plugin class for which this is a template.
    plugin = None


class ModelTemplateBase(TemplateBase):
    ''' The base class for registering custom model page templates. '''

    # The plugin class for which this is a template.
    model = None


class ExtrasTemplateBase(TemplateBase):
    ''' The base class for registering event registration extras templates. '''

    # The Javascript file associated with this extras template, if needed.
    js_name = ''


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


class ModelTemplatesRegistry(Registry):
    '''
    The Event models (including its child models) allow for the use of
    selectable templates (e.g. for different types of events).  This registry
    keeps track of the list of template options that is presented when adding
    an event.  To use this feature, register your model templates by defining
    a class in your app's model_templates.py that inherits from
    danceschool.core.registries.ModelTemplateBase, defining the template_name
    and model properties, then registering your class by decorating it with
    @model_templates_registry.register.
    '''

    # the package where the registry will try to find callbacks in each app
    look_into = "model_templates"


class RegExtrasTemplatesRegistry(Registry):
    '''
    Applications can hook into the registration check-in process to provide
    extra information that may be pertinent at check-in. This information is
    already provided to the core app views using the get_eventregistration_data
    signal. However, the core app does not know how to display this information.
    This registry allows apps to specify their own templates in which the extra
    information can be displayed.
    '''

    # the package where the registry will try to find callbacks in each app
    look_into = "extras_templates"


plugin_templates_registry = PluginTemplatesRegistry()
model_templates_registry = ModelTemplatesRegistry()
extras_templates_registry = RegExtrasTemplatesRegistry()
