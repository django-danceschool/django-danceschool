document.addEventListener("DOMContentLoaded", function(event) {

	function checkRichTextChoice() {
		var richTextInput = document.querySelector('#id_richTextChoice input:checked');
		var richTextChoice = richTextInput ? richTextInput.value : null;

		if (richTextChoice == "plain") {
			var contentFieldset = document.getElementById('id_content').closest('fieldset');
			contentFieldset.classList.remove('collapsed');
			contentFieldset.querySelector('h2').style.display = '';

			var htmlFieldset = document.getElementById('id_html_content').closest('fieldset');
			htmlFieldset.classList.add('collapsed');
			htmlFieldset.querySelector('h2').style.display = 'none';
		}
		if (richTextChoice == "HTML") {
			var contentFieldset = document.getElementById('id_content').closest('fieldset');
			contentFieldset.classList.add('collapsed');
			contentFieldset.querySelector('h2').style.display = 'none';

			var htmlFieldset = document.getElementById('id_html_content').closest('fieldset');
			htmlFieldset.classList.remove('collapsed');
			htmlFieldset.querySelector('h2').style.display = '';
		}
	}

	document.getElementById('id_richTextChoice').addEventListener('change', function(event){
		checkRichTextChoice();
	});

	checkRichTextChoice();

});
