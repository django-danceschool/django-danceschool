document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

	function checkRichTextChoice() {
		var richTextChoice = $('#id_richTextChoice input:checked').val();

		if (richTextChoice == "plain") {
			$('#id_content').parents('fieldset').first().removeClass('collapsed');
			$('#id_content').parents('fieldset').first().find('h2').show();

			$('#id_html_content').parents('fieldset').first().addClass('collapsed');
			$('#id_html_content').parents('fieldset').first().find('h2').hide();
		}
		if (richTextChoice == "HTML") {
			$('#id_content').parents('fieldset').first().addClass('collapsed');
			$('#id_content').parents('fieldset').first().find('h2').hide();

			$('#id_html_content').parents('fieldset').first().removeClass('collapsed');
			$('#id_html_content').parents('fieldset').first().find('h2').show();
		}
	}

	$('#id_richTextChoice').change(function(event){
		checkRichTextChoice();
	});

	CKEDITOR.on('pagePrepared', function() {
		checkRichTextChoice();
	});

	CKEDITOR.on('instanceReady', function() {
		CKEDITOR.fireOnce('pagePrepared');
	});

});
