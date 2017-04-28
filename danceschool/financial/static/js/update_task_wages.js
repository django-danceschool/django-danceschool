$(document).ready(function(){
	$('#id_category').change(function(){
		var this_default = $('#id_category option:selected').data('defaultrate');
		$('#id_wageRate').val(this_default);
	});
});
