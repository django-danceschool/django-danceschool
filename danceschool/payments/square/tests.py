from django.contrib.auth.context_processors import PermWrapper
from django.template.loader import render_to_string
from django.test import RequestFactory

from danceschool.core.tests.defaults import DefaultSchoolTestCase


class SquarePointOfSaleTemplateTest(DefaultSchoolTestCase):
    '''
    The point-of-sale button must render based on the session-level payAtDoor
    flag, not on a Registration object (which does not exist for carts that
    contain only merchandise).
    '''

    def _render(self, **extra):
        request = RequestFactory().get('/register/summary/')
        request.user = self.superuser
        context = {
            'request': request,
            'user': self.superuser,
            'perms': PermWrapper(self.superuser),
            'currencyCode': 'USD',
            'instance': None,
            'returnUrl': 'https://example.com/square/pos/',
            'squareApplicationId': 'test-app-id',
        }
        context.update(extra)
        return render_to_string('square/point_of_sale.html', context, request=request)

    def test_button_renders_without_registration(self):
        '''Merchandise-only carts have no Registration but should show the button.'''
        html = self._render(payAtDoor=True, registration=None)
        self.assertIn('square-pos-button', html)

    def test_button_renders_with_registration(self):
        html = self._render(payAtDoor=True, registration=object())
        self.assertIn('square-pos-button', html)

    def test_button_hidden_when_not_pay_at_door(self):
        html = self._render(payAtDoor=False, registration=None)
        self.assertNotIn('square-pos-button', html)
