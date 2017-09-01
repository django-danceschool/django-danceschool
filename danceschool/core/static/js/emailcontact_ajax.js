$(document).ready(function(){

	function checkRichTextChoice() {
		var richTextChoice = $('#div_id_richTextChoice input:checked').val();

		if (CKEDITOR.instances['id_html_message']) {
			window.initial_CKEditor_config = CKEDITOR.instances['id_html_message'].config;
			CKEDITOR.instances['id_html_message'].destroy();		
		}

		if (richTextChoice == "plain") {
			$('#div_id_message').show();
			$('#div_id_html_message').hide();
		}
		if (richTextChoice == "HTML") {
			$('#div_id_message').hide();
			$('#div_id_html_message').show();
		}

		CKEDITOR.replace('id_html_message', window.initial_CKEditor_config);

	}

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

	CKEDITOR.on('pagePrepared', function() {
		checkRichTextChoice();
	});

	CKEDITOR.on('instanceReady', function() {
		CKEDITOR.fireOnce('pagePrepared');
	});

	$('#div_id_richTextChoice').change(function(event){
		checkRichTextChoice();
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

				// Fill in the ID for the
				CKEDITOR.instances['id_html_message'].destroy();		
				$('#id_html_message').val(data['html_content']);
				$('#div_id_richTextChoice input[value="' + data['richTextChoice'] + '"]').prop('checked',true);
				checkRichTextChoice();
			},
			failure: function() {
				console.log('Failed to retrieve template data using AJAX.');
			},
		});
	});

});