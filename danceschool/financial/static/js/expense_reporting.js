$(document).ready(function(){
	$('#div_id_payToLocation').hide();
	$('#div_id_payToName').hide();
	$('#div_id_hours').show();
	$('#div_id_total').hide();

	// Make payment date field a datepicker
	$('#id_paymentDate').datepicker();

	$('input[name=payTo]').change(function(){
		var this_payTo = $('#div_id_payTo input:checked').val();

		if (this_payTo == "1") {
			$('#div_id_payToLocation').hide();
			$('#div_id_payToName').hide();
		}
		if (this_payTo == "2") {
			$('#div_id_payToLocation').show();
			$('#div_id_payToName').hide();
		}
		if (this_payTo == "3") {
			$('#div_id_payToLocation').hide();
			$('#div_id_payToName').show();
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
