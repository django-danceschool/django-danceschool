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
