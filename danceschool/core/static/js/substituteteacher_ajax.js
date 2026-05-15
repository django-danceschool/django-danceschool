document.addEventListener("DOMContentLoaded", function(event) {

	document.getElementById('id_occurrences').disabled = true;
	document.getElementById('id_occurrences').closest('div.mb-3').style.display = 'none';
	document.getElementById('id_replacedStaffMember').disabled = true;
	document.getElementById('id_replacedStaffMember').closest('div.mb-3').style.display = 'none';

	function getCookie(name) {
	    var cookieValue = null;
	    if (document.cookie && document.cookie !== '') {
	        var cookies = document.cookie.split(';');
	        for (var i = 0; i < cookies.length; i++) {
	            var cookie = cookies[i].trim();
	            if (cookie.substring(0, name.length + 1) === (name + '=')) {
	                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
	                break;
	            }
	        }
	    }
	    return cookieValue;
	}

	function postForm(formData) {
		return fetch("/staff/substitute/filter/", {
			method: "POST",
			headers: {"X-CSRFToken": getCookie('csrftoken')},
			body: new URLSearchParams(formData),
		}).then(function(response) { return response.json(); });
	}

	// id_event uses a Select2 autocomplete widget (dal), which triggers change via
	// jQuery.trigger() — not a native DOM event. Use django.jQuery to receive it.
	django.jQuery('#id_event').on('change', function() {
		var formData = {
			event: document.getElementById('id_event').value,
			category: document.getElementById('id_category').value,
		};

		postForm(formData)
		.then(function(data) {
			var occurrencesSelect = document.getElementById('id_occurrences');
			var replacedSelect = document.getElementById('id_replacedStaffMember');

			occurrencesSelect.innerHTML = '';
			replacedSelect.innerHTML = '';

			Object.entries(data['id_occurrences']).forEach(function([index, text]) {
				var opt = new Option(text, index);
				occurrencesSelect.appendChild(opt);
			});
			Object.entries(data['id_replacedStaffMember']).forEach(function([index, text]) {
				var opt = new Option(text, index);
				replacedSelect.appendChild(opt);
			});

			occurrencesSelect.closest('div.mb-3').style.display = '';
			occurrencesSelect.disabled = false;

			if (Object.keys(data['id_replacedStaffMember']).length !== 0) {
				replacedSelect.closest('div.mb-3').style.display = '';
				replacedSelect.disabled = false;
			}
		})
		.catch(function() {
			console.log('Failed to retrieve dropdown data using AJAX.');
		});
	});

	['id_category', 'id_occurrences'].forEach(function(id) {
		document.getElementById(id).addEventListener('change', function() {
			var formData = {
				event: document.getElementById('id_event').value,
				category: document.getElementById('id_category').value,
				occurrences: document.getElementById('id_occurrences').value,
			};

			postForm(formData)
			.then(function(data) {
				var replacedSelect = document.getElementById('id_replacedStaffMember');
				replacedSelect.innerHTML = '';

				Object.entries(data['id_replacedStaffMember']).forEach(function([index, text]) {
					var opt = new Option(text, index);
					replacedSelect.appendChild(opt);
				});

				replacedSelect.closest('div.mb-3').style.display = '';
				replacedSelect.disabled = false;
			})
			.catch(function() {
				console.log('Failed to retrieve dropdown data using AJAX.');
			});
		});
	});
});
