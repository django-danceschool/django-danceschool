document.addEventListener("DOMContentLoaded", function(event) { 

	// The code below requires jQuery
	var $ = django.jQuery;

	$("#id_template").select2({
	  tags: true,
	  createTag: function (params) {
	    return {
	      id: params.term,
	      text: params.term,
	      newOption: true
	    }
	  },
	   templateResult: function (data) {
	    var $result = $("<span></span>");

	    $result.text(data.text);

	    if (data.newOption) {
	      $result.append(" <em>(new)</em>");
	    }

	    return $result;
	  }
	});
});
