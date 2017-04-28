$(document).ready(function(){
	$('#id_occurrences').attr('disabled',true);
	$('#id_occurrences').parent('p').hide();
	$('#id_replacedStaffMember').attr('disabled',true);
	$('#id_replacedStaffMember').parent('p').hide();

	// Use Jquery to get the cookie value of the CSRF token
	function getCookie(name) {
	    var cookieValue = null;
	    if (document.cookie && document.cookie !== '') {
	        var cookies = document.cookie.split(';');
	        for (var i = 0; i < cookies.length; i++) {
	            var cookie = jQuery.trim(cookies[i]);
	            // Does this cookie string begin with the name we want?
	            if (cookie.substring(0, name.length + 1) === (name + '=')) {
	                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
	                break;
	            }
	        }
	    }
	    return cookieValue;
	}
	var csrftoken = getCookie('csrftoken');

	function csrfSafeMethod(method) {
	    // these HTTP methods do not require CSRF protection
	    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
	}

	// Ensure that CSRF token is passed
	$.ajaxSetup({
	    beforeSend: function(xhr, settings) {
	        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
	            xhr.setRequestHeader("X-CSRFToken", csrftoken);
	        }
	    }
	});


	$('#id_event').change(function(event){
		event.preventDefault();

		var formData = {event: $('#id_event').val()};

		$.ajax({
			url: "/staff/substitute/filter/",
			type: "POST",
			data: formData,
			success: function(data, textStatus, jqXHR) {
				$('#id_occurrences').empty();
				$('#id_replacedStaffMember').empty();

				$.each(data['id_occurrences'], function(index,text) {
					$('#id_occurrences').append(
						$('<option></option>').val(index).html(text)
					);
				});
				$.each(data['id_replacedStaffMember'], function(index,text) {
					$('#id_replacedStaffMember').append(
						$('<option></option>').val(index).html(text)
					);
				});
				$('#id_occurrences').parent('p').show();
				$('#id_replacedStaffMember').parent('p').show();
				$('#id_occurrences').attr('disabled',false);
				$('#id_replacedStaffMember').attr('disabled',false);
			},
			failure: function() {
				console.log('Failed to retrieve dropdown data using AJAX.');
			},
		});
	});
});