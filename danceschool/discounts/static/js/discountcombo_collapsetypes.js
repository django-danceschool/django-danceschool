$(document).ready(function(){

	function checkDiscountType() {
		var discountType = $('#id_discountType').val();

		if (discountType == "F") {
			$('.type_flatPrice').removeClass('collapsed');
			$('.type_flatPrice').find('h2').show();

			$('.type_dollarDiscount').addClass('collapsed');
			$('.type_dollarDiscount').find('h2').hide();

			$('.type_percentageDiscount').addClass('collapsed');
			$('.type_percentageDiscount').find('h2').hide();
		}
		if (discountType == "D") {
			$('.type_flatPrice').addClass('collapsed');
			$('.type_flatPrice').find('h2').hide();

			$('.type_dollarDiscount').removeClass('collapsed');
			$('.type_dollarDiscount').find('h2').show();

			$('.type_percentageDiscount').addClass('collapsed');
			$('.type_percentageDiscount').find('h2').hide();
		}
		if (discountType == "P") {
			$('.type_flatPrice').addClass('collapsed');
			$('.type_flatPrice').find('h2').hide();

			$('.type_dollarDiscount').addClass('collapsed');
			$('.type_dollarDiscount').find('h2').hide();

			$('.type_percentageDiscount').removeClass('collapsed');
			$('.type_percentageDiscount').find('h2').show();
		}
		if (discountType == "A") {
			$('.type_flatPrice').addClass('collapsed');
			$('.type_flatPrice').find('h2').hide();

			$('.type_dollarDiscount').addClass('collapsed');
			$('.type_dollarDiscount').find('h2').hide();

			$('.type_percentageDiscount').addClass('collapsed');
			$('.type_percentageDiscount').find('h2').hide();
		}
	}

	checkDiscountType();

	$('#id_discountType').change(function(event){
		checkDiscountType();
	});

});