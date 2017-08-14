/*global opener */
(function() {
    'use strict';
    var initData = JSON.parse(document.getElementById('django-admin-popup-response-constants').dataset.popupResponse);
    switch(initData.action) {
    case 'change':
        // Call modified version of dismissChangeRelatedObjectPopup that populates room options and capacity
        opener.dismissLocationChangeRelatedObjectPopup(window, initData.value, initData.obj, initData.new_value, initData.roomOptions, initData.defaultCapacity);
        break;
    case 'delete':
        opener.dismissDeleteRelatedObjectPopup(window, initData.value);
        break;
    default:
        // Call modified version of dismissAddRelatedObjectPopup that populates room options and capacity
        opener.dismissLocationAddRelatedObjectPopup(window, initData.value, initData.obj, initData.roomOptions, initData.defaultCapacity);
        break;
    }
})();
