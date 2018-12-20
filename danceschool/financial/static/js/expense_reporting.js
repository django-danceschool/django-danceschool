$(document).ready(function(){
	$('#div_id_hours').show();
	$('#div_id_total').hide();

	// Make payment date field a datepicker
	$('#id_paymentDate').datepicker();

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
