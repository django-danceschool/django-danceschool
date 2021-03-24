document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

    function handle_button(button, clicked=true) {

        fieldName = $(button).attr('data-field');
        type      = $(button).attr('data-type');
        var input = $("input[name='"+fieldName+"']");
        var currentVal = parseInt(input.val());
        if (!isNaN(currentVal)) {
            if(type == 'minus') {
                
                if(currentVal > input.attr('min') & clicked === true) {
                    input.val(currentVal - 1).change();
                }                 
                $(button).attr('disabled', (parseInt(input.val()) == input.attr('min')));

            } else if(type == 'plus') {
    
                if(currentVal < input.attr('max') & clicked === true) {
                    input.val(currentVal + 1).change();
                }
                $(button).attr('disabled', (parseInt(input.val()) == input.attr('max')));

            }
        } else {
            input.val(0);
        }
    }

    // On initial load, ensure that the disabled status of each button is
    // correct.
    $.each($('.btn-number'), function() {
        handle_button($(this), clicked=false);
    });

    $('.btn-number').click(function(e){
        e.preventDefault();
        handle_button($(this), clicked=true);
    });

    $('.input-number').focusin(function(){
       $(this).data('oldValue', $(this).val());
    });

    $('.input-number').change(function() {
        
        minValue =  parseInt($(this).attr('min'));
        maxValue =  parseInt($(this).attr('max'));
        valueCurrent = parseInt($(this).val());
        
        this_name = $(this).attr('name');
        if(valueCurrent >= minValue) {
            $(".btn-number[data-type='minus'][data-field='"+this_name+"']").removeAttr('disabled')
        } else {
            alert('Sorry, the minimum value was reached');
            $(this).val($(this).data('oldValue'));
        }
        if(valueCurrent <= maxValue) {
            $(".btn-number[data-type='plus'][data-field='"+this_name+"']").removeAttr('disabled')
        } else {
            alert('Sorry, the maximum value was reached');
            $(this).val($(this).data('oldValue'));
        }
    });
    
    $(".input-number").keydown(function (e) {
        // Allow: backspace, delete, tab, escape, enter and .
        if ($.inArray(e.keyCode, [46, 8, 9, 27, 13, 190]) !== -1 ||
             // Allow: Ctrl+A
            (e.keyCode == 65 && e.ctrlKey === true) || 
             // Allow: home, end, left, right
            (e.keyCode >= 35 && e.keyCode <= 39)) {
                 // let it happen, don't do anything
                 return;
        }
        // Ensure that it is a number and stop the keypress
        if ((e.shiftKey || (e.keyCode < 48 || e.keyCode > 57)) && (e.keyCode < 96 || e.keyCode > 105)) {
            e.preventDefault();
        }
    });
});
  