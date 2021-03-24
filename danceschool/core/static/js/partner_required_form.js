document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

    function disableNames() {
        $.each($("input[name$=customerId][value='0']"), function() {
            var prefix = $(this).attr('id').split('_').slice(0,4).join('_');

            if ($(this).prop('checked') === true) {
                $('#' + prefix + '_firstName').prop("disabled", false);
                $('#' + prefix + '_lastName').prop("disabled", false);
            }
            else {
                $('#' + prefix + '_firstName').prop("disabled", true);
                $('#' + prefix + '_lastName').prop("disabled", true);
            }
        });
    }
        
    // Updates names on load
    disableNames();

    // Update whenever a radio button is modified
    $("input[name$=customerId]").change(function(event){
		event.preventDefault();
        disableNames();
    });

});
