from .event_roles import EventRoleInline
from .event_features import ClassDescriptionAdminForm, ClassDescriptionAdmin
from .event_occurrences import EventOccurrenceInlineForm, EventOccurrenceInline
from .event_addons import EventAddOnInline
from .event_base import (
    WIDGET_FORMATS, repeat_events, EventParentAdmin, EventChildAdmin
)
from .event_categories import (
    PublicEventCategoryAdmin, SeriesCategoryAdmin, EventSessionAdmin
)
from .event_prices import PricingTierAdmin
from .event_registration import EventRegistrationInline, RegistrationAdmin
from .event_types import (
    SeriesAdminForm, PublicEventAdminForm, SeriesAdmin, PublicEventAdmin
)
from .invoices import InvoiceAdminForm, InvoiceItemInline, InvoiceAdmin
from .locations import RoomInline, RoomAdmin, LocationAdmin
from .staff import (
    EventStaffMemberInlineForm, EventStaffMemberInline, EventStaffCategoryAdmin,
    InstructorInline, StaffMemberAdmin
)
from .customers import (
    CustomerEventRegistrationInline, CustomerAdmin, CustomerGroupAdminForm,
    CustomerGroupAdmin
)
from .emails import EmailTemplateAdminForm, EmailTemplateAdmin