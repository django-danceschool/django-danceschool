from django.http import HttpResponseRedirect, Http404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView, RedirectView
from django.db.models import Q, Case, When, BooleanField
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from calendar import month_name
import re
from urllib.parse import unquote_plus
from cms.constants import RIGHT

from ..models import Event, Series, PublicEvent
from ..constants import getConstant, REG_VALIDATION_STR
from ..mixins import FinancialContextMixin, ReferralInfoMixin

import logging

logger = logging.getLogger(__name__)


#####################################
# Individual Class Series/Event Views


class IndividualClassReferralView(ReferralInfoMixin, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        if (
            self.kwargs.get('session_slug', None) and
            self.kwargs.get('year', None) and
            self.kwargs.get('month', None)
        ):
            return reverse('classViewSessionMonth', kwargs=kwargs)
        elif (
            self.kwargs.get('session_slug', None)
        ):
            return reverse('classViewSession', kwargs=kwargs)
        else:
            return reverse('classView', kwargs=kwargs)


class IndividualPublicEventReferralView(ReferralInfoMixin, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        if (
            self.kwargs.get('session_slug', None) and
            self.kwargs.get('year', None) and
            self.kwargs.get('month', None)
        ):
            return reverse('eventViewSessionMonth', kwargs=kwargs)
        elif (
            self.kwargs.get('session_slug', None)
        ):
            return reverse('eventViewSession', kwargs=kwargs)
        else:
            return reverse('eventView', kwargs=kwargs)


class IndividualEventView(ReferralInfoMixin, FinancialContextMixin, TemplateView):
    model_class = Event
    template_name = 'core/event_pages/individual_event.html'

    def dispatch(self, request, *args, **kwargs):
        # These are passed via the URL
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        session_slug = self.kwargs.get('session_slug')
        slug = self.kwargs.get('slug', '')
        event_uuid = self.kwargs.get('uuid')

        model_class = getattr(self, 'model_class', Event)

        passedCase = Q(endTime__lt=timezone.now())
        if getConstant('registration__displayLimitDays') or 0 > 0:
            passedCase = passedCase | Q(
                startTime__gte=timezone.now() + timedelta(
                    days=getConstant('registration__displayLimitDays')
                )
            )

        annotate_kwargs = dict(
            registrationPassed=Case(
                When(passedCase, then=True), default=False,
                output_field=BooleanField()
            )
        )

        if event_uuid:
            # UUID-based lookup: allow linkOnly events (they are specifically
            # accessed via their private link), but still exclude hidden events.
            self.event_set = model_class.objects.filter(
                uuid=event_uuid
            ).exclude(
                status=Event.RegStatus.hidden
            ).annotate(**annotate_kwargs)
            self.link_uuid = event_uuid
        else:
            if month:
                try:
                    month_number = list(month_name).index(month or 0)
                except ValueError:
                    raise Http404(_('Invalid month.'))

            # Slug-based lookup: linkOnly events are intentionally excluded so
            # that they cannot be reached without their private UUID link.
            filters = ~Q(status=Event.RegStatus.hidden) \
                & ~Q(status=Event.RegStatus.linkOnly)
            if model_class == Series:
                filters = filters & Q(classDescription__slug=slug)
            elif model_class == PublicEvent:
                filters = filters & Q(slug=slug)

            if year and month:
                filters = filters & Q(year=year or None) & Q(month=month_number or None)
            if session_slug:
                filters = filters & Q(session__slug=session_slug)

            self.event_set = model_class.objects.filter(
                filters
            ).annotate(**annotate_kwargs)
            self.link_uuid = None

        if not self.event_set:
            raise Http404(_('No events found.'))

        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        templates = [x.template for x in self.event_set if getattr(x, 'template', None)]
        if templates:
            return [templates[0],]
        else:
            return super().get_template_names()

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, *args, **kwargs):

        # This will pass through to the context data by default
        kwargs.update({'event_set': self.event_set})

        # If the user arrived via a UUID link, authorize any linkOnly events in
        # this event_set for cart addition (stored in session for the duration
        # of the registration session).
        link_authorized = False
        if self.link_uuid:
            for event in self.event_set:
                if event.status == Event.RegStatus.linkOnly:
                    reg_session = request.session.setdefault(REG_VALIDATION_STR, {})
                    authorized_ids = reg_session.setdefault('link_authorized', [])
                    if event.pk not in authorized_ids:
                        authorized_ids.append(event.pk)
                    request.session.modified = True
                    link_authorized = True
        kwargs['link_authorized'] = link_authorized

        model_lower = getattr(self, 'model_class', Event).__name__.lower()
        app_name = getattr(self, 'app_name', 'core')

        # For each Event in the set, add a button to the toolbar to edit the Event details
        if (
            hasattr(request, 'user') and
            request.user.has_perm('%s.change_%s' % (app_name, model_lower))
        ):
            for this_event in self.event_set:
                this_title = _('Edit Event Details')
                if len(self.event_set) > 1:
                    this_title += ' (#%s)' % this_event.id
                change_link = reverse(
                    'admin:%s_%s_change' % (app_name, model_lower),
                    args=([this_event.id, ])
                )
                request.toolbar.add_button(this_title, change_link, side=RIGHT)

        return super().get(request, *args, **kwargs)


class IndividualClassView(IndividualEventView):
    model_class = Series
    template_name = 'core/event_pages/individual_class.html'


class IndividualPublicEventView(IndividualEventView):
    model_class = PublicEvent
    template_name = 'core/event_pages/individual_event.html'

    def get(self, request, *args, **kwargs):
        # If an alternative link is given by one or more of these events, then redirect to that.
        overrideLinks = [x.link for x in self.event_set if getattr(x, 'link', None)]
        if overrideLinks:
            return HttpResponseRedirect(overrideLinks[0])

        return super().get(request, *args, **kwargs)
