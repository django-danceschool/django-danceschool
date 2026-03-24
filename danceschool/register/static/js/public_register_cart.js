/**
 * public_register_cart.js
 *
 * Public registration page extension for register_cart_common.js.
 * Requires register_cart_common.js to be loaded first.
 *
 * Sets regParams.preSubmit so that clicking "Register Now" collects the
 * current values of all .register-quantity number inputs and submits them
 * as a fresh cart rather than relying on an incrementally maintained cart
 * state.  register_cart_common.js calls regParams.preSubmit(cart) in its
 * submit handler if this function is defined.
 *
 * SKU format mirrors translateButtonData() in manage_register_cart.js:
 *   EVENT_<eventId>_ROLE_<roleId>   (when a role is specified)
 *   EVENT_<eventId>_GENERAL         (when no role is specified)
 *
 * The choice data JSONField is intentionally kept server-side and is never
 * included in the item payload; it will be attached to the EventRegistration
 * by a signal handler.
 */

regParams.preSubmit = function (currentCart) {
    var buildEventItem = window.registerCart.buildEventItem;
    var items = [];

    document.querySelectorAll('input.register-quantity').forEach(function (input) {
        var qty = parseInt(input.value, 10) || 0;
        if (qty <= 0) { return; }

        var eventId     = input.dataset.eventId;
        var roleId      = input.dataset.roleId || null;
        var price       = input.dataset.price ? parseFloat(input.dataset.price) : null;
        var isDropIn    = input.dataset.dropIn === 'true';
        var occurrenceId = input.dataset.occurrenceId || null;

        items.push(buildEventItem(eventId, roleId, qty, price, {
            dropIn:           isDropIn,
            dropInOccurrence: isDropIn ? occurrenceId : null,
        }));
    });

    // Fall back to the existing session cart if no inputs were filled in
    // (e.g. the user clicked "Register Now" to check out a cart from a
    // previous visit without changing any quantities).
    return items.length > 0 ? items : currentCart.items;
};
