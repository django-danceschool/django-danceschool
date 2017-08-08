$(document).ready(function(){
	var isInt = function(n) { return parseInt(Number(n)) === Number(n) };

	function updateRoomOptions(updateCapacity, setRoomVal, allowEmptyRoomVal) {

		this_roomOptions = $('#id_location option:selected').data('roomoptions');
		
		if (!this_roomOptions) {
			this_roomOptions = [];
		}
		if (this_roomOptions.length == 1 && !setRoomVal && !allowEmptyRoomVal) {
			setRoomVal = this_roomOptions[0]['id'];
		}

		var new_option_text = '<option value="">---------</option>'

		for (var i = 0, len = this_roomOptions.length; i < len; i++) {
			new_option_text += '<option value="' + this_roomOptions[i]['id'] + '" data-defaultCapacity="' + this_roomOptions[i]['defaultCapacity'] + '">' + this_roomOptions[i]['name'] + '</option>';
		}
		
		// Clear out the choices in the room field and replace them with the new options
		$('#id_room').find('option').remove().end().append(new_option_text).val(setRoomVal);

		var this_default = $('#id_room option:selected').data('defaultcapacity');

		if (isInt(this_default) && updateCapacity) {
			$('#id_capacity').val(Number(this_default));
		}
	}

	$('#id_location').change(function(){
		updateRoomOptions(true);
	});
	$('#id_room').change(function(){
		var this_default = $('#id_room option:selected').data('defaultcapacity');
		
		if (isInt(this_default)) {
			$('#id_capacity').val(Number(this_default));
		}
	});

	// On load, if the location is not already set, then clear out the room options.
	// If the location and room are set, then update the room options, but don't
	// modify the prior capacity.
	if ($('#id_location option:selected').val()) {
		updateRoomOptions(false,$('#id_room option:selected').val(),true);
	}
	else {
		updateRoomOptions(false);
	}

});
