document.addEventListener("DOMContentLoaded", function(event) {

	function checkDiscountType() {
		var discountType = document.getElementById('id_discountType').value;
		var types = ['type_flatPrice', 'type_dollarDiscount', 'type_percentageDiscount'];
		var activeType = {
			'F': 'type_flatPrice',
			'D': 'type_dollarDiscount',
			'P': 'type_percentageDiscount',
		}[discountType];

		types.forEach(function(cls) {
			document.querySelectorAll('.' + cls).forEach(function(el) {
				if (cls === activeType) {
					el.classList.remove('collapsed');
					var h2 = el.querySelector('h2');
					if (h2) { h2.style.display = ''; }
				} else {
					el.classList.add('collapsed');
					var h2 = el.querySelector('h2');
					if (h2) { h2.style.display = 'none'; }
				}
			});
		});
	}

	checkDiscountType();

	document.getElementById('id_discountType').addEventListener('change', function(event){
		checkDiscountType();
	});
});
