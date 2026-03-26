document.addEventListener('DOMContentLoaded', function () {

    // WeakMap replaces jQuery's .data() for per-element oldValue storage.
    var oldValues = new WeakMap();

    function handle_button(button, clicked) {
        if (clicked === undefined) { clicked = true; }

        var fieldName  = button.dataset.field;
        var type       = button.dataset.type;
        var input      = document.querySelector("input[name='" + fieldName + "']");
        if (!input) { return; }

        // Treat a missing or empty max attribute as no upper bound.
        var minVal = parseInt(input.min, 10);
        var maxVal = input.max !== '' ? parseInt(input.max, 10) : Infinity;

        var currentVal = parseInt(input.value, 10);
        if (!isNaN(currentVal)) {
            if (type === 'minus') {
                if (currentVal > minVal && clicked) {
                    input.value = currentVal - 1;
                    input.dispatchEvent(new Event('change'));
                }
                button.disabled = parseInt(input.value, 10) <= minVal;
            } else if (type === 'plus') {
                if (currentVal < maxVal && clicked) {
                    input.value = currentVal + 1;
                    input.dispatchEvent(new Event('change'));
                }
                button.disabled = isFinite(maxVal) && parseInt(input.value, 10) >= maxVal;
            }
        } else {
            input.value = 0;
        }
    }

    function initButtons() {
        document.querySelectorAll('.btn-number').forEach(function (btn) {
            handle_button(btn, false);
        });
    }

    // On initial load, ensure that the disabled status of each button is correct.
    initButtons();

    // Re-run after full page load to catch values restored by the browser
    // (autocomplete, session history, etc.) which fire after DOMContentLoaded.
    window.addEventListener('load', initButtons);

    // Expose a hook so external code (e.g. cart initialization) can call
    // initButtons() after programmatically setting input values.
    window.registerInputs = { initButtons: initButtons };

    document.querySelectorAll('.btn-number').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            handle_button(btn, true);
        });
    });

    document.querySelectorAll('.input-number').forEach(function (input) {
        input.addEventListener('focusin', function () {
            oldValues.set(this, this.value);
        });

        input.addEventListener('change', function () {
            var minValue     = parseInt(this.min, 10);
            var maxValue     = this.max !== '' ? parseInt(this.max, 10) : Infinity;
            var valueCurrent = parseInt(this.value, 10);
            var name         = this.name;
            var minusBtn = document.querySelector(".btn-number[data-type='minus'][data-field='" + name + "']");
            var plusBtn  = document.querySelector(".btn-number[data-type='plus'][data-field='" + name + "']");

            if (isNaN(valueCurrent) || valueCurrent < minValue) {
                alert('Sorry, the minimum value was reached');
                this.value = oldValues.get(this) || 0;
                valueCurrent = parseInt(this.value, 10);
            } else if (isFinite(maxValue) && valueCurrent > maxValue) {
                alert('Sorry, the maximum value was reached');
                this.value = oldValues.get(this) || 0;
                valueCurrent = parseInt(this.value, 10);
            }

            if (minusBtn) { minusBtn.disabled = valueCurrent <= minValue; }
            if (plusBtn)  { plusBtn.disabled  = isFinite(maxValue) && valueCurrent >= maxValue; }
        });

        input.addEventListener('keydown', function (e) {
            // Allow: backspace, delete, tab, escape, enter, decimal point
            if ([46, 8, 9, 27, 13, 190].includes(e.keyCode) ||
                // Allow: Ctrl+A
                (e.keyCode === 65 && e.ctrlKey === true) ||
                // Allow: home, end, left, right
                (e.keyCode >= 35 && e.keyCode <= 39)) {
                return;
            }
            // Ensure that it is a number and stop the keypress
            if ((e.shiftKey || (e.keyCode < 48 || e.keyCode > 57)) &&
                (e.keyCode < 96 || e.keyCode > 105)) {
                e.preventDefault();
            }
        });
    });
});
  