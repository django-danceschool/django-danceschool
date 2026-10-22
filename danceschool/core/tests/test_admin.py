from django.test import TestCase
from django.contrib.auth.models import User

from itertools import chain


class AdminTest(TestCase):
    '''
    Check that all admin add and changelist pages are functional at least for
    superusers.
    '''

    REDIRECT_ADMIN_OBJECTS = ['AliasContentVersion', 'PageContentVersion']

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            'admin',
            'admin@test.com',
            'pass',
            first_name='Frankie',
            last_name='Manning',
        )

    def test_admin_pages(self):
        '''
        Log in as superuser, get the list of admin pages, and check that all
        changelist and add pages return 200.
        '''
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        
        self.client.login(username=self.superuser.username, password='pass')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

        app_list = response.context_data.get('app_list', [])
        self.assertNotEqual(app_list, [])

        for model in chain(*[x.get('models', []) for x in app_list]):
            if model.get('admin_url') and (
                model.get('object_name') not in self.REDIRECT_ADMIN_OBJECTS
            ):
                response = self.client.get(model['admin_url'])
                self.assertEqual(response.status_code, 200)
            if model.get('add_url'):
                response = self.client.get(model['add_url'])
                self.assertEqual(response.status_code, 200)


class EventAdminSearchTest(TestCase):
    '''
    Event.name is a property, not a database field, so event admins must not
    search on it.  Searching with a non-empty term must not raise an error.
    '''

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            'admin', 'admin@test.com', 'pass',
        )

    def setUp(self):
        self.client.login(username=self.superuser.username, password='pass')

    def test_event_changelist_search(self):
        for model in ['event', 'publicevent', 'series']:
            with self.subTest(model=model):
                response = self.client.get(
                    '/admin/core/%s/' % model, {'q': 'test'}
                )
                self.assertEqual(response.status_code, 200)

    def test_event_addon_autocomplete_search(self):
        response = self.client.get('/admin/autocomplete/', {
            'term': 'test', 'app_label': 'core',
            'model_name': 'eventaddon', 'field_name': 'addOnEvent',
        })
        self.assertEqual(response.status_code, 200)
