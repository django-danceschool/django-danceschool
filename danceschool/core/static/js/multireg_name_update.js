document.addEventListener("DOMContentLoaded", function(event) {

	// The code below requires jQuery
	var $ = django.jQuery;

    function updateIsMe() {
        var invoice_data = $('#invoiceCustomer').data();

        $.each($("[id$=isMe]"), function() {
            var prefix = $(this).attr('id').split('_').slice(0,3).join('_')

            if ($(this).prop('checked') === true) {

                $('#' + prefix + '_firstName').val(invoice_data.firstName);
                $('#' + prefix + '_lastName').val(invoice_data.lastName);
                $('#' + prefix + '_email').val(invoice_data.email);
                $('#' + prefix + '_student').prop('checked', (invoice_data.student === "True"));
    
                $('#' + prefix + '_firstName').prop("disabled", true);
                $('#' + prefix + '_lastName').prop("disabled", true);
                $('#' + prefix + '_email').prop("disabled", true);
                $('#' + prefix + '_student').prop("disabled", true);
            }
            else {
                $('#' + prefix + '_firstName').prop("disabled", false);
                $('#' + prefix + '_lastName').prop("disabled", false);
                $('#' + prefix + '_email').prop("disabled", false);
                $('#' + prefix + '_student').prop("disabled", false);
            }
        });

    }
        
    // Updates names on load
    updateIsMe();

    // Update whenever a checkbox is modified
    $('[id$=isMe]').change(function(event){
		event.preventDefault();
        updateIsMe();
    });

    // Ensures that the names from disabled fields are submitted
    $('form').submit(function(event) {
        $('[id^=id_er]').prop("disabled", false);
        return true;
    })

});
