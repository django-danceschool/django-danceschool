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
                if(response.status == "success" && response.redirect) {
                    window.location.href = response.redirect;
                }
                else {
                    window.location.href = registerUrl;
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
        itemCount ++;

        $('#itemCount').text(itemCount).css('display', 'block');

        var this_data = $(this).data();
        var this_name = this_data['name'];
        var this_price = this_data['price'];

        // Add the data from the button to the regData
        regData['event_' + this_data['id']] = this_data;
        $('#cartItems').append(
            '<tr data-id="' + this_data['id'] + '"><td>' +
                this_name +
            '</td><td>' + 
                currencySymbol + this_price +
            '</td><td><button class="btn btn-outline-secondary removeItem">' + 
                removeText + 
            '</button></td></tr>'
        );

        // Calculate Total Price
        priceTotal += this_price;
        $('#cartTotal').text(totalString + ": " + currencySymbol + priceTotal);
    }); 

    // Hide and Show Cart Items
    $('.openCloseCart').click(function(){
        $('#shoppingCart').toggle();
    });

    // Empty Cart
    $('#emptyCart').click(function() {
        itemCount = 0;
        priceTotal = 0;

        $('#itemCount').css('display', 'none');
        $('#cartItems').text('');
        $('#cartTotal').text(totalString + ": " + currencySymbol + priceTotal);
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
        priceTotal -= this_data['price'];
        $('#cartTotal').text(totalString + ": " + currencySymbol + priceTotal);

        if (itemCount == 0) {
            $('#itemCount').css('display', 'none');
        }
    });

    // Submit registration
    $('.submit-button').click(function(e) {
        e.preventDefault();
        submitData();
    });

});