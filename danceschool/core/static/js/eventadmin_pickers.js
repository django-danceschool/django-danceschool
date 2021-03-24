document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

	$(document).on('formset:added', function(event, $row, formsetName) {
		if (formsetName == 'eventoccurrence_set') {
			makepickers();
			set_new_times();
			set_new_dates();
    	}
    });

	function makepickers() {
		// Add classes needed to make the datepair work
		$('.dynamic-eventoccurrence_set input[id*=Time_0]').addClass('makeDatePicker');
		$('.dynamic-eventoccurrence_set input[id*=Time_1]').addClass('makeTimePicker');
		$('.dynamic-eventoccurrence_set input[id*=-startTime]').addClass('startTimePicker');
		$('.dynamic-eventoccurrence_set input[id*=-endTime]').addClass('endTimePicker');
	
		$.each($('.dynamic-eventoccurrence_set'), function() {

			$(this).find('.makeTimePicker').timepicker({
				'scrollDefault': '7:00pm', 'step': 15,'showDuration': true,'timeFormat':'g:ia',
			});
			$(this).find('.makeDatePicker').datepicker({
				'dateFormat': 'yy-mm-dd',
			});

			var datepair = new Datepair($(this)[0],{
				'dateClass': 'makeDatePicker',
				'timeClass': 'makeTimePicker',
				'startClass': 'startTimePicker',
				'endClass': 'endTimePicker',

				// We specify these to avoid potential namespace issues related
				// to multiple jQuery instances.
				parseTime: function(input){
					return $(input).timepicker('getTime');
				},
				updateTime: function(input, dateObj){
					$(input).timepicker('setTime', dateObj);
				},
				setMinTime: function(input, dateObj){
					$(input).timepicker('option', 'minTime', dateObj);
				},
				parseDate: function(input){
					return input.value && $(input).datepicker('getDate');
				},
				updateDate: function(input, dateObj){
					$(input).datepicker('update', dateObj);
				}
			});
		});
	}
	
	function set_new_times() {
		var start_fields = $('.dynamic-eventoccurrence_set input[id*=-startTime_1]');
		var new_start_field = start_fields.last()[0];
		try {
			new_start_field.value = start_fields.not(new_start_field).last()[0].value;
		}
		catch(err) {}
			
		var end_fields = $('.dynamic-eventoccurrence_set input[id*=-endTime_1]');
		var new_end_field = end_fields.last()[0];
		try {
			new_end_field.value = end_fields.not(new_end_field).last()[0].value;
		}
		catch(err) {}
	}
	
	function set_new_dates() {
		// Requires moment.js
	
		var startDate_fields = $('.dynamic-eventoccurrence_set input[id*=-startTime_0]');
		var new_startDate_field = startDate_fields.last()[0];
		var old_startDate = moment($(startDate_fields.not(new_startDate_field).last()[0]).val());
		if (old_startDate.isValid()) {
			new_startDate_field.value = old_startDate.add(7,'days').format('YYYY-MM-DD');
		}
	
		var endDate_fields = $('.dynamic-eventoccurrence_set input[id*=-endTime_0]');
		var new_endDate_field = endDate_fields.last()[0];
		var old_endDate = moment($(endDate_fields.not(new_endDate_field).last()[0]).val());
		if (old_endDate.isValid()) {
			new_endDate_field.value = old_endDate.add(7,'days').format('YYYY-MM-DD');
		}
	}

	$(document).ready(function() {
		makepickers();
	});

});