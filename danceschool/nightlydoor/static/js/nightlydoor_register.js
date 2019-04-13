var $ = django.jQuery;

$(document).ready(function() {

    // This object contains the information for which the individual should register.
    var regData = {'json': true}
    var itemCount = 0;
    var priceTotal = 0;

    function submitData(){

        for (var property in regData) {
            if (regData.hasOwnProperty(property)) {
                if (regData[property].hasOwnProperty('field')) {
                    regData[property] = JSON.stringify(regData[property]['field']);
                }
                else {
                    delete regData[property]['id'];
                    delete regData[property]['name'];
                    delete regData[property]['price'];    
                }
            }
        }

        $.ajax({
            url: registerUrl,
            type: "POST",
            data: regData,
            success: function(response){
                console.log(response);

                if(response.status == "success" && response.redirect) {
                    window.location.href = response.redirect;
                }
                else {
                    var errorText = '<ul>';
                    for (const [key, error] of Object.entries(response.errors)) {
                        errorText += '<li>' + error + '</li>';
                    }
                    errorText += '</ul>';
                    addAlert(errorText);
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

    function addAlert(message) {
        $('#alert-box').append(
            '<div class="alert alert-danger my-1 alert-dismissible fade show" role="alert">' +
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
    $('.add').click(function (){

        // Before proceeding, validate to ensure that
        var this_data = $(this).data();
        var this_key = 'event_' + this_data['id'];
        existing_data = regData[this_key];

        if (existing_data) {
            addAlert(multipleRegisterString);
            return;
        }

        // Since no errors were found, proceed.
        itemCount ++;
        $('#itemCount').text(itemCount).css('display', 'block');
        $('#cart-submit').removeClass('invisible');

        var this_name = this_data['name'] + ': ' + this_data['roleName'];
        var this_price = parseFloat(this_data['price']);

        // Add the data from the button to the regData
        regData['event_' + this_data['id']] = this_data;
        $('#cartItems').append(
            '<tr data-id="' + this_data['id'] + '"><td>' +
                this_name +
            '</td><td>' + 
                currencySymbol + this_price +
            '<button type="button" class="close removeItem" aria-label="Close"><span aria-hidden="true">&times;</span></button></td></tr>'
        );

        // Calculate Total Price
        priceTotal += this_price;
        $('#cartTotal').text(priceTotal);

        // Remove any existing alerts.
        $('.alert').alert('close')
    }); 

    // Hide and Show Cart Items
    $('.openCloseCart').click(function(){
        $('#shoppingCart').toggle();
    });

    // Empty Cart
    $('#emptyCart').click(function() {
        itemCount = 0;
        priceTotal = 0;
        regData = {};

        // Clear everything and remove any existing alerts
        $('#itemCount').css('display', 'none');
        $('#cartItems').text('');
        $('#cartTotal').text(priceTotal);
        $('#cart-submit').addClass('invisible');
        $('.alert').alert('close');
    }); 

    // Remove Item From Cart
    $('#shoppingCart').on('click', '.removeItem', function(){

        var this_item_id = $(this).closest('tr').attr('data-id');
        var this_data = regData['event_' + this_item_id];
        delete regData['event_' + this_item_id];

        $(this).closest('tr').remove();
        itemCount --;
        $('#itemCount').text(itemCount);

        // Remove Cost of Deleted Item from Total Price
        priceTotal -= parseFloat(this_data['price']);
        $('#cartTotal').text(priceTotal);
        
        if (itemCount == 0) {
            $('#itemCount').css('display', 'none');
            $('#cart-submit').addClass('invisible');
        }

        // Remove any existing alerts.
        $('.alert').alert('close')
    });

    // Submit registration
    $('.submit-button').click(function(e) {
        e.preventDefault();
        submitData();
    });

});