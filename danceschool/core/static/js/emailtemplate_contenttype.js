$(document).ready(function(){

	function checkRichTextChoice() {
		var richTextChoice = $('#id_richTextChoice input:checked').val();

		if (CKEDITOR.instances['id_html_content']) {
			window.initial_CKEditor_config = CKEDITOR.instances['id_html_content'].config;
			CKEDITOR.instances['id_html_content'].destroy();		
		}

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
			CKEDITOR.replace('id_html_content', window.initial_CKEditor_config);
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