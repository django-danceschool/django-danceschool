$(document).ready(function() {

    // This function makes and returns a deep copy of the existing regData.
    // It's useful for error handling.
    function deepCopyFunction(regData) {
        if(typeof regData !== "object" || regData === null) {
            return regData // Return the value if inObject is not an object
          }
        
          // Create an array or object to hold the values
          var deepCopy = Array.isArray(regData) ? [] : {};

          for (key in regData) {
            value = regData[key];
        
            // Recursively (deep) copy for nested objects, including arrays
            deepCopy[key] = (typeof value === "object" && value !== null) ? deepCopyFunction(value) : value;
          }

        return deepCopy;
    }

    // Used to format string to title case.
    function toTitleCase(str) {
        return str.replace(
          /\w\S*/g,
          function(txt) {
            return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
          }
        );
    }

    // Used to clear out regData as needed (expired registration, initial
    // page load, cart cleared)
    function initializeRegData() {
        regData = {
            id: null, // Invoice ID, if passed
            payAtDoor: regParams.payAtDoor, // Used for registration pricing
            grossTotal: 0, // Total before discounts or vouchers
            total: 0, // Total after discounts and vouchers have been applied
            taxes: 0, // Any applicable taxes
            adjustments: 0, // Any applicable adjustments
            outstandingBalance: 0, // The total amount to be paid
            buyerPaysSalesTax: true, // If true, taxes are shown in the subtotal line
            itemCount: 0,
            items: [], // Information on each item in the cart
            discounts: [], // Information about discounts, if applicable
            voucher: {}, // Information on an applied voucher, if applicable
            addonItems: [], // List of add-on items, if applicable
        };
    }

    // Initalize regData once at page load.
    initializeRegData();
    $('#cartTotal').text(0);

    function refreshCart() {
        // First, clear the existing shopping cart and remove existing alerts.
        $('#cartSummary').css('display', 'none');
        $('#cartItems').text('');
        $('#subtotalLine').text('');
        $('#discountList').text('');
        $('#preTaxVoucherList').text('');
        $('#addonList').text('');
        $('#taxInfo').text('');
        $('#postTaxVoucherList').text('');
        $('#adjustmentInfo').text('');
        $('.badge-choice-counter').text('');;
        $('#cart-submit').addClass('invisible');

        // Then, add items based on regData
        $.each(regData.items, function() {
            this_data_string = 'data-choice-id="' + this.choiceId + '" ';
            this_name = this.description;

            if (this.type == "eventRegistration") {
                if (this.roleName) {
                    this_name += ': ' + this.roleName;
                }
                else if (this.dropIn === true) {
                    this_name += ': ' + regParams.dropInString;
                }
                this_data_string += 'data-event="' + this.eventId +
                    '" data-event-reg="' + this.eventRegistrationId + '"';
            }
            else if (this.type == "merchItem") {
                this_data_string += 'data-item-variant="' + this.variantId +
                    '" data-order-item="' + this.itemId + '"';
            }
            var this_price = parseFloat(this.grossTotal).toFixed(2);
    
            // Add item to the shopping cart
            $('#cartItems').append(
                '<tr ' + this_data_string + '><td>' +
                    this_name +
                '</td><td>' +
                    regParams.currencySymbol + this_price +
                '<button type="button" class="close remove-item" aria-label="Remove" data-id="' + this.id + '"><span aria-hidden="true">&times;</span></button></td></tr>'
            );

            // Update the badge for the button that was pressed for each selection.
            if (this.choiceId) {
                var this_badge = $("#" + this.choiceId + " .badge-choice-counter");
                this_badge.text(this.quantity || (parseInt(this_badge.text() | 0) + 1));
            }
        });

        // Add discounts
        $.each(regData.discounts, function() {
            $('#discountList').append(
                '<tr class="discount"><td><strong>' + regParams.discountString +
                ':</strong> ' + this.name + '</td><td> -' +
                regParams.currencySymbol + parseFloat(this.discount_amount).toFixed(2) + '</td></tr>'
            );
        });

        // Add vouchers
        if (regData.voucher.hasOwnProperty('voucherAmount') && regData.voucher.voucherAmount > 0) {
            if (regData.voucher.hasOwnProperty('voucherName')) {
                var voucherText = regData.voucher.voucherName + ' (' + regData.voucher.voucherId + ')';
            }
            else {
                var voucherText = '';
            }

            if(regData.voucher.beforeTax === true) {
                var voucherTbody = '#preTaxVoucherList'
            }
            else {
                var voucherTbody = '#postTaxVoucherList'
            }

            $(voucherTbody).append(
                '<tr class="voucher"><td><strong>' + regParams.voucherString +
                ':</strong> ' + voucherText +'</td><td> -' +
                regParams.currencySymbol + parseFloat(regData.voucher.voucherAmount).toFixed(2) + 
                '<button type="button" class="close remove-voucher" aria-label="Remove"><span aria-hidden="true">&times;</span></button></td></tr>'
            );
        }

        // Add add-ons
        $.each(regData.addonItems, function() {
            $('#addonList').append(
                '<tr class="addons"><td><strong>' + regParams.addonString + ':</strong> ' +
                this + '</td><td></td></tr>'
            );
        });

        if (regData.taxes !== 0 && regData.buyerPaysSalesTax === true) {
            $('#taxInfo').append(
                '<tr class="taxes"><td>' + regParams.taxesString + ':</td><td>' + regParams.currencySymbol + parseFloat(regData.taxes).toFixed(2) + '</td></tr>'
            );
        }

        // If there are discounts, vouchers, or add-ons, add a subtotal line (grossTotal)
        if (
            $('#discountList').text() !== '' ||
            $('#preTaxVoucherList').text() !== '' ||
            $('#addonList').text() !== '' ||
            $('#postTaxVoucherList').text() !== '' ||
            $('#taxInfo').text() !== ''
        ) {
            $('#subtotalLine').append(
                '<tr class="subtotal"><th>' + regParams.subtotalString + ':</th><th>' + regParams.currencySymbol + parseFloat(regData.grossTotal).toFixed(2) + '</th></tr>'
            );
        }

        var itemString = regParams.itemStringPlural;
        if (regData.itemCount == 1) {
            itemString = regParams.itemString;
        }

        $('item').text(regData.itemsCount).css('display', 'block');
        $('#cartTotal').text(parseFloat(regData.outstandingBalance).toFixed(2));
        $('#cartSummary').text(regData.itemCount + ' ' + itemString + ': ' + regParams.currencySymbol + parseFloat(regData.outstandingBalance).toFixed(2));

        if (regData.hasOwnProperty('addonItems') && regData.addonItems.length > 0) {
            $('#addonList').removeClass('invisible');
        }
        else {
            $('#addonList').addClass('invisible');            
        }

        if (regData.itemCount > 0) {
            $('#cartSummary').css('display', 'block');
            $('#cart-submit').removeClass('invisible');
        }
        else {;
            $('#cartSummary').css('display', 'none');
            $('#cart-submit').addClass('invisible');
        }

        // Add any alerts from invalid vouchers and unset the voucher ID.
        if (regData.voucher.hasOwnProperty('errors')) {            
            var errorText = '<ul>';
            for (const [key, error] of Object.entries(regData.voucher.errors)) {
                errorText += '<li>' + error.message + '</li>';
            }
            errorText += '</ul>';
            addAlert(errorText);
            
            regData.voucher.voucherId = '';
        }
    }

    function submitData(prior, redirect=false, removeAlerts=false){

        // The Ajax view should only return a redirect URL if we are moving forward.
        if (redirect) {
            regData.finalize = true;
        }

        $.ajax({
            url: regParams.registerUrl,
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify(regData),
            success: function(response){

                if(response.status == "success" && response.redirect && redirect === true) {
                    window.location.href = response.redirect;
                }
                else if(response.status == "success") {
                    regData = response.invoice;

                    if (removeAlerts === true) {
                        // Remove any existing alerts.
                        $('.alert').alert('close')
                    }

                    // Ensure that some properties of the response are defined to avoid errors.
                    if (!regData.hasOwnProperty('voucher')) {
                        regData.voucher = {};
                    }
                    if (!regData.hasOwnProperty('discounts')) {
                        regData.discounts = [];
                    }
                    if (!regData.hasOwnProperty('addonItems')) {
                        regData.discounts = [];
                    }

                    refreshCart();
                }
                else {
                    var errorText = '<ul>';
                    for (const [key, error] of Object.entries(response.errors)) {
                        errorText += '<li>' + error.message + '</li>';
                    }
                    errorText += '</ul>';
                    addAlert(errorText);

                    // reset regData for expired invoices
                    if (response.errors.filter(function(e){return e.code == 'expired'}).length > 0) {
                        initializeRegData();
                    }
                    // Otherwise, return to whatever previous regData was passed.
                    else {
                        regData = deepCopyFunction(prior);
                    }

                    refreshCart();
                }
            },
        });
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

    function addAlert(message, alertClass="alert-danger") {
        $('#alert-box').append(
            '<div class="alert ' + alertClass + ' my-1 alert-dismissible fade show" role="alert">' +
            '<button type="button" class="close" data-dismiss="alert" aria-label="Close">' +
            '<span aria-hidden="true">&times;</span></button>' +
            '<span class="register-alert-text">' + message + '</span>'
        );
    }

    // Ensure that CSRF token is passed
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });

    // Add Item to Cart
    $('.add-item').click(function (){

        // Grab the data and also add the ID of the element that was clicked.
        var this_data = $(this).data();

        // Copy existing regData in case there is an error
        var old_regData = deepCopyFunction(regData);

        // Events can also be set to apply vouchers at the same time.
        if (this_data.voucherId) {
            // If an existing voucher code exists, then we can't add a new one
            // without removing the old one.
            if (
                regData.voucher.hasOwnProperty('voucherId') &&
                regData.voucher.voucherId !== '' &&
                regData.voucher.voucherId !== this_data.voucherId
            ) {
                addAlert(regParams.multipleVoucherString);
                return;
            }

            regData.voucher.voucherId = this_data.voucherId;
            delete this_data.voucherId;
        }

        // The student attribute actually applies to the registration, not to
        // one particular item, so move this to the correct place in regData
        if (this_data.student === true) {
            regData.student = this_data.student;
            delete this_data.student;
        }

        if (this_data.type == "eventRegistration") {
            // Avoid passing anything but integer values for role ID, which will
            // happen when registration buttons have no associated role.
            if (isNaN(parseInt(this_data.roleId))) {
                delete this_data.roleId;
            }
        }

        var prior_choice = regData.items.findIndex(item => item.choiceId === this_data.choiceId);

        if (
            this_data.updateQuantity === true && this_data.quantity &&
            prior_choice !== -1
        ) {
            regData.items[prior_choice].quantity += this_data.quantity;
        }
        else {
            // Add the data from the button to the regData and submit
            regData['items'].push(this_data);
        }
        submitData(prior=old_regData, redirect=false, removeAlerts=true);

    });

    // Hide and Show Cart Items
    $('.openCloseCart').click(function(){
        $('#shoppingCart').toggle();
    });

    // Empty Cart
    $('#emptyCart').click(function() {
        initializeRegData();
        submitData(prior=regData, redirect=false, removeAlerts=true);
    });

    // Remove Item From Cart
    $('#shoppingCart').on('click', '.remove-item', function(){

        // Copy existing regData in case there is an error
        var old_regData = deepCopyFunction(regData);

        var this_item_id = $($(this).closest('tr')).data('choiceId');

        if (this_item_id) {
            for( var i = 0; i < regData.items.length; i++){ 
                if ( regData.items[i]['choiceId'] === this_item_id) {
                  regData.items.splice(i, 1); 
                  i--;
                }
             }
        }
        
        submitData(prior=old_regData, redirect=false);
    });

    // Submit registration
    $('.submit-button').click(function(e) {
        e.preventDefault();
        submitData(prior=regData, redirect=true);
    });

    // Add voucher code
    $('.add-voucher').click(function () {

        var this_code = $(this).data('id');
        if (!this_code) {
            this_code = $(this).closest('.voucherDetail').find('input').val();
        }

        // If an existing voucher code exists, then we can't add a new one without removing the old one.
        if (
            this_code !== '' && regData.voucher.hasOwnProperty('voucherId') &&
            regData.voucher.voucherId !== '' && regData.voucher.voucherId !== this_code
        ) {
            addAlert(regParams.multipleVoucherString);
            return;
        }

        // Copy existing regData in case there is an error
        var old_regData = deepCopyFunction(regData);

        regData.voucher.voucherId = this_code;

        if ($.isEmptyObject(regData['items'])) {
            addAlert(regParams.emptyRegisterVoucherString, alertClass='alert-info');
        }
        else {
            submitData(prior=old_regData, redirect=false);
        }
    });

    // Remove voucher code
    $('#shoppingCart').on('click', '.remove-voucher', function(){

        // Copy existing regData in case there is an error
        var old_regData = deepCopyFunction(regData);
        regData.voucher = {};
        submitData(prior=old_regData, redirect=false);
    });

    // Lookup customer
    $('#id_name').change(function() {

        var this_data = $($(this).find(':selected').text()).data();

        if (this_data['type'] == regParams.customerString) {
            var ajaxData = {
                id: this_data['id'],
                guestType: this_data['type'],
                date: regParams.registerDate,
                eventList: regParams.guestLookupEvents,
            };

            $('#guestInfoTable tbody tr td').empty();
            $('#guestInfoTable').addClass('d-none');
            $('#customerInfoTable tbody').empty();
            $('#customerInfoCard').removeClass('collapse');
            $('#customerInfoCard').addClass('show');

            $.ajax({
                url: regParams.customerLookupUrl,
                type: "POST",
                contentType: "application/json",
                data: JSON.stringify(ajaxData),
                success: function(response){
    
                    console.log(response);

                    $('#customerInfoTable').removeClass('d-none');

                    $.each(response, function() {
                        $('#customerInfoExample tr').clone().appendTo($('#customerInfoTable tbody'));
                        var this_row = $('#customerInfoTable tbody tr:last');

                        var statusString = this.registration.invoice.statusLabel;
                        if (this.registration.invoice.outstandingBalance > 0) {
                            statusString += ' (' + regParams.outstandingBalanceString + ' ' + regParams.currencySymbol + parseFloat(this.registration.invoice.outstandingBalance).toFixed(2) + ')';
                        }

                        this_row.find('.customerCheckIn').attr('id', 'checkIn_' + this.id + '_' + this.occurrenceId);
                        this_row.find('.customerCheckInLabel').attr('for', 'checkIn_' + this.id);
                        this_row.find('.customerCheckIn').attr('checked', this.checkedIn);
                        this_row.find('.customerCheckIn').attr('value', this.id);
                        this_row.find('.customerCheckIn').data('occurrence-id', this.occurrenceId);
                        this_row.find('.customerCheckIn').data('event-id', this.event.id);
                        this_row.find('.customerInfoEvent').text(this.event.name);
                        this_row.find('.customerInfoTime').text(moment(this.occurrenceStartTime).format('LT'));
                        var role_text = "";
                        if (this.dropIn == true) {
                            role_text += regParams.dropInString + ' ';
                        }
                        if (this.role.name) {
                            role_text += this.role.name;
                        }
                        this_row.find('.customerInfoRole').text(role_text);
                        this_row.find('.customerInfoStudent').text(toTitleCase(this.registration.student.toString()));
                        this_row.find('.customerInfoPaymentStatus').text(statusString);
                        this_row.find('.customerInvoiceLink').attr('href',this.registration.invoice.url);
                        this_row.find('.customerRegistrationLink').attr('href',this.registration.url);
                    });
    
                },
            });
        }
        else if (this_data['type']) {
            var ajaxData = {
                id: this_data['id'],
                guestListId: this_data['guestListId'],
                modelType: this_data['modelType'],
                date: regParams.registerDate,
                eventList: regParams.guestLookupEvents,
                checkinType: "O",
            };

            $('#customerInfoTable tbody').empty();
            $('#customerInfoTable').addClass('d-none');
            $('#customerInfoCard').removeClass('collapse');
            $('#customerInfoCard').addClass('show');
            $('#guestInfoTable tbody').empty();

            $.ajax({
                url: regParams.guestLookupUrl,
                type: "POST",
                contentType: "application/json",
                data: JSON.stringify(ajaxData),
                success: function(response){
                    $('#guestInfoTable').removeClass('d-none');

                    $.each(response.events, function() {
                        $('#guestInfoExample tr').clone().appendTo($('#guestInfoTable tbody'));
                        var this_row = $('#guestInfoTable tbody tr:last');

                        this_row.find('.customerCheckIn').attr('id', 'checkIn_' + this.id + '_' + this.eventId);
                        this_row.find('.customerCheckInLabel').attr('for', 'checkIn_' + this.id + '_' + this.eventId);
                        this_row.find('.customerCheckIn').attr('checked', this.checkedIn);
                        this_row.find('.customerCheckIn').attr('value', this.id);
                        this_row.find('.customerCheckIn').data('first-name', this.firstName);
                        this_row.find('.customerCheckIn').data('last-name', this.lastName);
                        this_row.find('.customerCheckIn').data('model-type', this.modelType);
                        this_row.find('.customerCheckIn').data('event-id', this.eventId);
                        this_row.find('.customerCheckIn').data('occurrence-id', this.occurrenceId);
                        this_row.find('.guestInfoEvent').text(this.eventName);
                        this_row.find('.guestInfoType').text(this.guestType);
                    });
                },
            });
        }
        else {
            $('#guestInfoTable tbody').empty();
            $('#guestInfoTable').addClass('d-none');
            $('#customerInfoTable tbody').empty();
            $('#customerInfoTable').addClass('d-none');
        }
    });

    // Check-in customer, guest.
    $(document).on("click", ".customerCheckIn", function() {

        $(this).attr("disabled", true);
        var initial_status = ($(this).prop('checked') == false);

		var this_request = {
			request: "update",
			event_id: $(this).data('eventId'),
            checkin_type: "O",
            occurrence_id: $(this).data('occurrenceId'),
        };

        if ($(this).hasClass("guestCheckIn")) {
            this_request["names"] = [{
                first_name: $(this).data("firstName"),
                last_name: $(this).data("lastName"),
                cancelled: ($(this).prop('checked') == false),
            },];
        }
        else if ($(this).hasClass("registrationCheckIn")) {
            this_request["registrations"] = [{
                id: $(this).attr("value"),
                cancelled: ($(this).prop('checked') == false),
            },];
        }

	    $.ajax(
	    {
	        url : regParams.checkInUrl,
	        type: "POST",
            contentType: "application/json",
            data: JSON.stringify(this_request),
	        success:function(data, textStatus, jqXHR)
	        {
                if (data["status"] == "success") {
                    setTimeout(function() {
                        $(".customerCheckIn,.guestCheckIn").removeAttr("disabled");
                    }, 500);
				}
				else {
                    console.log('Update failure! Resetting to: ' + initial_status);
                    setTimeout(function() {
                        // Reset the checkbox before re-enabling it.
                        $(this).prop('checked', initial_status);
                        $(".customerCheckIn,.guestCheckIn").removeAttr("disabled");
                    }, 500);
                }
	        },
	        error: function(jqXHR, textStatus, errorThrown)
	        {
                console.log('Update failure! Resetting to: ' + initial_status);
                setTimeout(function() {
                    // Reset the checkbox before re-enabling it.
                    $(this).prop('checked', initial_status);
                    $(".customerCheckIn").removeAttr("disabled");
                }, 500);
            }
	    });
    });
});
