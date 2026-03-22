/**
 * register_cart_common.js
 *
 * Shared shopping-cart logic for both the at-the-door and public registration
 * pages.  Handles catalog loading, cart state, display, API communication,
 * and the basic handlers (empty cart, remove item, submit with preSubmit hook).
 *
 * At the end of DOMContentLoaded this file exposes window.registerCart so
 * that extension scripts loaded after it can access shared state and helpers:
 *
 *   window.registerCart = {
 *     cart, syncCart, refreshCart, addAlert, clearAlerts, displayErrors,
 *     jsonFetch, csrfToken, fmt, toTitleCase, htmlToNodes
 *   }
 *
 * Extended by:
 *   manage_register_cart.js  – at-the-door register (add-item, voucher,
 *                               customer lookup, check-in)
 *   public_register_cart.js  – public register (preSubmit from number inputs)
 */
document.addEventListener('DOMContentLoaded', function () {

    // ===== Utilities =====

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return decodeURIComponent(parts.pop().split(';').shift());
        }
        return null;
    }

    const csrfToken = getCookie('csrftoken');

    function jsonFetch(url, options) {
        const merged = Object.assign({
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        }, options || {});
        return fetch(url, merged);
    }

    function fmt(amount) {
        return parseFloat(amount || 0).toFixed(2);
    }

    function toTitleCase(str) {
        return String(str).replace(/\w\S*/g, function (txt) {
            return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
        });
    }

    function htmlToNodes(html) {
        const t = document.createElement('template');
        t.innerHTML = html;
        return Array.from(t.content.childNodes);
    }

    // ===== Alerts =====

    function addAlert(message, alertClass) {
        const box = document.getElementById('alert-box');
        if (!box) { return; }
        const div = document.createElement('div');
        div.className = 'alert ' + (alertClass || 'alert-danger') + ' my-1 alert-dismissible fade show';
        div.setAttribute('role', 'alert');
        div.innerHTML =
            '<button type="button" class="close" data-dismiss="alert" aria-label="Close">' +
            '<span aria-hidden="true">&times;</span></button>' +
            '<span class="register-alert-text">' + message + '</span>';
        box.appendChild(div);
    }

    function clearAlerts() {
        const box = document.getElementById('alert-box');
        if (box) { box.innerHTML = ''; }
    }

    function displayErrors(errors) {
        let html = '<ul>';
        if (Array.isArray(errors)) {
            errors.forEach(function (e) {
                html += '<li>' + (e.message || e) + '</li>';
            });
        } else if (errors && typeof errors === 'object') {
            Object.values(errors).forEach(function (msgs) {
                const list = Array.isArray(msgs) ? msgs : [msgs];
                list.forEach(function (m) { html += '<li>' + (m.message || m) + '</li>'; });
            });
        } else {
            html += '<li>' + errors + '</li>';
        }
        html += '</ul>';
        addAlert(html);
    }

    // ===== Catalog =====
    // Maps SKU -> {item_id, item_type, sku, description, price}
    let catalog = {};

    function serializerTypeToCartType(serializerType) {
        // PurchasableItemsView sets item_type to the serializer class name;
        // CartView expects the bare model name.
        if (serializerType === 'EventSerializer') { return 'Event'; }
        if (serializerType === 'MerchItemSerializer') { return 'MerchItem'; }
        return serializerType;
    }

    function buildCatalog(results) {
        catalog = {};
        (results || []).forEach(function (item) {
            const cartItemType = serializerTypeToCartType(item.item_type);
            (item.variants || []).forEach(function (variant) {
                // Prefer the variant description; fall back to item name.
                const description = (
                    variant.description &&
                    variant.description !== 'General Admission'
                ) ? item.name + ': ' + variant.description : item.name;

                catalog[variant.sku] = {
                    item_id: item.id,
                    item_type: cartItemType,
                    sku: variant.sku,
                    description: description,
                    price: parseFloat(variant.price || 0),
                    dropIn: variant.dropIn || false,
                };
            });
        });
    }

    function lookupPrice(sku) {
        return catalog[sku] ? catalog[sku].price : 0;
    }

    function lookupDescription(sku, fallback) {
        return catalog[sku] ? catalog[sku].description : (fallback || sku);
    }

    // ===== Local cart state =====
    // Mirrors what the server stores in the session.
    let cart = {
        items: [],
        discount_code: '',
        student: false,
        payAtDoor: regParams.payAtDoor,
        discount_preview: null,
        voucher_preview: null,
    };

    // ===== Cart display =====

    function refreshCart() {
        const ids = [
            'cartItems', 'subtotalLine', 'discountList', 'preTaxVoucherList',
            'addonList', 'taxInfo', 'postTaxVoucherList',
        ];
        ids.forEach(function (id) {
            const el = document.getElementById(id);
            if (el) { el.innerHTML = ''; }
        });
        document.querySelectorAll('.badge-choice-counter').forEach(function (b) {
            b.textContent = '';
        });

        const submitBtn = document.getElementById('cart-submit');
        const cartSummary = document.getElementById('cartSummary');

        if (submitBtn) { submitBtn.classList.add('invisible'); }
        if (cartSummary) { cartSummary.style.display = 'none'; }

        const totalEl = document.getElementById('cartTotal');

        if (!cart.items || cart.items.length === 0) {
            if (totalEl) { totalEl.textContent = fmt(0); }
            return;
        }

        let grossTotal = 0;
        const tbody = document.getElementById('cartItems');

        cart.items.forEach(function (item) {
            // Prefer catalog price (ensures consistency with the API), but
            // fall back to the price cached from the button's data-price
            // attribute when the catalog SKU doesn't match (e.g. DanceRole ID
            // vs EventRole ID difference between register page and catalog API).
            const price = lookupPrice(item.sku) || item.price || 0;
            const qty = item.quantity || 1;
            const lineTotal = price * qty;
            grossTotal += lineTotal;

            const tr = document.createElement('tr');
            tr.dataset.sku = item.sku;
            if (item.choiceId) { tr.dataset.choiceId = item.choiceId; }

            tr.innerHTML =
                '<td>' + lookupDescription(item.sku, item.description) + '</td>' +
                '<td>' + regParams.currencySymbol + fmt(lineTotal) +
                '<button type="button" class="close remove-item" aria-label="Remove"' +
                ' data-sku="' + item.sku + '">' +
                '<span aria-hidden="true">&times;</span></button></td>';

            if (tbody) { tbody.appendChild(tr); }

            // Update the badge on the source button (door register only).
            if (item.choiceId) {
                const badge = document.querySelector('#' + item.choiceId + ' .badge-choice-counter');
                if (badge) { badge.textContent = qty; }
            }
        });

        // Discount preview rows.
        const preview = cart.discount_preview;
        let displayTotal = grossTotal;
        const discountList = document.getElementById('discountList');
        if (discountList) {
            if (preview && preview.total_discount > 0) {
                preview.discounts.forEach(function (d) {
                    const tr = document.createElement('tr');
                    tr.className = 'discount-row text-success';
                    tr.innerHTML =
                        '<td>' + d.name + '</td>' +
                        '<td>-' + regParams.currencySymbol + fmt(d.discount_amount) + '</td>';
                    discountList.appendChild(tr);
                });
                displayTotal = preview.discounted_total;
            }
        }

        // Voucher preview rows.
        const voucherPreview = cart.voucher_preview;
        const preTaxVoucherList = document.getElementById('preTaxVoucherList');
        const postTaxVoucherList = document.getElementById('postTaxVoucherList');
        if (voucherPreview) {
            if (voucherPreview.error) {
                addAlert(voucherPreview.error);
                cart.discount_code = '';
                cart.voucher_preview = null;
            } else {
                const targetList = voucherPreview.before_tax ? preTaxVoucherList : postTaxVoucherList;
                if (targetList) {
                    const tr = document.createElement('tr');
                    tr.className = 'voucher-row text-success';
                    const label = (regParams.voucherString || 'Voucher') +
                        (voucherPreview.voucher_name ? ': ' + voucherPreview.voucher_name : '');
                    tr.innerHTML =
                        '<td>' + label + '</td>' +
                        '<td>-' + regParams.currencySymbol + fmt(voucherPreview.voucher_amount) +
                        '<button type="button" class="close remove-voucher" aria-label="Remove">' +
                        '<span aria-hidden="true">&times;</span></button></td>';
                    targetList.appendChild(tr);
                }
                if (voucherPreview.before_tax) {
                    displayTotal = Math.max(0, displayTotal - voucherPreview.voucher_amount);
                }
            }
        }

        if (totalEl) { totalEl.textContent = fmt(displayTotal); }

        const itemCount = cart.items.length;
        const itemString = itemCount === 1 ? regParams.itemString : regParams.itemStringPlural;
        if (cartSummary) {
            cartSummary.textContent = itemCount + ' ' + itemString + ': ' +
                regParams.currencySymbol + fmt(displayTotal);
            cartSummary.style.display = 'block';
        }

        if (submitBtn) { submitBtn.classList.remove('invisible'); }
    }

    // ===== CartView API =====

    function buildPayload(items, extra) {
        const payload = Object.assign({
            payAtDoor: cart.payAtDoor,
            items: items,
            student: cart.student,
        }, extra || {});
        if (cart.discount_code) {
            payload.discount_code = cart.discount_code;
        }
        return payload;
    }

    function syncCart(items, extra) {
        // POST updated items to CartView and refresh display.
        clearAlerts();
        jsonFetch(regParams.cartUrl, {
            method: 'POST',
            body: JSON.stringify(buildPayload(items, extra)),
        })
        .then(function (response) {
            if (!response.ok) {
                return response.json().then(function (data) {
                    return Promise.reject(data);
                });
            }
            return response.json();
        })
        .then(function (data) {
            // Preserve UI-only fields (choiceId, price) that the server never
            // stores.  Use the items we SENT (the `items` parameter, which
            // is already the updated list) as the source — not cart.items,
            // which still holds the pre-send state.
            cart.items = (data.items || []).map(function (serverItem) {
                const sent = items.find(function (o) { return o.sku === serverItem.sku; });
                return Object.assign({}, serverItem, {
                    choiceId: sent ? sent.choiceId : null,
                    price: sent ? sent.price : null,
                    description: sent ? sent.description : null,
                });
            });
            cart.student = data.student || false;
            cart.discount_preview = data.discount_preview || null;
            cart.voucher_preview = data.voucher_preview || null;
            refreshCart();
        })
        .catch(function (errors) {
            displayErrors(errors);
            refreshCart();
        });
    }

    // ===== Initialization =====

    jsonFetch(regParams.purchasableItemsUrl + '?payAtDoor=' + regParams.payAtDoor)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            buildCatalog(data.results || []);
            // Load current session cart.
            return jsonFetch(regParams.cartUrl);
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.items) {
                cart.items = data.items;
                if (data.payAtDoor !== undefined) { cart.payAtDoor = data.payAtDoor; }
                if (data.student !== undefined) { cart.student = data.student; }
                if (data.discount_code) { cart.discount_code = data.discount_code; }
                if (data.discount_preview) { cart.discount_preview = data.discount_preview; }
                if (data.voucher_preview) { cart.voucher_preview = data.voucher_preview; }
            }
            refreshCart();
        })
        .catch(function (err) {
            console.error('Cart initialization failed:', err);
            refreshCart();
        });

    // ===== Event handlers =====

    // Empty cart.
    const emptyCartBtn = document.getElementById('emptyCart');
    if (emptyCartBtn) {
        emptyCartBtn.addEventListener('click', function () {
            cart.discount_code = '';
            cart.voucher_preview = null;
            cart.student = false;
            syncCart([]);
        });
    }

    // Remove individual item.
    const shoppingCart = document.getElementById('shoppingCart');
    if (shoppingCart) {
        shoppingCart.addEventListener('click', function (e) {
            const btn = e.target.closest('.remove-item');
            if (!btn) { return; }
            const sku = btn.dataset.sku;
            syncCart(cart.items.filter(function (i) { return i.sku !== sku; }));
        });

        // Remove voucher.
        shoppingCart.addEventListener('click', function (e) {
            const btn = e.target.closest('.remove-voucher');
            if (!btn) { return; }
            cart.discount_code = '';
            cart.voucher_preview = null;
            syncCart(cart.items);
        });
    }

    // Submit registration (checkout).
    //
    // If regParams.preSubmit is defined (e.g. by public_register_cart.js), it
    // is called with the current cart state and its return value is used as the
    // item list to submit.  This lets the public register collect number-input
    // quantities at submit time without syncing on every keystroke.
    document.querySelectorAll('.submit-button').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            clearAlerts();
            const itemsToCheckout = (
                typeof regParams.preSubmit === 'function'
            ) ? regParams.preSubmit(cart) : cart.items;
            fetch(regParams.cartUrl, {
                method: 'POST',
                redirect: 'follow',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify(buildPayload(itemsToCheckout, { checkout: true })),
            })
            .then(function (response) {
                // fetch follows the server redirect; navigate to the final URL.
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
                if (!response.ok) {
                    return response.json().then(function (data) {
                        displayErrors(data);
                    });
                }
                // JSON response with explicit redirect field (future-proof).
                return response.json().then(function (data) {
                    if (data && data.redirect) {
                        window.location.href = data.redirect;
                    }
                });
            })
            .catch(function (err) {
                console.error('Checkout error:', err);
                addAlert('An error occurred during checkout. Please try again.');
            });
        });
    });

    // ===== Expose shared API for extension scripts =====
    window.registerCart = {
        cart:          cart,
        syncCart:      syncCart,
        refreshCart:   refreshCart,
        addAlert:      addAlert,
        clearAlerts:   clearAlerts,
        displayErrors: displayErrors,
        jsonFetch:     jsonFetch,
        csrfToken:     csrfToken,
        fmt:           fmt,
        toTitleCase:   toTitleCase,
        htmlToNodes:   htmlToNodes,
    };

});
