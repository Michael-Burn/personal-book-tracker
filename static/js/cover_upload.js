/**
 * Resize/compress book cover files before multipart form submit.
 * Keeps payloads small so Werkzeug multipart parsing (and CSRF) do not
 * see a truncated empty form on large phone photos.
 */
(function (global) {
  'use strict';

  var MAX_EDGE = 600;
  var JPEG_QUALITY = 0.85;
  var SKIP_UNDER_BYTES = 400 * 1024;

  function loadImage(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('Could not read cover image'));
      };
      img.src = url;
    });
  }

  function canvasToBlob(canvas, type, quality) {
    return new Promise(function (resolve) {
      if (canvas.toBlob) {
        canvas.toBlob(function (blob) {
          resolve(blob);
        }, type, quality);
        return;
      }
      try {
        var dataUrl = canvas.toDataURL(type, quality);
        var parts = dataUrl.split(',');
        var bin = atob(parts[1] || '');
        var arr = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        resolve(new Blob([arr], { type: type }));
      } catch (e) {
        resolve(null);
      }
    });
  }

  function compressFile(file) {
    if (!file || !file.type || file.type.indexOf('image/') !== 0) {
      return Promise.resolve(file);
    }
    if (file.size > 0 && file.size <= SKIP_UNDER_BYTES) {
      return Promise.resolve(file);
    }

    return loadImage(file).then(function (img) {
      var w = img.naturalWidth || img.width;
      var h = img.naturalHeight || img.height;
      if (!w || !h) return file;

      var scale = Math.min(1, MAX_EDGE / Math.max(w, h));
      var tw = Math.max(1, Math.round(w * scale));
      var th = Math.max(1, Math.round(h * scale));

      var canvas = document.createElement('canvas');
      canvas.width = tw;
      canvas.height = th;
      var ctx = canvas.getContext('2d');
      if (!ctx) return file;
      ctx.drawImage(img, 0, 0, tw, th);

      var outType = 'image/jpeg';
      if (
        typeof canvas.toBlob === 'function' &&
        (file.type === 'image/webp' ||
          (typeof HTMLCanvasElement !== 'undefined' &&
            canvas.toDataURL('image/webp').indexOf('data:image/webp') === 0))
      ) {
        outType = 'image/webp';
      }

      return canvasToBlob(canvas, outType, JPEG_QUALITY).then(function (blob) {
        if (!blob || blob.size === 0) return file;
        if (blob.size >= file.size && scale >= 1) return file;
        var base = (file.name || 'cover').replace(/\.[^.]+$/, '');
        var ext = outType === 'image/webp' ? '.webp' : '.jpg';
        return new File([blob], base + ext, {
          type: outType,
          lastModified: Date.now(),
        });
      });
    }).catch(function () {
      return file;
    });
  }

  function replaceCoverInput(input, file) {
    if (!input || !file || typeof DataTransfer === 'undefined') return false;
    try {
      var dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      return true;
    } catch (e) {
      return false;
    }
  }

  function bindForm(form) {
    if (!form || form.getAttribute('data-cover-compress')) return;
    var coverInput = form.querySelector('input[name="cover"]');
    if (!coverInput) return;

    form.setAttribute('data-cover-compress', '1');
    form.addEventListener('submit', function (e) {
      var file = coverInput.files && coverInput.files[0];
      if (!file) return;
      if (form.getAttribute('data-cover-compressing')) return;

      e.preventDefault();
      form.setAttribute('data-cover-compressing', '1');

      var submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;

      compressFile(file)
        .then(function (out) {
          if (out && out !== file) replaceCoverInput(coverInput, out);
        })
        .catch(function () {
          /* keep original file */
        })
        .then(function () {
          form.removeAttribute('data-cover-compressing');
          if (submitBtn) submitBtn.disabled = false;
          // Native submit() does not re-fire the submit listener.
          HTMLFormElement.prototype.submit.call(form);
        });
    });
  }

  function initAll() {
    document
      .querySelectorAll('form[enctype="multipart/form-data"] input[name="cover"]')
      .forEach(function (input) {
        bindForm(input.closest('form'));
      });
  }

  global.CoverUpload = { initAll: initAll, compressFile: compressFile };
})(window);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () {
    if (window.CoverUpload) window.CoverUpload.initAll();
  });
} else if (window.CoverUpload) {
  window.CoverUpload.initAll();
}
