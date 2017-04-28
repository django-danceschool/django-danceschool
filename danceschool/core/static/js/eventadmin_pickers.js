(function($) {
    $(document).on('formset:added', function(event, $row, formsetName) {
    	if (formsetName == 'eventoccurrence_set') {
			set_new_times();
			set_new_dates();
			make_timepickers();
			make_datepickers();
    	}
    });
})(django.jQuery);

$(document).ready(function(){
	$('#eventoccurrence_set-group .field-startTime input[id*=-startTime_0]').change(function(){
		set_end_dates();
	});

	$('#eventoccurrence_set-group .field-endTime input[id*=-endTime_1]').focus(function(){
		set_end_dates();
	});

	make_timepickers();
	make_datepickers();	
});

function make_timepickers() {
	console.log('Making timepickers.');
	$.each($('#eventoccurrence_set-group .field-startTime input[id*=-startTime_1]'), function(index,inputfield) {
		$(inputfield).timepicker({'scrollDefault': '7:00pm', 'step': 15});
	});
	$.each($('#eventoccurrence_set-group .field-endTime input[id*=-endTime_1]'), function(index,inputfield) {
		$(inputfield).timepicker({'scrollDefault': '7:00pm', 'step': 15});
	});
}

function make_datepickers() {
	console.log('Making datepickers.');
	$.each($('#eventoccurrence_set-group .field-startTime input[id*=-startTime_0]'), function(index,inputfield) {
		$('#'+inputfield.id).datepicker();
	});
}


function set_new_times() {
	console.log('Setting new times.');
	var start_fields = $('#eventoccurrence_set-group .field-startTime input[id*=-startTime_1]').not('#id_eventoccurrence_set-__prefix__-startTime_1');
	var new_start_field = start_fields.last()[0];
	try {
		new_start_field.value = start_fields.not(new_start_field).last()[0].value;
	}
	catch(err) {}
		
	var end_fields = $('#eventoccurrence_set-group .field-endTime input[id*=-endTime_1]').not('#id_eventoccurrence_set-__prefix__-endTime_1');
	var new_end_field = end_fields.last()[0];
	try {
		new_end_field.value = end_fields.not(new_end_field).last()[0].value;
	}
	catch(err) {}
}

function set_end_dates() {
	console.log('Setting end dates.');
	$.each($('#eventoccurrence_set-group .dynamic-eventoccurrence_set'), function(index,setgroup) {
		$(setgroup).find('.field-endTime input[id*=-endTime_0]').val($(setgroup).find('.field-startTime input[id*=-startTime_0]').val());
	});
}

function set_new_dates() {
	console.log('Setting new dates.');
	var date_fields = $('#eventoccurrence_set-group .field-startTime input[id*=-startTime_0]').not('#id_eventoccurrence_set-__prefix__-startTime_0');
	var new_date_field = date_fields.last()[0];
	var old_date = new Date($(date_fields.not(new_date_field).last()[0]).val());
	var new_date = new Date();
	new_date.setTime(old_date.getTime() + 7 * 86400000);
	try {
		new_date_field.value = (new_date.getMonth() + 1) + '/' + new_date.getDate() + '/' + new_date.getFullYear();
	}
	catch(err) {}

	set_end_dates();
}