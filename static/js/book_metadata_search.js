/**
 * Live book metadata search for Add Book forms.
 * Debounced fetch → Google Books / Open Library via /api/books/search.
 * Selecting a hit fills title/author and offers the provider cover as default.
 */
(function (global) {
  'use strict';

  var DEBOUNCE_MS = 350;
  var MIN_QUERY = 2;
  var clientCache = Object.create(null);

  function debounce(fn, wait) {
    var t = null;
    return function () {
      var ctx = this;
      var args = arguments;
      if (t) clearTimeout(t);
      t = setTimeout(function () {
        t = null;
        fn.apply(ctx, args);
      }, wait);
    };
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function initForm(form, options) {
    if (!form || form.getAttribute('data-book-meta-ready')) return;
    options = options || {};

    var root = form.querySelector('[data-book-meta-search]');
    if (!root) return;

    var titleInput = form.querySelector('input[name="title"]');
    var authorInput = form.querySelector('input[name="author"]');
    var coverUrlInput = root.querySelector('[data-book-meta-cover-url]');
    var resultsEl = root.querySelector('[data-book-meta-results]');
    var statusEl = root.querySelector('[data-book-meta-status]');
    var coverInput = form.querySelector(
      options.coverInputSelector || 'input[name="cover"]'
    );
    var coverImg =
      (options.coverImgId && document.getElementById(options.coverImgId)) ||
      form.querySelector('.cover-preview-img');
    var coverPh =
      (options.coverPhId && document.getElementById(options.coverPhId)) ||
      form.querySelector('.book-cover-placeholder--preview');

    if (!titleInput || !resultsEl) return;

    form.setAttribute('data-book-meta-ready', '1');
    titleInput.setAttribute('autocomplete', 'off');
    titleInput.setAttribute('aria-autocomplete', 'list');
    titleInput.setAttribute('aria-controls', resultsEl.id || 'book-meta-results');
    if (!resultsEl.id) {
      resultsEl.id =
        'book-meta-results-' + Math.random().toString(36).slice(2, 9);
      titleInput.setAttribute('aria-controls', resultsEl.id);
    }

    var searchUrl = options.searchUrl || '/api/books/search';
    var abortCtrl = null;
    var activeIndex = -1;
    var currentHits = [];

    function setStatus(msg, isError) {
      if (!statusEl) return;
      if (!msg) {
        statusEl.hidden = true;
        statusEl.textContent = '';
        statusEl.classList.remove('is-error');
        return;
      }
      statusEl.hidden = false;
      statusEl.textContent = msg;
      statusEl.classList.toggle('is-error', !!isError);
    }

    function hideResults() {
      resultsEl.hidden = true;
      resultsEl.innerHTML = '';
      activeIndex = -1;
      currentHits = [];
      titleInput.setAttribute('aria-expanded', 'false');
    }

    function showCoverPreview(url) {
      if (!coverImg) return;
      if (!url) {
        coverImg.hidden = true;
        coverImg.removeAttribute('src');
        if (coverPh) coverPh.hidden = false;
        return;
      }
      coverImg.onload = function () {
        coverImg.hidden = false;
        if (coverPh) coverPh.hidden = true;
      };
      coverImg.onerror = function () {
        coverImg.hidden = true;
        coverImg.removeAttribute('src');
        if (coverPh) coverPh.hidden = false;
      };
      coverImg.src = url;
    }

    function clearProviderCover() {
      if (coverUrlInput) coverUrlInput.value = '';
    }

    function applyHit(hit) {
      if (!hit) return;
      titleInput.value = hit.title || '';
      if (authorInput) authorInput.value = hit.author || '';
      if (coverUrlInput) {
        coverUrlInput.value = hit.cover_url || '';
      }
      if (coverInput) {
        try {
          coverInput.value = '';
        } catch (e) {
          /* ignore */
        }
      }
      if (hit.cover_url) {
        showCoverPreview(hit.cover_url);
      }
      hideResults();
      setStatus(
        hit.cover_url
          ? 'Filled from catalog. You can edit any field or replace the cover.'
          : 'Filled from catalog. You can edit any field before saving.'
      );
      if (authorInput && !authorInput.value) {
        authorInput.focus();
      }
    }

    function renderHits(hits) {
      currentHits = hits || [];
      activeIndex = -1;
      if (!currentHits.length) {
        resultsEl.innerHTML =
          '<div class="book-meta-search__empty">No catalog matches — enter details manually.</div>';
        resultsEl.hidden = false;
        titleInput.setAttribute('aria-expanded', 'true');
        return;
      }
      var html = currentHits
        .map(function (hit, i) {
          var cover = hit.cover_url
            ? '<img class="book-meta-search__cover" src="' +
              escapeHtml(hit.cover_url) +
              '" alt="" loading="lazy" referrerpolicy="no-referrer">'
            : '<div class="book-meta-search__cover book-meta-search__cover--empty" aria-hidden="true"></div>';
          var meta = [hit.author, hit.year].filter(Boolean).join(' · ');
          return (
            '<button type="button" class="book-meta-search__item" role="option" data-index="' +
            i +
            '" id="' +
            resultsEl.id +
            '-opt-' +
            i +
            '">' +
            cover +
            '<span class="book-meta-search__text">' +
            '<span class="book-meta-search__title">' +
            escapeHtml(hit.title) +
            '</span>' +
            (meta
              ? '<span class="book-meta-search__meta">' +
                escapeHtml(meta) +
                '</span>'
              : '') +
            '</span></button>'
          );
        })
        .join('');
      resultsEl.innerHTML = html;
      resultsEl.hidden = false;
      titleInput.setAttribute('aria-expanded', 'true');
    }

    function highlight(idx) {
      var items = resultsEl.querySelectorAll('.book-meta-search__item');
      items.forEach(function (el, i) {
        el.classList.toggle('is-active', i === idx);
        if (i === idx) {
          titleInput.setAttribute('aria-activedescendant', el.id);
          el.scrollIntoView({ block: 'nearest' });
        }
      });
      activeIndex = idx;
    }

    function runSearch(query) {
      var q = (query || '').trim();
      if (q.length < MIN_QUERY) {
        hideResults();
        setStatus('');
        return;
      }
      var cacheKey = q.toLowerCase();
      if (clientCache[cacheKey]) {
        renderHits(clientCache[cacheKey]);
        setStatus('');
        return;
      }
      if (abortCtrl) {
        try {
          abortCtrl.abort();
        } catch (e) {
          /* ignore */
        }
      }
      abortCtrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      setStatus('Searching catalogs…');
      var url = searchUrl + '?q=' + encodeURIComponent(q);
      fetch(url, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal: abortCtrl ? abortCtrl.signal : undefined,
      })
        .then(function (res) {
          if (!res.ok) throw new Error('search failed');
          return res.json();
        })
        .then(function (data) {
          var hits = (data && data.results) || [];
          clientCache[cacheKey] = hits;
          renderHits(hits);
          setStatus(hits.length ? '' : '');
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;
          hideResults();
          setStatus('Catalog search unavailable — enter the book manually.', true);
        });
    }

    var debouncedSearch = debounce(function () {
      runSearch(titleInput.value);
    }, DEBOUNCE_MS);

    titleInput.addEventListener('input', function () {
      clearProviderCover();
      debouncedSearch();
    });

    titleInput.addEventListener('keydown', function (e) {
      if (resultsEl.hidden || !currentHits.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlight(Math.min(activeIndex + 1, currentHits.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlight(Math.max(activeIndex - 1, 0));
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault();
        applyHit(currentHits[activeIndex]);
      } else if (e.key === 'Escape') {
        hideResults();
      }
    });

    resultsEl.addEventListener('click', function (e) {
      var btn = e.target.closest('.book-meta-search__item');
      if (!btn) return;
      var idx = parseInt(btn.getAttribute('data-index'), 10);
      if (!isNaN(idx)) applyHit(currentHits[idx]);
    });

    document.addEventListener('click', function (e) {
      if (!form.contains(e.target)) hideResults();
    });

    if (coverInput) {
      coverInput.addEventListener('change', function () {
        if (coverInput.files && coverInput.files[0]) {
          clearProviderCover();
        }
      });
    }
  }

  function initAll(options) {
    document.querySelectorAll('form.rating-form').forEach(function (form) {
      if (form.querySelector('[data-book-meta-search]')) {
        initForm(form, options);
      }
    });
  }

  global.BookMetaSearch = { initForm: initForm, initAll: initAll };
})(window);
