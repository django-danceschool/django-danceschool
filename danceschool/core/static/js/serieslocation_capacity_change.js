document.addEventListener("DOMContentLoaded", function(event) {

	var isInt = function(n) { return parseInt(Number(n)) === Number(n) };

	function updateRoomOptions(updateCapacity, setRoomVal, allowEmptyRoomVal) {
		var locationSelect = document.getElementById('id_location');
		var roomSelect = document.getElementById('id_room');
		var selectedLocation = locationSelect.options[locationSelect.selectedIndex];

		// Room options are stored as data-roomOptions on the option element (set by LocationWithDataWidget),
		// or as _roomoptions (set by location_related_objects_lookup.js after a popup add/change).
		var this_roomOptions = selectedLocation ? (
			selectedLocation._roomoptions ||
			JSON.parse(selectedLocation.dataset.roomoptions || '[]')
		) : [];
		if (this_roomOptions.length == 1 && !setRoomVal && !allowEmptyRoomVal) {
			setRoomVal = this_roomOptions[0]['id'];
		}

		var new_option_text = '<option value="">---------</option>';

		for (var i = 0, len = this_roomOptions.length; i < len; i++) {
			new_option_text += '<option value="' + this_roomOptions[i]['id'] + '" data-defaultCapacity="' + this_roomOptions[i]['defaultCapacity'] + '">' + this_roomOptions[i]['name'] + '</option>';
		}

		// Clear out the choices in the room field and replace them with the new options
		roomSelect.innerHTML = new_option_text;
		if (setRoomVal !== undefined) {
			roomSelect.value = setRoomVal;
		}

		var selectedRoom = roomSelect.options[roomSelect.selectedIndex];
		var this_default = selectedRoom ? selectedRoom.dataset.defaultcapacity : null;

		if (isInt(this_default) && updateCapacity) {
			document.getElementById('id_capacity').value = Number(this_default);
		}
	}

	document.getElementById('id_location').addEventListener('change', function(){
		updateRoomOptions(true);
	});

	document.getElementById('id_room').addEventListener('change', function(){
		var roomSelect = document.getElementById('id_room');
		var selectedRoom = roomSelect.options[roomSelect.selectedIndex];
		var this_default = selectedRoom ? selectedRoom.dataset.defaultcapacity : null;

		if (isInt(this_default)) {
			document.getElementById('id_capacity').value = Number(this_default);
		}
	});

	// On load, if the location is not already set, then clear out the room options.
	// If the location and room are set, then update the room options, but don't
	// modify the prior capacity.
	var locationSelect = document.getElementById('id_location');
	var roomSelect = document.getElementById('id_room');
	if (locationSelect.value) {
		updateRoomOptions(false, roomSelect.value, true);
	} else {
		updateRoomOptions(false);
	}
});
