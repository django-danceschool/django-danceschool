(function($) {
$(document).ready(function(){

    var this_js_script = $('script[src*=classregistration_ajax]');
    var registration_url = this_js_script.attr('data-registration-url');
    if (typeof registration_url === "undefined" ) {
        var registration_url = '/register/';
     }

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

    $('.register-ajax').click(function(event) {
        event.preventDefault();
        var this_data = $(this).data();
        var this_role = (typeof this_data['roleId'] === 'undefined') ? null : this_data['roleId'];
        var this_type = (typeof this_data['eventType'] === 'undefined') ? 'event' : this_data['eventType'];
        var regData = {json: true};

        // Allow drop-ins or roles, but not both.
        if (this_data['dropinId']) {
            regData[this_type + '_' + this_data['id']] = '{"dropin_' + this_data['dropinId'] + '": true}';
        }
        else {
            regData[this_type + '_' + this_data['id']] = '{"role": ' + this_role + '}';
        }

        $.ajax({
            url: registration_url,
            type: "POST",
            data: regData,
            success: function(response){
                if(response.status == "success" && response.redirect) {
                    window.location.href = response.redirect;
                }
                else {
                    window.location.href = registration_url;
                }
            },
        });
    });
});
})(django.jQuery);
