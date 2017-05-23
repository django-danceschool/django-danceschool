from django.views.generic import FormView, TemplateView
from django.http import JsonResponse

from datetime import datetime, timedelta

from danceschool.core.models import Instructor
from danceschool.core.constants import getConstant

from .forms import SlotCreationForm, SlotUpdateForm, SlotBookingForm
from .models import InstructorAvailabilitySlot

# Create your views here.


class InstructorAvailabilityView(TemplateView):
    template_name = 'private_lessons/instructor_availability_fullcalendar.html'

    def get_context_data(self,**kwargs):
        context = super(InstructorAvailabilityView,self).get_context_data(**kwargs)

        context.update({
            'instructor': getattr(self.request,'user').staffmember,
            'creation_form': SlotCreationForm(),
            'update_form': SlotUpdateForm(),
        })

        return context


class AddAvailabilitySlotView(FormView):
    form_class = SlotCreationForm

    def get(self, request, *args, **kwargs):
        return JsonResponse({'valid': False})

    def form_invalid(self, form):
        return JsonResponse(form.errors, status=400)

    def form_valid(self, form):
        '''
        Create slots and return success message.
        '''
        startDate = form.cleaned_data['startDate']
        endDate = form.cleaned_data['endDate']
        startTime = form.cleaned_data['startTime']
        endTime = form.cleaned_data['endTime']
        instructor = form.cleaned_data['instructorId']

        interval_minutes = getConstant('privateLessons__lessonLengthInterval')

        print(form.cleaned_data)

        this_date = startDate
        while this_date <= endDate:
            this_time = startTime
            while this_time < endTime:
                InstructorAvailabilitySlot.objects.create(
                    instructor=instructor,
                    startTime=datetime.combine(this_date, this_time),
                    duration=interval_minutes,
                    location=form.cleaned_data.get('location')
                )
                this_time = (datetime.combine(this_date, this_time) + timedelta(minutes=interval_minutes)).time()
            this_date += timedelta(days=1)

        return JsonResponse({'valid': True})


class UpdateAvailabilitySlotView(FormView):
    form_class = SlotUpdateForm
    http_method_names = ['post',]

    def get(self, request, *args, **kwargs):
        return JsonResponse({'valid': False})

    def form_invalid(self, form):
        return JsonResponse(form.errors, status=400)

    def form_valid(self, form):
        '''
        Modify or delete the availability slot as requested and return success message.
        '''
        slotIds = form.cleaned_data['slotIds']
        deleteSlot = form.cleaned_data.get('deleteSlot', False)

        these_slots = InstructorAvailabilitySlot.objects.filter(id__in=slotIds)

        if deleteSlot:
            these_slots.delete()
        else:
            for this_slot in these_slots:
                this_slot.location = form.cleaned_data['updateLocation']
                this_slot.status = form.cleaned_data['updateStatus']
                this_slot.save()

        return JsonResponse({'valid': True})


class BookPrivateLessonView(FormView):
    template_name = 'private_lessons/private_lesson_fullcalendar.html'
    form_class = SlotBookingForm

    def get_context_data(self,**kwargs):
        context = super(BookPrivateLessonView,self).get_context_data(**kwargs)
        context.update({
            'instructor_list': Instructor.objects.filter(availableForPrivates=True,instructorprivatelessondetails__isnull=False),
        })
        return context
