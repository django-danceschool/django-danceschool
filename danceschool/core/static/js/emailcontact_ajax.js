document.addEventListener("DOMContentLoaded", function(event) {

	function checkRichTextChoice() {
		var richTextInput = document.querySelector('#div_id_richTextChoice input:checked');
		var richTextChoice = richTextInput ? richTextInput.value : null;

		if (richTextChoice === 'plain') {
			document.getElementById('div_id_message').style.display = '';
			document.getElementById('div_id_html_message').style.display = 'none';
		} else if (richTextChoice === 'HTML') {
			document.getElementById('div_id_message').style.display = 'none';
			document.getElementById('div_id_html_message').style.display = '';
		}
	}

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

	function setEditorContent(html) {
		var editors = window.cms_editor_plugin && window.cms_editor_plugin._editors;
		var editor = editors && editors['id_html_message'];
		if (editor) {
			editor.commands.setContent(html || '');
		} else {
			document.getElementById('id_html_message').value = html || '';
		}
	}

	checkRichTextChoice();

	document.getElementById('div_id_richTextChoice').addEventListener('change', function(event){
		checkRichTextChoice();
	});

	document.getElementById('id_template').addEventListener('change', function(event){
		event.preventDefault();

		var formData = new FormData();
		formData.append('template', document.getElementById('id_template').value);

		fetch("/staff/sendemail/template/", {
			method: "POST",
			headers: {"X-CSRFToken": getCookie('csrftoken')},
			body: formData,
		})
		.then(function(response) { return response.json(); })
		.then(function(data) {
			document.getElementById('id_subject').value = data['subject'];
			document.getElementById('id_message').value = data['content'];
			document.getElementById('div_id_template').style.display = 'none';

			setEditorContent(data['html_content']);

			var richTextInput = document.querySelector('#div_id_richTextChoice input[value="' + data['richTextChoice'] + '"]');
			if (richTextInput) { richTextInput.checked = true; }
			checkRichTextChoice();
		})
		.catch(function() {
			console.log('Failed to retrieve template data using AJAX.');
		});
	});

});
