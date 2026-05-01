(function () {
    'use strict';

    // Capture currentScript synchronously before any async callbacks run.
    var scriptTag = document.currentScript;

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    /**
     * Build the canonical SKU string for a cart item.
     *
     * Format:  EVENT_{id}[_DROPIN]_ROLE_{roleId}
     *       or EVENT_{id}[_DROPIN]_GENERAL
     *
     * The DROPIN segment is inserted when data-dropin-id is present, and the
     * ROLE segment is inserted when data-role-id is present.  The two are
     * independent and can appear together (e.g. a drop-in for a specific role).
     */
    function buildSku(dataset) {
        var id = dataset.id;
        var middle = dataset.dropinId ? '_DROPIN' : '';
        if (dataset.roleId) {
            return 'EVENT_' + id + middle + '_ROLE_' + dataset.roleId;
        }
        return 'EVENT_' + id + middle + '_GENERAL';
    }

    function submitAddToCart(cartUrl, fields) {
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = cartUrl;

        Object.keys(fields).forEach(function (name) {
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = fields[name];
            form.appendChild(input);
        });

        document.body.appendChild(form);
        form.submit();
    }

    document.addEventListener('DOMContentLoaded', function () {
        var cartUrl = scriptTag && scriptTag.getAttribute('data-cart-url');
        if (!cartUrl) {
            console.error('classregistration_ajax.js: data-cart-url is not set on the script tag.');
            return;
        }

        document.querySelectorAll('.register-ajax').forEach(function (button) {
            button.addEventListener('click', function (e) {
                e.preventDefault();
                var d = this.dataset;

                var fields = {
                    csrfmiddlewaretoken: getCsrfToken(),
                    action: 'add',
                    item_id: d.id,
                    sku: buildSku(d),
                    quantity: '1',
                };

                if (d.dropinId) {
                    fields.dropIn = 'true';
                    fields.dropInOccurrence = d.dropinId;
                }

                submitAddToCart(cartUrl, fields);
            });
        });
    });
}());
