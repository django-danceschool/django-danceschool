document.addEventListener("DOMContentLoaded", function(event) {

    function updateIsMe() {
        var invoiceCustomer = document.getElementById('invoiceCustomer');
        if (!invoiceCustomer) {
            return;
        }

        var invoiceData = invoiceCustomer.dataset;

        document.querySelectorAll('[id$=isMe]').forEach(function(el) {
            var prefix = el.id.split('_').slice(0, -1).join('_');
            var firstNameEl = document.getElementById(prefix + '_firstName');
            var lastNameEl = document.getElementById(prefix + '_lastName');
            var emailEl = document.getElementById(prefix + '_email');
            var studentEl = document.getElementById(prefix + '_student');

            if (!firstNameEl || !lastNameEl || !emailEl) {
                return;
            }

            if (el.checked === true) {
                firstNameEl.value = invoiceData.firstName;
                lastNameEl.value = invoiceData.lastName;
                emailEl.value = invoiceData.email;
                if (studentEl) {
                    studentEl.checked = (invoiceData.student === "True");
                }

                firstNameEl.disabled = true;
                lastNameEl.disabled = true;
                emailEl.disabled = true;
                if (studentEl) {
                    studentEl.disabled = true;
                }
            } else {
                firstNameEl.disabled = false;
                lastNameEl.disabled = false;
                emailEl.disabled = false;
                if (studentEl) {
                    studentEl.disabled = false;
                }
            }
        });
    }

    // Updates names on load
    updateIsMe();

    // Update whenever a checkbox is modified
    document.querySelectorAll('[id$=isMe]').forEach(function(el) {
        el.addEventListener('change', function(event) {
            event.preventDefault();
            updateIsMe();
        });
    });

    // Ensures that the names from disabled fields are submitted
    document.querySelector('form').addEventListener('submit', function(event) {
        document.querySelectorAll('[id^=id_er]').forEach(function(el) {
            el.disabled = false;
        });
        return true;
    });

});
