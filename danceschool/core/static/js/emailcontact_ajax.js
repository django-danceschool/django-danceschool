$(document).ready(function(){

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

	$('#id_template').change(function(event){
		event.preventDefault();

		var formData = {template: $('#id_template').val()};

		$.ajax({
			url: "/staff/sendemail/template/",
			type: "POST",
			data: formData,
			success: function(data, textStatus, jqXHR) {
				$('#id_subject').val(data['subject']);
				$('#id_message').val(data['content']);
				$('#div_id_template').slideUp();
			},
			failure: function() {
				console.log('Failed to retrieve template data using AJAX.');
			},
		});
	});
});