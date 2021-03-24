document.addEventListener("DOMContentLoaded", function(e) {

	// Requires jQuery
	var $ = django.jQuery;
	
	$('#id_invoiceItem').attr('disabled',true);

	// Make received date field a datepicker
	$('#id_receivedDate').datepicker();

	// Keep track of previous value of grossTotal
	var grossField = $('#id_grossTotal');
	grossField.data('previous', grossField.val());

	// Use Jquery to get the cookie value of the CSRF token
	function getCookie(name) {
	    var cookieValue = null;
	    if (document.cookie && document.cookie !== '') {
	        var cookies = document.cookie.split(';');
	        for (var i = 0; i < cookies.length; i++) {
	            var cookie = $.trim(cookies[i]);
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

	grossField.change(function(event) {
		event.preventDefault();

		var priorGross = $(this).data("previous");
		var currentTotal = $('#id_total').val();
		var currentGross = $(this).val();

		if ((currentTotal == priorGross) || (currentTotal == "")) {
			$('#id_total').val(currentGross);
		}

		$(this).data("previous", currentGross);
	});

	$('#received-event-start').click(function(event) {
		event.preventDefault();
		var startDate = $($('#id_event :selected').text()).data().startDate;
		if (startDate) {
			$('#id_receivedDate').val(startDate);
		}
	});

	$('#id_event').change(function(event) {
		event.preventDefault();

		var formData = {event: $('#id_event').val()}
		var emptyFlag = true;

		$.ajax({
			url: "/financial/submit-revenues/eventfilter/",
			type: "POST",
			data: formData,
			success: function(data, textStatus, jqXHR) {

				$('#id_invoiceItem').empty();

				$('#id_invoiceItem').append($('<option></option>').val('').html('-----'));

				$.each(data['id_invoiceItem'], function(index,text) {
					$('#id_invoiceItem').append(
						$('<option></option>').val(index).html(text)
					);
					emptyFlag = false;
				});
				if (emptyFlag == false) {
					$('#div_id_invoiceItem').show();
					$('#id_invoiceItem').attr('disabled',false);
				}
				else {
					$('#id_invoiceItem').attr('disabled',true);
				}
			},
			failure: function() {
				console.log('Failed to retrieve dropdown data using AJAX.');
			},
		});
	});
});
