document.addEventListener("DOMContentLoaded", function(e) {

	document.getElementById('id_category').addEventListener('change', function(){
		var selected = this.options[this.selectedIndex];
		document.getElementById('id_wageRate').value = selected ? (selected.dataset.defaultrate || '') : '';
	});

});
