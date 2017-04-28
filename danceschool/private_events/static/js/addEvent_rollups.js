$(document).ready(function(){
	check_visibility_divs();
	check_reminder_divs();

	$('#id_eventoccurrence_set-0-startTime_0').datepicker();
	$('#id_eventoccurrence_set-0-endTime_0').datepicker();

	$('#id_eventoccurrence_set-0-startTime_1').timepicker({'scrollDefault': '7:00pm'});
	$('#id_eventoccurrence_set-0-endTime_1').timepicker({'scrollDefault': '7:00pm'});

	check_allDay();

	$('#div_id_visibleTo').change(function(){
		check_visibility_divs();
	});
	$('#div_id_eventoccurrence_set-0-sendReminderTo').change(function(){
		check_reminder_divs();
	});
	$('#id_eventoccurrence_set-0-allDay').change(function(){
		check_allDay();
	});
	$('#id_eventoccurrence_set-0-startTime_0').change(function(){
		if ($('#id_eventoccurrence_set-0-endTime_0').val() == false) {
			$('#id_eventoccurrence_set-0-endTime_0').val($('#id_eventoccurrence_set-0-startTime_0').val());
		}
	});
	$('#id_eventoccurrence_set-0-startTime_1').change(function(){
		if ($('#id_eventoccurrence_set-0-endTime_1').val() == false) {
			var this_moment = moment($('#id_eventoccurrence_set-0-startTime_1').val(),"hh:mma").add(1,'hours')
			$('#id_eventoccurrence_set-0-endTime_1').val(this_moment.format("hh:mma"));
		}
	});
	$('form').submit(function() {
		$('#id_eventoccurrence_set-0-startTime_1').removeAttr('disabled');
		$('#id_eventoccurrence_set-0-endTime_1').removeAttr('disabled');
	});
});

function check_visibility_divs() {
	var this_visibleTo = $('#div_id_visibleTo option:selected').val();

	if (this_visibleTo == "all" || this_visibleTo == "me") {
		$('#div_id_displayToGroup').hide();
		$('#div_id_displayToUsers').hide();
	}
	if (this_visibleTo == "group") {
		$('#div_id_displayToGroup').show();
		$('#div_id_displayToUsers').hide();
	}
	if (this_visibleTo == "users") {
		$('#div_id_displayToGroup').hide();
		$('#div_id_displayToUsers').show();
	}
}


function check_reminder_divs() {
	var this_reminderTo = $('#div_id_eventoccurrence_set-0-sendReminderTo option:selected').val();

	if (this_reminderTo == "all" || this_reminderTo == "me" || this_reminderTo == "none") {
		$('#div_id_eventoccurrence_set-0-sendReminderGroup').hide();
		$('#div_id_eventoccurrence_set-0-sendReminderUsers').hide();
	}
	if (this_reminderTo == "group") {
		$('#div_id_eventoccurrence_set-0-sendReminderGroup').show();
		$('#div_id_eventoccurrence_set-0-sendReminderUsers').hide();
	}
	if (this_reminderTo == "users") {
		$('#div_id_eventoccurrence_set-0-sendReminderGroup').hide();
		$('#div_id_eventoccurrence_set-0-sendReminderUsers').show();
	}
}


function check_allDay() {
	var selected = $('#id_eventoccurrence_set-0-allDay').is(':checked');

	if (selected == true) {
		$('#id_eventoccurrence_set-0-startTime_1').prop("disabled", true);
		$('#id_eventoccurrence_set-0-endTime_1').prop("disabled", true);
	}
	else {
		$('#id_eventoccurrence_set-0-startTime_1').prop("disabled", false);
		$('#id_eventoccurrence_set-0-endTime_1').prop("disabled", false);
	}
}