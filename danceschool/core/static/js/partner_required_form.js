document.addEventListener("DOMContentLoaded", function(event) {

    function disableNames() {
        document.querySelectorAll("input[name$=customerId][value='0']").forEach(function(el) {
            var prefix = el.id.split('_').slice(0,4).join('_');

            if (el.checked === true) {
                document.getElementById(prefix + '_firstName').disabled = false;
                document.getElementById(prefix + '_lastName').disabled = false;
            } else {
                document.getElementById(prefix + '_firstName').disabled = true;
                document.getElementById(prefix + '_lastName').disabled = true;
            }
        });
    }

    // Updates names on load
    disableNames();

    // Update whenever a radio button is modified
    document.querySelectorAll("input[name$=customerId]").forEach(function(el) {
        el.addEventListener('change', function() {
            disableNames();
        });
    });

});
