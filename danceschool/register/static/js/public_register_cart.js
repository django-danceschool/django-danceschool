/**
 * public_register_cart.js
 *
 * Public registration page extension for register_cart_common.js.
 * Requires register_cart_common.js to be loaded first.
 *
 * Behaviour
 * ---------
 * • Every time a .register-quantity input changes (whether by clicking +/−
 *   or by direct keyboard entry), the cart is immediately POSTed to CartView
 *   and the collapsible cart display is refreshed.
 * • Items that have no matching input on this page (e.g. items from a
 *   different plugin, or merch) are silently preserved in every sync.
 * • The "Your Cart" toggle button is hidden until the cart contains at least
 *   one item, then shown automatically.
 * • regParams.preSubmit is kept as a lightweight fallback: if the user somehow
 *   reaches the checkout button before any change event has fired (e.g. the
 *   page was pre-populated and they click straight through), cart.items is
 *   returned as-is; if that is also empty, inputs are scanned as a last resort.
 *
 * Key format used to match inputs ↔ cart items
 * --------------------------------------------
 *   regular:  sku                       e.g. EVENT_42_ROLE_1
 *   drop-in:  sku + ':' + occurrenceId  e.g. EVENT_42_GENERAL:1212
 */

(function () {

    // ── Key helpers ─────────────────────────────────────────────────────────

    function inputKey(input) {
        var eventId  = input.dataset.eventId;
        var roleId   = input.dataset.roleId || null;
        var isDropIn = input.dataset.dropIn === 'true';
        var occId    = input.dataset.occurrenceId || null;
        var sku = (roleId && !isNaN(parseInt(roleId, 10)))
            ? 'EVENT_' + eventId + '_ROLE_' + roleId
            : 'EVENT_' + eventId + '_GENERAL';
        return isDropIn ? sku + ':' + occId : sku;
    }

    function cartItemKey(item) {
        return item.dropIn ? item.sku + ':' + item.dropInOccurrence : item.sku;
    }

    // ── Description helpers ──────────────────────────────────────────────────
    // Build a human-readable cart label from the input's surrounding DOM.
    //
    // For a regular role slot:  "Event Name"  (or "Event Name: Role" if the
    //   label text adds something beyond just the event name)
    // For a drop-in slot:       "Event Name: Drop-in Mar. 5"

    function getInputDescription(input) {
        var isDropIn = input.dataset.dropIn === 'true';

        // Event name from the nearest .reg-event-title inside the same card.
        var card = input.closest('.reg-event');
        var titleEl = card ? card.querySelector('.reg-event-title') : null;
        var eventName = titleEl ? titleEl.textContent.trim() : '';

        if (!isDropIn) {
            // For role slots, append the role name from the associated label.
            // The label renders as "Leader (6)" — strip the trailing count.
            var roleId = input.dataset.roleId || null;
            if (roleId && !isNaN(parseInt(roleId, 10))) {
                var roleLabelEl = input.id
                    ? document.querySelector("label[for='" + input.id + "']")
                    : null;
                var roleLabelText = roleLabelEl ? roleLabelEl.textContent.trim() : '';
                // Remove trailing " (N)" registration count.
                var roleName = roleLabelText.replace(/\s*\(\d+\)\s*$/, '').trim();
                if (eventName && roleName) {
                    return eventName + ': ' + roleName;
                }
            }
            return eventName || null;
        }

        // For drop-ins, read the date from the <label for="…"> associated with
        // this input.  The template renders it as "Drop-in: Mar. 5".
        var labelEl = input.id
            ? document.querySelector("label[for='" + input.id + "']")
            : null;
        var labelText = labelEl ? labelEl.textContent.trim() : '';

        // Strip the leading "Drop-in: " prefix (translated or not) and keep
        // only the date portion, so we can reassemble it ourselves.
        var dateMatch = labelText.match(/:\s*(.+)$/);
        var datePart  = dateMatch ? dateMatch[1].trim() : labelText;

        if (eventName && datePart) {
            return eventName + ': Drop-in ' + datePart;
        }
        return eventName || labelText || null;
    }

    // Build a map from inputKey → description for all inputs on the page.
    function buildDescriptionMap() {
        var map = {};
        document.querySelectorAll('input.register-quantity').forEach(function (input) {
            var desc = getInputDescription(input);
            if (desc) { map[inputKey(input)] = desc; }
        });
        return map;
    }

    // ── Item collection ──────────────────────────────────────────────────────
    // Builds the full item list for a syncCart call: non-zero inputs on this
    // page plus any cart items that have no matching input here.

    function collectInputItems(currentCart) {
        var buildEventItem = window.registerCart.buildEventItem;
        var descMap = buildDescriptionMap();

        var visibleKeys = new Set();
        document.querySelectorAll('input.register-quantity').forEach(function (input) {
            visibleKeys.add(inputKey(input));
        });

        var inputItems = [];
        document.querySelectorAll('input.register-quantity').forEach(function (input) {
            var qty = parseInt(input.value, 10) || 0;
            if (qty <= 0) { return; }

            var eventId      = input.dataset.eventId;
            var roleId       = input.dataset.roleId || null;
            var price        = input.dataset.price ? parseFloat(input.dataset.price) : null;
            var isDropIn     = input.dataset.dropIn === 'true';
            var occurrenceId = input.dataset.occurrenceId || null;
            var key          = inputKey(input);

            inputItems.push(buildEventItem(eventId, roleId, qty, price, {
                dropIn:           isDropIn,
                dropInOccurrence: isDropIn ? occurrenceId : null,
                description:      descMap[key] || null,
            }));
        });

        var hiddenItems = (currentCart.items || []).filter(function (item) {
            return !visibleKeys.has(cartItemKey(item));
        });

        return inputItems.concat(hiddenItems);
    }

    // ── Cart toggle visibility ───────────────────────────────────────────────

    function updateCartToggle(hasItems) {
        var toggle = document.getElementById('cart-toggle-container');
        if (!toggle) { return; }
        if (hasItems) {
            toggle.style.removeProperty('display');
            toggle.classList.remove('d-none');
        } else {
            toggle.style.setProperty('display', 'none', 'important');
        }
    }

    // ── Immediate sync on input change ───────────────────────────────────────
    // Handles both +/− button clicks (which dispatch a bubbling synthetic
    // change event via registration_number_input.js) and direct keyboard entry.

    document.addEventListener('change', function (e) {
        if (!e.target.matches('input.register-quantity')) { return; }
        var rc = window.registerCart;
        if (!rc) { return; }

        var items = collectInputItems(rc.cart);
        if (items.length === 0) {
            rc.cart.discount_code = '';
            rc.cart.voucher_preview = null;
            rc.cart.student = false;
        }
        rc.syncCart(items);
    });

    // ── Post-refresh hook ────────────────────────────────────────────────────
    // Called by refreshCart() in register_cart_common.js after every cart
    // update.  Keeps inputs in sync with the server-confirmed cart state,
    // refreshes +/− button enabled/disabled states, shows/hides the toggle,
    // and ensures cart items carry DOM-sourced descriptions so the cart
    // display shows readable labels rather than raw SKUs.

    regParams.onCartRefresh = function (cart) {
        var cartMap = {};
        var descMap = buildDescriptionMap();

        (cart.items || []).forEach(function (item) {
            var key = cartItemKey(item);
            cartMap[key] = item.quantity || 1;
            // Enrich with a DOM-sourced description if the item doesn't already
            // carry one (e.g. items loaded from the server on page load).
            if (!item.description && descMap[key]) {
                item.description = descMap[key];
            }
        });

        document.querySelectorAll('input.register-quantity').forEach(function (input) {
            input.value = cartMap[inputKey(input)] || 0;
        });

        // Re-evaluate +/− enabled state after values change programmatically.
        if (window.registerInputs && window.registerInputs.initButtons) {
            window.registerInputs.initButtons();
        }

        updateCartToggle(cart.items && cart.items.length > 0);
    };

    // ── Checkout preSubmit ───────────────────────────────────────────────────
    // By the time the user clicks "Register Now", cart.items is already current
    // thanks to the change listener above.  We return it directly.
    // collectInputItems is used only as a last-resort fallback (e.g. the user
    // pre-populated the page and hit submit without triggering any change event).

    regParams.preSubmit = function (currentCart) {
        if (currentCart.items && currentCart.items.length > 0) {
            return currentCart.items;
        }
        return collectInputItems(currentCart);
    };

}());
