/* Progressive enhancement: add-to-cart / wishlist without a page reload, toasts, quantity steppers. */
(function ($) {
  'use strict';

  function toast(message, level) {
    var $stack = $('#toast-stack');
    var $t = $('<div class="toast-msg" role="status"></div>').addClass('toast-' + (level || 'success')).text(message);
    $stack.append($t);
    setTimeout(function () { $t.css('opacity', 0); setTimeout(function () { $t.remove(); }, 400); }, 3500);
  }

  // Flash messages rendered by the server fade out too
  $('#toast-stack .toast-msg').each(function () {
    var $t = $(this);
    setTimeout(function () { $t.css('opacity', 0); setTimeout(function () { $t.remove(); }, 400); }, 4500);
  });

  function post($form, done) {
    var $btn = $form.find('button[type=submit]').prop('disabled', true);
    $.ajax({
      url: $form.attr('action'), method: 'POST', data: $form.serialize(),
      headers: { 'X-Requested-With': 'XMLHttpRequest' }, dataType: 'json'
    }).done(done).fail(function (xhr) {
      var msg = (xhr.responseJSON && xhr.responseJSON.message) || 'Something went wrong. Please try again.';
      toast(msg, 'error');
    }).always(function () { $btn.prop('disabled', false); });
  }

  // "Buy now" must do a normal submit (it redirects to the cart)
  $(document).on('click', 'button[name=buy_now]', function () { $(this).closest('form').data('plain', true); });

  $(document).on('submit', '.js-cart-form', function (e) {
    var $form = $(this);
    if ($form.data('plain')) { return; }
    e.preventDefault();
    post($form, function (data) {
      $('#cart-count').text(data.cart_count);
      toast(data.message, 'success');
    });
  });

  $(document).on('submit', '.js-wish-form', function (e) {
    e.preventDefault();
    var $form = $(this);
    post($form, function (data) {
      $('#wishlist-count').text(data.wishlist_count ? ' [' + data.wishlist_count + ']' : '');
      $form.find('button.heart').toggleClass('is-saved', data.added);
      if (!data.added && /\/wishlist\/$/.test(location.pathname)) {
        $form.closest('.col-md-6').fadeOut(200, function () { $(this).remove(); });
      }
      toast(data.message, 'success');
    });
  });

  // Quantity steppers on the product page
  $('.quantity-right-plus').on('click', function (e) {
    e.preventDefault();
    var $q = $('#quantity'), max = parseInt($q.attr('max'), 10) || 50, v = parseInt($q.val(), 10) || 1;
    $q.val(Math.min(v + 1, max));
  });
  $('.quantity-left-minus').on('click', function (e) {
    e.preventDefault();
    var $q = $('#quantity'), v = parseInt($q.val(), 10) || 1;
    $q.val(Math.max(v - 1, 1));
  });

  // Cart page: submit when the quantity changes
  $('.js-qty-form input[name=quantity]').on('change', function () { this.form.submit(); });

  // Hide bank details unless bank transfer is selected
  function syncBank() {
    var transfer = $('input[name=payment_method]:checked').val() === 'transfer';
    $('#bank-details').toggle(transfer);
    $('#card-note').toggle($('input[name=payment_method]:checked').val() === 'card');
  }
  if ($('#bank-details').length) { $('input[name=payment_method]').on('change', syncBank); syncBank(); }

  // The template reveals .ftco-animate blocks via scroll waypoints, which can miss content that is
  // already on screen at load (e.g. on tall phones). Reveal on intersection instead, with a safe fallback.
  function reveal(el) { $(el).addClass('fadeInUp ftco-animated'); }
  var $animated = $('.ftco-animate');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { reveal(en.target); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -5% 0px' });
    $animated.each(function () { io.observe(this); });
  } else {
    $animated.each(function () { reveal(this); });
  }
})(jQuery);
