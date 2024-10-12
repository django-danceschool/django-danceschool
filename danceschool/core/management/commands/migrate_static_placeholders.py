import glob
import logging
import os
import re

from itertools import chain

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from cms.models import CMSPlugin, Placeholder, StaticPlaceholder

from djangocms_alias.models import Category, Alias, AliasContent
from djangocms_alias.constants import DEFAULT_STATIC_ALIAS_CATEGORY_NAME

from djangocms_versioning.models import Version
from djangocms_versioning.constants import DRAFT, PUBLISHED

logger = logging.getLogger(__name__)

"""
Steps for migrating static_placeholders to aliases from CMS 3.5 to CMS 4.0
--------------------------------------------------------------------------

for each existing static_placeholder:
    Remap the static_placeholder's contents to the newly formed static_alias
    
for each template:
    Edit the template file to replace 'static_placeholder' with 'static_alias' and remove any 'site' attribute
    
Remove all static_placeholders (their contents will now be empty)
"""

def _get_or_create_alias_category():
    # Parlers get_or_create doesn't work well with translations, so we must perform our own get or create
    default_category = Category.objects.filter(translations__name=DEFAULT_STATIC_ALIAS_CATEGORY_NAME).first()
    if not default_category:
        default_category = Category.objects.create(name=DEFAULT_STATIC_ALIAS_CATEGORY_NAME)
    return default_category


def _get_or_create_alias(category, static_code, site):

    alias_filter_kwargs = {
        'static_code': static_code,
    }
    # Site
    if site:
        alias_filter_kwargs['site'] = site
    else:
        alias_filter_kwargs['site_id__isnull'] = True

    # Try and find an Alias to render
    alias = Alias.objects.filter(**alias_filter_kwargs).first()
    # If there is no alias found we need to create one
    if not alias:

        alias_creation_kwargs = {
            'static_code': static_code,
            'creation_method': Alias.CREATION_BY_TEMPLATE
        }
        # Site
        if site:
            alias_creation_kwargs['site'] = site

        alias = Alias.objects.create(category=category, **alias_creation_kwargs)

        logger.info(f'Created Alias: {alias}')

    return alias


def _get_or_create_alias_content(alias, name, language, user, state=PUBLISHED):
    alias_content, created = AliasContent.objects.get_or_create(
        alias=alias,
        name=name,
        language=language,
    )

    content_ct = ContentType.objects.get_for_model(AliasContent)

    version, version_created = Version.objects.get_or_create(
        content_type=content_ct, object_id=alias_content.id, created_by=user,
        state=state
    )

    if created:
        logger.info(f'Created AliasContent {alias_content}')

    return alias_content


def _remap_static_placeholder_plugins_to_static_alias(static_placeholder_id, static_placeholder_code,
                                                      alias, migration_user, version_state=PUBLISHED):

    published_plugins = CMSPlugin.objects.filter(placeholder_id=static_placeholder_id)
    # Group the plugins by their language because in cms3 placeholders contain all of the contents
    # in all languages vs in cms4 each language has it's own placeholder
    plugin_language_groups = {}
    for plugin in published_plugins:
        if plugin.language not in plugin_language_groups:
            plugin_language_groups[plugin.language] = []
        plugin_language_groups[plugin.language].append(plugin)

    # For every language
    for language in plugin_language_groups.keys():
        logger.info(f'Processing plugin language: {language}')

        plugin_set = plugin_language_groups[language]
        alias_content = _get_or_create_alias_content(alias, static_placeholder_code, language, migration_user, version_state)
        alias_placeholder_id = alias_content.placeholder.id

        # Move the plugins into the Alias
        for plugin in plugin_set:
            plugin.placeholder_id = alias_placeholder_id
            plugin.save()


def _process_static_placeholders(migration_user):
    alias_category = _get_or_create_alias_category()

    # Rescan each page, this will create a <slot> placeholder for each page if it doesn't already exist!
    # for each existing static_placeholder:
    for static_placeholder in StaticPlaceholder.objects.all():
        logger.info(f'Processing static_placeholder {static_placeholder}')

        # Get or create Alias
        alias = _get_or_create_alias(alias_category, static_placeholder.code, static_placeholder.site)

        _remap_static_placeholder_plugins_to_static_alias(
            static_placeholder.public_id, static_placeholder.code, alias, migration_user)

        # If new draft changes are pending "dirty" create a new draft version with those changes
        if static_placeholder.dirty:
            _remap_static_placeholder_plugins_to_static_alias(
                static_placeholder.draft_id, static_placeholder.code, alias, migration_user, version_state=DRAFT)


def _cleanup():
    logger.info('Cleaning up')

    for static_placeholder in StaticPlaceholder.objects.all():
        # Remove the global placeholders associated with the static_placeholder
        Placeholder.objects.filter(id=static_placeholder.public_id).delete()
        Placeholder.objects.filter(id=static_placeholder.draft_id).delete()

        static_placeholder.delete()


class Command(BaseCommand):
    help = 'Convert static_placeholders to static_alias tags'

    def handle(self, *args, **options):
        logger.info('Starting conversion from static_placeholder to static_alias')

        migration_user = User.objects.filter(is_superuser=True).first()
        if not migration_user:
            self.stdout.write(
                self.style.ERROR(
                    'ERROR: Superuser has not yet been created.  Please run ' +
                    '\'python manage.py createsuperuser\' before proceeding.'
                )
            )
            return None

        _process_static_placeholders(migration_user)
        _cleanup()
