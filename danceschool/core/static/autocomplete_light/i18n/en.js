/*
 * DAL language file override for Select2 4.0.x compatibility.
 *
 * DAL's upstream en.js uses Select2 4.1.x's $.fn.select2.amd AMD module system,
 * which does not exist in Django admin's bundled Select2 4.0.13. This causes:
 *   TypeError: Cannot read properties of undefined (reading 'define')
 *
 * Select2 4.0.x has English strings built in, so language registration is a
 * no-op here. The dal-language-loaded event must still be dispatched so that
 * autocomplete_light.js completes its initialisation.
 */
var dalLoadLanguage = function(e) {
    if (!e || !e.fn || !e.fn.select2 || !e.fn.select2.amd) { return; }
    var amd = e.fn.select2.amd;
    amd.define('select2/i18n/en', [], function() {
        return {
            errorLoading: function() { return 'The results could not be loaded.'; },
            inputTooLong: function(e) {
                var n = e.input.length - e.maximum;
                return 'Please delete ' + n + ' character' + (n !== 1 ? 's' : '');
            },
            inputTooShort: function(e) {
                return 'Please enter ' + (e.minimum - e.input.length) + ' or more characters';
            },
            loadingMore: function() { return 'Loading more results…'; },
            maximumSelected: function(e) {
                return 'You can only select ' + e.maximum + ' item' + (e.maximum !== 1 ? 's' : '');
            },
            noResults: function() { return 'No results found'; },
            searching: function() { return 'Searching…'; },
            removeAllItems: function() { return 'Remove all items'; },
            removeItem: function() { return 'Remove item'; },
            search: function() { return 'Search'; }
        };
    });
};
var event = new CustomEvent('dal-language-loaded', {lang: 'en'});
document.dispatchEvent(event);
