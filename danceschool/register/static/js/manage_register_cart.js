/**
 * manage_register_cart.js
 *
 * At-the-door register extension for register_cart_common.js.
 * Adds item-button handling, voucher codes, customer/guest lookup, and
 * check-in.  Requires register_cart_common.js to be loaded first.
 *
 * Legacy button attributes translated to CartView item format:
 *   type="eventRegistration", event="<id>", roleId="<id>", dropIn="true/false"
 *   type="MerchItem", itemId="<id>", sku="<sku>"
 *
 * Items that already carry item_type / item_id / sku pass through unchanged.
 */
document.addEventListener('DOMContentLoaded', function () {

    const {
        cart, syncCart, addAlert, jsonFetch,
        fmt, toTitleCase, htmlToNodes,
    } = window.registerCart;

    // ===== Item format translation =====
    // Translates the data attributes from .add-item buttons (legacy format used
    // by existing register plugin templates) into CartView item format.

    // Template data attributes use Python-style booleans ("True"/"False").
    // This helper matches both "True" and "true" (and the boolean true).
    function isTruthy(v) {
        return v === true || (typeof v === 'string' && v.toLowerCase() === 'true');
    }

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
                // Cache the event name so lookupDescription() can fall back to
                // it when the SKU is not yet in the catalog.
                description: raw.name || raw.description || null,
                // Cache the door price from data-price so lookupPrice() has a
                // fallback when the catalog SKU is not yet populated.
                price: raw.price ? parseFloat(raw.price) : null,
            };
            if (isTruthy(raw.dropIn)) {
                item.dropIn = true;
                if (raw.dropInOccurrence) {
                    item.dropInOccurrence = parseInt(raw.dropInOccurrence);
                }
            }
            if (raw.requireFull !== undefined) { item.requireFull = isTruthy(raw.requireFull); }
            if (raw.autoSubmit !== undefined) { item.autoSubmit = isTruthy(raw.autoSubmit); }
            if (raw.autoFulfill !== undefined) { item.autoFulfill = isTruthy(raw.autoFulfill); }
            return item;
        }

        if (raw.type === 'MerchItem' || raw.type === 'merch' || raw.type === 'merchItem') {
            return {
                item_type: 'MerchItem',
                item_id: parseInt(raw.itemId),
                sku: raw.sku,
                quantity: parseInt(raw.quantity) || 1,
                choiceId: raw.choiceId || null,
                description: raw.description || null,
                price: raw.price ? parseFloat(raw.price) : null,
            };
        }

        // Unknown type — pass through as-is and let the server validate.
        return raw;
    }

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

        // Student flag: propagate to cart-level state so the server can
        // apply student-only discounts.
        if (raw.student === 'True' || raw.student === 'true' || raw.student === true) {
            cart.student = true;
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
            // Select2 (via django-autocomplete-light) stores result data in
            // jQuery's internal data store on the <option> element, not as
            // plain HTML data-* attributes.  jQuery is always present on the
            // CMS admin page, so use it to read the option data.
            const $ = window.jQuery;
            const optData = $ ? ($(this).find('option:selected').data() || {}) : {};


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
