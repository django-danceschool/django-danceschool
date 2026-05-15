/*global SelectBox, interpolate*/
// Handles related-objects functionality: lookup link for raw_id_fields
// and Add Another links.

document.addEventListener("DOMContentLoaded", function(event) {
    'use strict';

    // IE doesn't accept periods or dashes in the window name, but the element IDs
    // we use to generate popup window names may contain them, therefore we map them
    // to allowed characters in a reversible way so that we can locate the correct
    // element when the popup window is dismissed.
    function location_id_to_windowname(text) {
        text = text.replace(/\./g, '__dot__');
        text = text.replace(/\-/g, '__dash__');
        return text;
    }

    function location_windowname_to_id(text) {
        text = text.replace(/__dot__/g, '.');
        text = text.replace(/__dash__/g, '-');
        return text;
    }

    function dismissLocationAddRelatedObjectPopup(win, newId, newRepr, newRoomOptions, newDefaultCapacity) {
        var name = location_windowname_to_id(win.name);
        var elem = document.getElementById(name);
        if (elem) {
            var elemName = elem.nodeName.toUpperCase();
            if (elemName === 'SELECT') {
                var o = new Option(newRepr, newId, true, true);
                // Store room options data as custom properties (read by serieslocation_capacity_change.js)
                o._roomoptions = JSON.parse(newRoomOptions) || [];
                o._defaultcapacity = newDefaultCapacity;
                elem.options[elem.options.length] = o;
            } else if (elemName === 'INPUT') {
                if (elem.className.indexOf('vManyToManyRawIdAdminField') !== -1 && elem.value) {
                    elem.value += ',' + newId;
                } else {
                    elem.value = newId;
                }
            }
            // Trigger a change event to update related links if required.
            elem.dispatchEvent(new Event('change', {bubbles: true}));
        } else {
            var toId = name + "_to";
            var o = new Option(newRepr, newId);
            o._roomoptions = JSON.parse(newRoomOptions) || [];
            o._defaultcapacity = newDefaultCapacity;
            SelectBox.add_to_cache(toId, o);
            SelectBox.redisplay(toId);
        }
        win.close();
    }

    function dismissLocationChangeRelatedObjectPopup(win, objId, newRepr, newId, newRoomOptions, newDefaultCapacity) {
        var id = location_windowname_to_id(win.name).replace(/^edit_/, '');
        var selects = document.querySelectorAll('#' + id + ', #' + id + '_from, #' + id + '_to');
        selects.forEach(function(select) {
            Array.from(select.options).forEach(function(opt) {
                if (opt.value === objId) {
                    opt.textContent = newRepr;
                    opt.value = newId;
                    opt._roomoptions = JSON.parse(newRoomOptions) || [];
                    opt._defaultcapacity = newDefaultCapacity;
                    select.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
        });
        win.close();
    }

    window.dismissLocationAddRelatedObjectPopup = dismissLocationAddRelatedObjectPopup;
    window.dismissLocationChangeRelatedObjectPopup = dismissLocationChangeRelatedObjectPopup;

});
