$(document).ready(function() {

    // Used to clear out regData as needed (expired registration, inital page load, cart cleared)
    function initializeRegData() {
        regData = {
            payAtDoor: regParams.payAtDoor,
            subtotal: 0,
            total: 0,
            itemCount: 0,
            events: {},
        }
    }

    // Initalize regData once at page load.
    initializeRegData();
    $('#cartTotal').text(0);

    function refreshCart() {
        // First, clear the existing shopping cart and remove existing alerts.;
        $('#cartSummary').css('display', 'none');
        $('#cartItems').text('');
        $('#subtotalLine').text('');
        $('#discountList').text('');
        $('#voucherList').text('');
        $('#addonList').text('');
        $('#cart-submit').addClass('invisible');

        // Then, add the items based on regData;
        $.each(regData['events'], function() {
            var this_name = this['name']
            if (this['roleName']) {
                this_name += ': ' + this['roleName'];
            }
            else if (this['dropIn']) {
                this_name += ': ' + regParams.dropInString;
            }
            var this_price = parseFloat(this['price']).toFixed(2);
    
            $('#cartItems').append(
                '<tr data-event="' + this['event'] + '" data-eventreg="' + this['eventreg'] + '"><td>' +
                    this_name +
                '</td><td>' +
                    regParams.currencySymbol + this_price +
                '<button type="button" class="close remove-item" aria-label="Remove" data-id="' + this['event'] + '"><span aria-hidden="true">&times;</span></button></td></tr>'
            );
        });

        // Add discounts
        $.each(regData['discounts'], function() {
            $('#discountList').append(
                '<tr class="discount"><td><strong>' + regParams.discountString +
                ':</strong> ' + this.name + '</td><td> -' +
                regParams.currencySymbol + parseFloat(this.discount_amount).toFixed(2) + '</td></tr>'
            );
        });

        // Add vouchers
        if (regData.hasOwnProperty('voucher_amount') && regData.voucher_amount > 0) {
            if (regData.hasOwnProperty('voucher')) {
                var voucherText = regData.voucher.name + ' (' + regData.voucher.id + ')';
            }
            else {
                var voucherText = '';
            }

            $('#voucherList').append(
                '<tr class="voucher"><td><strong>' + regParams.voucherString +
                ':</strong> ' + voucherText +'</td><td> -' +
                regParams.currencySymbol + parseFloat(regData.voucher_amount).toFixed(2) + 
                '<button type="button" class="close remove-voucher" aria-label="Remove"><span aria-hidden="true">&times;</span></button></td></tr>'
            );
        }

        // Add add-ons;
        $.each(regData['addonItems'], function() {
            $('#addonList').append(
                '<tr class="addons"><td><strong>' + regParams.addonString + ':</strong> ' +
                this + '</td><td></td></tr>'
            );
        });

        // If there are discounts, vouchers, or add-ons, add a subtotal line
        if (
            $('#discountList').text() !== '' ||
            $('#voucherList').text() !== '' ||
            $('#addonList').text() !== ''
        ) {
            $('#subtotalLine').append(
                '<tr class="subtotal"><th>' + regParams.subtotalString + ':</th><th>' + regParams.currencySymbol + parseFloat(regData.subtotal).toFixed(2) + '</th></tr'
            );
        }

        var itemString = regParams.itemStringPlural;
        if (regData.itemCount == 1) {
            itemString = regParams.itemString;
        }

        $('item').text(regData.itemsCount).css('display', 'block');
        $('#cartTotal').text(parseFloat(regData.total).toFixed(2));
        $('#cartSummary').text(regData.itemCount + ' ' + itemString + ': ' + regParams.currencySymbol + parseFloat(regData.total).toFixed(2));

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
        if (regData.hasOwnProperty('voucher') && regData.voucher.hasOwnProperty('errors')) {            
            var errorText = '<ul>';
            for (const [key, error] of Object.entries(regData.voucher.errors)) {
                errorText += '<li>' + error.message + '</li>';
            }
            errorText += '</ul>';
            addAlert(errorText);
            
            regData.voucherId = '';
        }
    }

    function submitData(redirect=false, removeAlerts=false){

        // The Ajax view should only return a redirect URL if we are moving forward.;
        if (redirect) {
            regData['finalize'] = true;
        }

        $.ajax({
            url: regParams.registerUrl,
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify(regData),
            success: function(response){

                if(response.status == "success" && response.redirect && redirect == true) {
                    window.location.href = response.redirect;
                }
                else if(response.status == "success") {
                    regData = response.reg;

                    if (removeAlerts == true) {
                        // Remove any existing alerts.
                        $('.alert').alert('close')
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

                    // reset regData for expired registrations
                    if (response.errors.filter(function(e){return e.code == 'expired'}).length > 0) {
                        initializeRegData();
                        refreshCart();
                    }
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

        // Before proceeding, validate to ensure that there is not already an
        // item in the cart for this event.
        var this_data = $(this).data();
        var this_key = this_data['event'];
        existing_data = regData['events'][this_key];

        if (existing_data) {
            addAlert(regParams.multipleRegisterString);
            return;
        }

        // Events can also be set to apply vouchers at the same time.
        if (this_data['voucherId']) {
            // If an existing voucher code exists, then we can't add a new one without removing the old one.
            if (
                regData.hasOwnProperty('voucherId') &&
                regData['voucherId'] !== '' &&
                regData['voucherId'] !== this_data['voucherId']
            ) {
                addAlert(regParams.multipleVoucherString);
                return;
            }

            regData['voucherId'] = this_data['voucherId'];
            delete this_data['voucherId'];
        }

        // The student attribute actually applies to the registration, not to
        // one particular item, so move this to the correct place in regData
        if (this_data['student']) {
            regData['student'] = this_data['student'];
            delete this_data['student'];
        }

        // Avoid passing anything but integer values for role ID, which will happen
        // when registration buttons have no associated role.
        if (isNaN(parseInt(this_data['roleId']))) {
            delete this_data['roleId'];
        }

        // Add the data from the button to the regData and submit
        regData['events'][this_key] = this_data;

        submitData(redirect=false, removeAlerts=true);

    });

    // Hide and Show Cart Items
    $('.openCloseCart').click(function(){
        $('#shoppingCart').toggle();
    });

    // Empty Cart
    $('#emptyCart').click(function() {
        initializeRegData();
        submitData(redirect=false, removeAlerts=true);
    });

    // Remove Item From Cart
    $('#shoppingCart').on('click', '.remove-item', function(){
        var this_event_id = $($(this).closest('tr')).data('event');
        delete regData['events'][this_event_id];
        submitData(redirect=false);
    });

    // Submit registration
    $('.submit-button').click(function(e) {
        e.preventDefault();
        submitData(redirect=true);
    });

    // Add voucher code
    $('.add-voucher').click(function () {

        var this_code = $(this).data('id');
        if (!this_code) {
            this_code = $(this).closest('.voucherDetail').find('input').val();
        }

        // If an existing voucher code exists, then we can't add a new one without removing the old one.
        if (
            this_code !== '' && regData.hasOwnProperty('voucherId') &&
            regData['voucherId'] !== '' && regData['voucherId'] !== this_code
        ) {
            addAlert(regParams.multipleVoucherString);
            return;
        }

        regData['voucherId'] = this_code;

        if ($.isEmptyObject(regData['events'])) {
            addAlert(regParams.emptyRegisterVoucherString, alertClass='alert-info');
        }
        else {
            submitData(redirect=false);
        }
    });

    // Remove voucher code
    $('#shoppingCart').on('click', '.remove-voucher', function(){
        delete regData['voucherId'];
        delete regData['voucher'];        
        submitData(redirect=false);
    });

    // Lookup customer
    $('#id_name').change(function() {

        var this_data = $($(this).find(':selected').text()).data();

        if (this_data['type'] == regParams.customerString) {
            var ajaxData = {
                id: this_data['id'],
                guestType: this_data['type'],
                date: regParams.registerDate,
            };

            $('#guestInfoTable tbody tr td').empty();
            $('#guestInfoTable').addClass('d-none');
            $('#customerInfoTable tbody').empty();
            $('#customerInfoCard').removeClass('collapse');
            $('#customerInfoCard').addClass('show');

            $.ajax({
                url: regParams.guestLookupUrl,
                type: "GET",
                data: ajaxData,
                success: function(response){
    
                    $('#customerInfoTable').removeClass('d-none');

                    $.each(response, function() {
                        $('#customerInfoExample tr').clone().appendTo($('#customerInfoTable tbody'));
                        var this_row = $('#customerInfoTable tbody tr:last');

                        var statusString = this.registration.invoice.statusLabel;
                        if (this.registration.invoice.outstandingBalance > 0) {
                            statusString += ' (' + regParams.outstandingBalanceString + ' ' + regParams.currencySymbol + parseFloat(this.registration.invoice.outstandingBalance).toFixed(2) + ')';
                        }

                        this_row.find('.customerCheckIn').attr('checked', this.checkedIn);
                        this_row.find('.customerCheckIn').attr('value', this.registration.id);
                        this_row.find('.customerCheckIn').data('event-id', this.event.id);
                        this_row.find('.customerInfoEvent').text(this.event.name);
                        var role_text = "";
                        if (this.dropIn == true) {
                            role_text += regParams.dropInString + ' ';
                        }
                        if (this.role.name) {
                            role_text += this.role.name;
                        }
                        this_row.find('.customerInfoRole').text(role_text);
                        this_row.find('.customerInfoStudent').text(this.registration.student);
                        this_row.find('.customerInfoPaymentStatus').text(statusString);
                        this_row.find('.customerInvoiceLink').attr('href',this.registration.invoice.url);
                        this_row.find('.customerRegistrationLink').attr('href',this.registration.url);
                    });
    
                },
            });
        }
        else if (this_data['type']) {
            $('#customerInfoTable tbody').empty();
            $('#customerInfoTable').addClass('d-none');
            $('#customerInfoCard').removeClass('collapse');
            $('#customerInfoCard').addClass('show');
            $('#guestInfoTable tbody tr td').text($('#id_name').val());
            $('#guestInfoTable').removeClass('d-none');
        }
        else {
            $('#guestInfoTable tbody tr td').empty();
            $('#guestInfoTable').addClass('d-none');
            $('#customerInfoTable tbody').empty();
            $('#customerInfoTable').addClass('d-none');
        }
    });

    // Check-in customer.
    $(document).on("click", ".customerCheckIn", function() {

        $(this).attr("disabled", true);

        var postData = [
            {name: "event_id", value: $(this).data('eventId')},
            {name: "reg_id", value: $(this).attr("value")},
        ];

	    $.ajax(
	    {
	        url : regParams.checkInUrl,
	        type: "POST",
	        data : postData,
	        success:function(data, textStatus, jqXHR)
	        {
                setTimeout(function() {
                    $(".customerCheckIn").removeAttr("disabled");
                }, 1000);
	        },
	        error: function(jqXHR, textStatus, errorThrown)
	        {
                console.log('Update failure!')
                setTimeout(function() {
                    $(".customerCheckIn").removeAttr("disabled");
                }, 1000);
            }
	    });


    });

});
