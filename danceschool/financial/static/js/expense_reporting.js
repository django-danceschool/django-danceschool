document.addEventListener("DOMContentLoaded", function(event) {

	$('#div_id_total').show();
	$('#div_id_hours').hide();

	// Make payment date field a datepicker
	$('#id_paymentDate').datepicker();

	$('#payment-event-start').click(function(event) {
		event.preventDefault();
		var startDate = $($('#id_event :selected').text()).data().startDate;
		if (startDate) {
			$('#id_paymentDate').val(startDate);
		}
	});

	$('input[name=payBy]').change(function(){
		var this_payBy = $('#div_id_payBy input:checked').val();

		if (this_payBy == "1") {
			$('#div_id_hours').show();
			$('#div_id_total').hide();
		}
		if (this_payBy == "2") {
			$('#div_id_hours').hide();
			$('#div_id_total').show();
		}
	});

});
