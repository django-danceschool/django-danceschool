/**
 * manage_register_cart.js
 *
 * At-the-door registration using the CartView API (/registration/cart/).
 * No jQuery dependency.
 *
 * Catalog (prices, descriptions) is loaded from PurchasableItemsView on page
 * start. Cart state is maintained locally and synced to the server on every
 * change.  Discount codes are stored in the cart and applied at checkout.
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

    function lookupDescription(sku) {
        return catalog[sku] ? catalog[sku].description : sku;
    }

    // ===== Local cart state =====
    // Mirrors what the server stores in the session.
    let cart = {
        items: [],
        discount_code: '',
        student: false,
        payAtDoor: regParams.payAtDoor,
        discount_preview: null,
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
            const price = lookupPrice(item.sku);
            const qty = item.quantity || 1;
            const lineTotal = price * qty;
            grossTotal += lineTotal;

            const tr = document.createElement('tr');
            tr.dataset.sku = item.sku;
            if (item.choiceId) { tr.dataset.choiceId = item.choiceId; }

            tr.innerHTML =
                '<td>' + lookupDescription(item.sku) + '</td>' +
                '<td>' + regParams.currencySymbol + fmt(lineTotal) +
                '<button type="button" class="close remove-item" aria-label="Remove"' +
                ' data-sku="' + item.sku + '">' +
                '<span aria-hidden="true">&times;</span></button></td>';

            if (tbody) { tbody.appendChild(tr); }

            // Update the badge on the source button.
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
            cart.items = data.items || [];
            cart.student = data.student || false;
            cart.discount_preview = data.discount_preview || null;
            refreshCart();
        })
        .catch(function (errors) {
            displayErrors(errors);
            refreshCart();
        });
    }

    // ===== Item format translation =====
    // Translates the data attributes from .add-item buttons (legacy format used
    // by existing register plugin templates) into CartView item format.
    //
    // Legacy button attributes:
    //   type="eventRegistration", event="<id>", roleId="<id>", dropIn="true/false"
    //   type="MerchItem", itemId="<id>", sku="<sku>"
    //
    // Items that already provide item_type / item_id / sku pass through unchanged.

    function translateButtonData(raw) {
        // Already in CartView format.
        if (raw.itemType || raw.item_type) {
            return {
                item_type: raw.itemType || raw.item_type,
                item_id: parseInt(raw.itemId || raw.item_id),
                sku: raw.sku,
                quantity: parseInt(raw.quantity) || 1,
                choiceId: raw.choiceId || null,
            };
        }

        if (raw.type === 'eventRegistration') {
            const eventId = raw.event;
            let sku;
            if (raw.roleId && !isNaN(parseInt(raw.roleId))) {
                sku = 'EVENT_' + eventId + '_ROLE_' + raw.roleId;
            } else {
                sku = 'EVENT_' + eventId + '_GENERAL';
            }
            const item = {
                item_type: 'Event',
                item_id: parseInt(eventId),
                sku: sku,
                quantity: parseInt(raw.quantity) || 1,
                choiceId: raw.choiceId || null,
            };
            if (raw.dropIn === 'true' || raw.dropIn === true) { item.dropIn = true; }
            if (raw.requireFull !== undefined) { item.requireFull = (raw.requireFull === 'true'); }
            if (raw.autoSubmit !== undefined) { item.autoSubmit = (raw.autoSubmit === 'true'); }
            if (raw.autoFulfill !== undefined) { item.autoFulfill = (raw.autoFulfill === 'true'); }
            return item;
        }

        if (raw.type === 'MerchItem' || raw.type === 'merch') {
            return {
                item_type: 'MerchItem',
                item_id: parseInt(raw.itemId),
                sku: raw.sku,
                quantity: parseInt(raw.quantity) || 1,
                choiceId: raw.choiceId || null,
            };
        }

        // Unknown type — pass through as-is and let the server validate.
        return raw;
    }

    // ===== Initialization =====

    jsonFetch(regParams.purchasableItemsUrl + '?payAtDoor=true')
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
            }
            refreshCart();
        })
        .catch(function (err) {
            console.error('Cart initialization failed:', err);
            refreshCart();
        });

    // ===== Event handlers =====

    // Add item to cart.
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.add-item');
        if (!btn) { return; }

        const raw = {};
        Object.keys(btn.dataset).forEach(function (k) { raw[k] = btn.dataset[k]; });

        // Embedded voucher code.
        if (raw.voucherId) {
            if (cart.discount_code && cart.discount_code !== raw.voucherId) {
                addAlert(regParams.multipleVoucherString);
                return;
            }
            cart.discount_code = raw.voucherId;
            delete raw.voucherId;
        }

        const newItem = translateButtonData(raw);
        const existingIdx = cart.items.findIndex(function (i) { return i.sku === newItem.sku; });
        let updatedItems;

        if (existingIdx !== -1 && raw.updateQuantity === 'true') {
            updatedItems = cart.items.map(function (item, idx) {
                if (idx !== existingIdx) { return item; }
                return Object.assign({}, item, {
                    quantity: (item.quantity || 1) + (newItem.quantity || 1),
                });
            });
        } else if (existingIdx !== -1) {
            updatedItems = cart.items.map(function (item, idx) {
                return idx === existingIdx ? newItem : item;
            });
        } else {
            updatedItems = cart.items.concat([newItem]);
        }

        syncCart(updatedItems);
    });

    // Empty cart.
    const emptyCartBtn = document.getElementById('emptyCart');
    if (emptyCartBtn) {
        emptyCartBtn.addEventListener('click', function () {
            cart.discount_code = '';
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
            syncCart(cart.items);
        });
    }

    // Submit registration (checkout).
    document.querySelectorAll('.submit-button').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            clearAlerts();
            fetch(regParams.cartUrl, {
                method: 'POST',
                redirect: 'follow',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify(buildPayload(cart.items, { checkout: true })),
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

    // Add voucher code.
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.add-voucher');
        if (!btn) { return; }

        let code = btn.dataset.id || '';
        if (!code) {
            const input = btn.closest('.voucherDetail') &&
                btn.closest('.voucherDetail').querySelector('input');
            if (input) { code = input.value; }
        }
        if (!code) { return; }

        if (cart.discount_code && cart.discount_code !== code) {
            addAlert(regParams.multipleVoucherString);
            return;
        }

        cart.discount_code = code;

        if (!cart.items || cart.items.length === 0) {
            addAlert(regParams.emptyRegisterVoucherString, 'alert-info');
        } else {
            syncCart(cart.items);
        }
    });

    // ===== Customer lookup =====

    const nameSelect = document.getElementById('id_name');
    if (nameSelect) {
        nameSelect.addEventListener('change', function () {
            const opt = this.options[this.selectedIndex];
            const optData = opt ? opt.dataset : {};

            if (!optData.type) {
                clearCustomerPanels();
                return;
            }

            if (optData.type === regParams.customerString) {
                const payload = {
                    id: optData.id,
                    guestType: optData.type,
                    date: regParams.registerDate,
                    eventList: regParams.guestLookupEvents,
                };

                clearElement('guestInfoTable', 'tbody tr td');
                hideEl('guestInfoTable');
                clearElement('customerInfoTable', 'tbody');
                showEl('customerInfoCard');

                jsonFetch(regParams.customerLookupUrl, {
                    method: 'POST',
                    body: JSON.stringify(payload),
                })
                .then(function (r) { return r.json(); })
                .then(function (response) {
                    const table = document.getElementById('customerInfoTable');
                    const example = document.getElementById('customerInfoExample');
                    if (!table || !example) { return; }
                    table.classList.remove('d-none');
                    const tbody = table.querySelector('tbody');

                    response.forEach(function (entry) {
                        const row = example.querySelector('tr').cloneNode(true);
                        const checkId = 'checkIn_' + entry.id + '_' + entry.occurrenceId;
                        setCheckIn(row, '.customerCheckIn', checkId, {
                            checked: entry.checkedIn,
                            value: entry.id,
                            occurrenceId: entry.occurrenceId,
                            eventId: entry.event.id,
                        });

                        let statusString = entry.registration.invoice.statusLabel;
                        if (entry.registration.invoice.outstandingBalance > 0) {
                            statusString += ' (' + regParams.outstandingBalanceString +
                                ' ' + regParams.currencySymbol +
                                fmt(entry.registration.invoice.outstandingBalance) + ')';
                        }

                        let extrasText = '';
                        regExtrasFunctions.forEach(function (fn) { extrasText += fn(entry.extras); });
                        const extrasEl = row.querySelector('.customerInfoExtras');
                        if (extrasEl) { extrasEl.replaceChildren.apply(extrasEl, htmlToNodes(extrasText)); }

                        let roleHtml = '';
                        if (extrasText) { roleHtml += '<strong>' + regParams.roleString + ':</strong> '; }
                        if (entry.dropIn) { roleHtml += regParams.dropInString + ' '; }
                        if (entry.role && entry.role.name) { roleHtml += entry.role.name; }
                        const roleEl = row.querySelector('.customerInfoRole');
                        if (roleEl) { roleEl.innerHTML = roleHtml; }

                        setText(row, '.customerInfoEvent', entry.event.name);
                        setText(row, '.customerInfoTime',
                            new Date(entry.occurrenceStartTime)
                                .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        );
                        setText(row, '.customerInfoStudent', toTitleCase(String(entry.student)));
                        setText(row, '.customerInfoPaymentStatus', statusString);
                        setHref(row, '.customerInvoiceLink', entry.registration.invoice.url);
                        setHref(row, '.customerRegistrationLink', entry.registration.url);

                        tbody.appendChild(row);
                    });
                });

            } else if (optData.type) {
                const payload = {
                    id: optData.id,
                    guestListId: optData.guestListId,
                    modelType: optData.modelType,
                    date: regParams.registerDate,
                    eventList: regParams.guestLookupEvents,
                    checkinType: 'O',
                };

                clearElement('customerInfoTable', 'tbody');
                hideEl('customerInfoTable');
                showEl('customerInfoCard');
                clearElement('guestInfoTable', 'tbody');

                jsonFetch(regParams.guestLookupUrl, {
                    method: 'POST',
                    body: JSON.stringify(payload),
                })
                .then(function (r) { return r.json(); })
                .then(function (response) {
                    const table = document.getElementById('guestInfoTable');
                    const example = document.getElementById('guestInfoExample');
                    if (!table || !example) { return; }
                    table.classList.remove('d-none');
                    const tbody = table.querySelector('tbody');

                    (response.events || []).forEach(function (entry) {
                        const row = example.querySelector('tr').cloneNode(true);
                        const checkId = 'checkIn_' + entry.id + '_' + entry.eventId;
                        setCheckIn(row, '.customerCheckIn', checkId, {
                            checked: entry.checkedIn,
                            value: entry.id,
                            firstName: entry.firstName,
                            lastName: entry.lastName,
                            modelType: entry.modelType,
                            eventId: entry.eventId,
                            occurrenceId: entry.occurrenceId,
                        });

                        setText(row, '.guestInfoEvent', entry.eventName);

                        const nameEl = row.querySelector('.guestInfoName');
                        if (nameEl) {
                            let nameHtml = entry.firstName + ' ' + entry.lastName;
                            if (entry.email) { nameHtml += '<br>' + entry.email; }
                            nameEl.innerHTML = nameHtml;
                        }

                        setText(row, '.guestInfoType', entry.guestType);

                        let extrasText = '';
                        regExtrasFunctions.forEach(function (fn) { extrasText += fn(entry.extras); });
                        const extrasEl = row.querySelector('.guestInfoExtras');
                        if (extrasEl) { extrasEl.replaceChildren.apply(extrasEl, htmlToNodes(extrasText)); }

                        tbody.appendChild(row);
                    });
                });
            }
        });
    }

    // ===== Check-in =====

    document.addEventListener('click', function (e) {
        const checkIn = e.target.closest('.customerCheckIn');
        if (!checkIn) { return; }

        checkIn.disabled = true;
        const initialStatus = !checkIn.checked;

        const requestData = {
            request: 'update',
            event_id: checkIn.dataset.eventId,
            checkin_type: 'O',
            occurrence_id: checkIn.dataset.occurrenceId,
        };

        if (checkIn.classList.contains('guestCheckIn')) {
            requestData.names = [{
                first_name: checkIn.dataset.firstName,
                last_name: checkIn.dataset.lastName,
                cancelled: !checkIn.checked,
            }];
        } else if (checkIn.classList.contains('registrationCheckIn')) {
            requestData.registrations = [{
                id: checkIn.value,
                cancelled: !checkIn.checked,
            }];
        }

        jsonFetch(regParams.checkInUrl, {
            method: 'POST',
            body: JSON.stringify(requestData),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            setTimeout(function () {
                document.querySelectorAll('.customerCheckIn,.guestCheckIn')
                    .forEach(function (el) { el.removeAttribute('disabled'); });
            }, 500);
            if (data.status !== 'success') {
                checkIn.checked = initialStatus;
            }
        })
        .catch(function () {
            setTimeout(function () {
                checkIn.checked = initialStatus;
                document.querySelectorAll('.customerCheckIn')
                    .forEach(function (el) { el.removeAttribute('disabled'); });
            }, 500);
        });
    });

    // ===== DOM helpers =====

    function clearCustomerPanels() {
        clearElement('guestInfoTable', 'tbody');
        hideEl('guestInfoTable');
        clearElement('customerInfoTable', 'tbody');
        hideEl('customerInfoTable');
    }

    function clearElement(tableId, selector) {
        const el = document.getElementById(tableId);
        if (!el) { return; }
        const target = selector ? el.querySelector(selector) : el;
        if (target) { target.innerHTML = ''; }
    }

    function hideEl(id) {
        const el = document.getElementById(id);
        if (el) { el.classList.add('d-none'); }
    }

    function showEl(id) {
        const el = document.getElementById(id);
        if (!el) { return; }
        el.classList.remove('collapse');
        el.classList.add('show');
    }

    function setText(row, selector, text) {
        const el = row.querySelector(selector);
        if (el) { el.textContent = text; }
    }

    function setHref(row, selector, href) {
        const el = row.querySelector(selector);
        if (el) { el.href = href; }
    }

    function setCheckIn(row, selector, checkId, data) {
        const checkIn = row.querySelector(selector);
        const label = row.querySelector(selector + 'Label');
        if (checkIn) {
            checkIn.setAttribute('id', checkId);
            checkIn.checked = data.checked || false;
            checkIn.value = data.value || '';
            Object.keys(data).forEach(function (k) {
                if (k !== 'checked' && k !== 'value') {
                    checkIn.dataset[k] = data[k];
                }
            });
        }
        if (label) { label.setAttribute('for', checkId); }
    }

});
