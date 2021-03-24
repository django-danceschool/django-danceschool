document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

	function checkSendToSet() {
		var sendToSet = $('#div_id_sendToSet input:checked').val();

		if (sendToSet == "series") {
			$('#div_id_series').show();
			$('#div_id_month').hide();
		}
		if (sendToSet == "month") {
			$('#div_id_series').hide();
			$('#div_id_month').show();
		}
	}

	checkSendToSet();

	$('#div_id_sendToSet').change(function(event){
		checkSendToSet();
	});
});
