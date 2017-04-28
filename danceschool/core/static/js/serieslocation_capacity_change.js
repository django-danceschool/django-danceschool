$(document).ready(function(){
	var isInt = function(n) { return parseInt(Number(n)) === Number(n) };

	$('#id_location').change(function(){
		var this_default = $('#id_location option:selected').data('defaultcapacity');
		
		if (isInt(this_default)) {
			$('#id_capacity').val(Number(this_default));
		}
	});
});
