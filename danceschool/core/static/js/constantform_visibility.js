$(document).ready(function(){

	function checkVisibility() {
		var valueType = $('#id_valueType').val();

		if (valueType == "float") {
			$('div.field-valueFloat').show();
			$('div.field-valueBool').hide();
			$('div.field-valueStr').hide();
		}
		if (valueType == "bool") {
			$('div.field-valueFloat').hide();
			$('div.field-valueBool').show();
			$('div.field-valueStr').hide();
		}
		if (valueType == "str") {
			$('div.field-valueFloat').hide();
			$('div.field-valueBool').hide();
			$('div.field-valueStr').show();
		}
	}

	checkVisibility();

	$('#id_valueType').change(function(event){
		checkVisibility();
	});
});