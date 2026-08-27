from django.test import TestCase
from django.dispatch import Signal


class HeaderStatsSignalTest(TestCase):
    """
    Tests that the get_registration_summary_header_stats signal is declared
    in danceschool.core.signals and is a Signal instance.
    """

    def test_signal_is_declared(self):
        from danceschool.core.signals import get_registration_summary_header_stats
        self.assertIsInstance(get_registration_summary_header_stats, Signal)
