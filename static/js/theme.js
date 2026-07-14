/**
 * Kwalitec Library — Theme Manager
 * Appearance: light | dark | system (default).
 * Persists to localStorage key "kwalitec-theme". No server/DB involvement.
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'kwalitec-theme';
    var VALID = { light: true, dark: true, system: true };
    var mediaQuery = null;
    var charts = [];

    function readPreference() {
        try {
            var stored = localStorage.getItem(STORAGE_KEY);
            if (stored && VALID[stored]) return stored;
        } catch (e) { /* private mode */ }
        return 'system';
    }

    function writePreference(pref) {
        try {
            localStorage.setItem(STORAGE_KEY, pref);
        } catch (e) { /* private mode */ }
    }

    function systemIsDark() {
        return !!(global.matchMedia && global.matchMedia('(prefers-color-scheme: dark)').matches);
    }

    function resolveTheme(pref) {
        if (pref === 'dark') return 'dark';
        if (pref === 'light') return 'light';
        return systemIsDark() ? 'dark' : 'light';
    }

    function applyResolved(resolved) {
        var root = document.documentElement;
        root.setAttribute('data-theme', resolved);
        root.style.colorScheme = resolved;
    }

    function dispatchChange(pref, resolved) {
        try {
            document.dispatchEvent(new CustomEvent('kwalitec:themechange', {
                detail: { preference: pref, theme: resolved }
            }));
        } catch (e) { /* older browsers */ }
        refreshCharts();
        syncControls(pref);
        updateNavThemeToggle(pref);
    }

    function setPreference(pref) {
        if (!VALID[pref]) pref = 'system';
        writePreference(pref);
        var resolved = resolveTheme(pref);
        applyResolved(resolved);
        document.documentElement.setAttribute('data-theme-pref', pref);
        dispatchChange(pref, resolved);
        return resolved;
    }

    function getPreference() {
        return document.documentElement.getAttribute('data-theme-pref') || readPreference();
    }

    function getTheme() {
        return document.documentElement.getAttribute('data-theme') || resolveTheme(getPreference());
    }

    function cssVar(name, fallback) {
        var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback || '';
    }

    function getChartColors() {
        return {
            primary: cssVar('--color-primary', '#5B54E8'),
            primarySoft: cssVar('--color-primary-soft', 'rgba(91, 84, 232, 0.15)'),
            success: cssVar('--color-success', '#16A34A'),
            successSoft: cssVar('--color-success-soft', 'rgba(22, 163, 74, 0.15)'),
            warning: cssVar('--color-warning', '#D97706'),
            warningSoft: cssVar('--color-warning-soft', 'rgba(217, 119, 6, 0.18)'),
            danger: cssVar('--color-danger', '#DC2626'),
            text: cssVar('--chart-text', cssVar('--color-text-muted', '#52525B')),
            grid: cssVar('--chart-grid', 'rgba(0, 0, 0, 0.07)'),
            surface: cssVar('--color-surface', '#FAFAF9'),
            background: cssVar('--color-background', '#EDEEEF'),
            border: cssVar('--color-border', '#D4D4D8')
        };
    }

    function applyChartDefaults() {
        if (typeof global.Chart === 'undefined') return;
        var c = getChartColors();
        Chart.defaults.color = c.text;
        Chart.defaults.borderColor = c.grid;
        if (Chart.defaults.plugins && Chart.defaults.plugins.tooltip) {
            Chart.defaults.plugins.tooltip.backgroundColor = c.surface;
            Chart.defaults.plugins.tooltip.titleColor = cssVar('--color-text', '#0A0A0A');
            Chart.defaults.plugins.tooltip.bodyColor = c.text;
            Chart.defaults.plugins.tooltip.borderColor = c.border;
            Chart.defaults.plugins.tooltip.borderWidth = 1;
        }
    }

    function registerChart(chart) {
        if (chart && charts.indexOf(chart) === -1) charts.push(chart);
        return chart;
    }

    function refreshCharts() {
        applyChartDefaults();
        var c = getChartColors();
        charts = charts.filter(function (chart) {
            if (!chart || typeof chart.destroy !== 'function') return false;
            try {
                if (chart.options && chart.options.scales) {
                    Object.keys(chart.options.scales).forEach(function (axis) {
                        var scale = chart.options.scales[axis];
                        if (scale && scale.grid) scale.grid.color = c.grid;
                        if (scale && scale.ticks) scale.ticks.color = c.text;
                    });
                }
                if (chart.data && chart.data.datasets) {
                    chart.data.datasets.forEach(function (ds) {
                        if (ds._kwTheme === 'primary') {
                            ds.borderColor = c.primary;
                            ds.backgroundColor = c.primarySoft;
                            if (ds.pointBackgroundColor) ds.pointBackgroundColor = c.primary;
                        } else if (ds._kwTheme === 'success') {
                            ds.borderColor = c.success;
                            ds.backgroundColor = c.successSoft;
                            if (ds.pointBackgroundColor) ds.pointBackgroundColor = c.success;
                        } else if (ds._kwTheme === 'warning') {
                            ds.borderColor = c.warning;
                            ds.backgroundColor = c.warningSoft;
                        }
                    });
                }
                Chart.defaults.color = c.text;
                chart.update('none');
                return true;
            } catch (e) {
                return false;
            }
        });
    }

    function syncControls(pref) {
        pref = pref || getPreference();
        var nodes = document.querySelectorAll('[data-theme-option]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var value = el.getAttribute('data-theme-option');
            if (el.type === 'radio') {
                el.checked = value === pref;
            } else {
                el.classList.toggle('is-active', value === pref);
                el.setAttribute('aria-checked', value === pref ? 'true' : 'false');
            }
        }
    }

    function onSystemChange() {
        if (getPreference() !== 'system') return;
        var resolved = resolveTheme('system');
        applyResolved(resolved);
        dispatchChange('system', resolved);
    }

    var CYCLE_ORDER = ['light', 'dark', 'system'];
    var CYCLE_LABELS = { light: 'Light', dark: 'Dark', system: 'System' };

    function updateNavThemeToggle(pref) {
        var btn = document.getElementById('navThemeToggle');
        if (!btn) return;
        var label = btn.querySelector('.theme-label');
        if (label) label.textContent = CYCLE_LABELS[pref] || '';
        btn.setAttribute('data-current-pref', pref || 'system');
        btn.setAttribute('title', 'Theme: ' + (CYCLE_LABELS[pref] || 'System') + ' — click to cycle');
    }

    function bindNavThemeToggle() {
        var btn = document.getElementById('navThemeToggle');
        if (!btn || btn._kwThemeBound) return;
        btn._kwThemeBound = true;
        btn.addEventListener('click', function () {
            var current = getPreference();
            var idx = CYCLE_ORDER.indexOf(current);
            var next = CYCLE_ORDER[(idx + 1) % CYCLE_ORDER.length];
            setPreference(next);
        });
        updateNavThemeToggle(getPreference());
    }

    function bindControls(root) {
        root = root || document;
        var nodes = root.querySelectorAll('[data-theme-option]');
        for (var i = 0; i < nodes.length; i++) {
            (function (el) {
                if (el._kwThemeBound) return;
                el._kwThemeBound = true;
                el.addEventListener('change', function () {
                    if (el.type === 'radio' && el.checked) {
                        setPreference(el.getAttribute('data-theme-option'));
                    }
                });
                el.addEventListener('click', function () {
                    if (el.type !== 'radio') {
                        setPreference(el.getAttribute('data-theme-option'));
                    }
                });
            })(nodes[i]);
        }
        bindNavThemeToggle();
        syncControls();
    }

    function init() {
        var pref = readPreference();
        document.documentElement.setAttribute('data-theme-pref', pref);
        applyResolved(resolveTheme(pref));

        if (global.matchMedia) {
            mediaQuery = global.matchMedia('(prefers-color-scheme: dark)');
            if (mediaQuery.addEventListener) {
                mediaQuery.addEventListener('change', onSystemChange);
            } else if (mediaQuery.addListener) {
                mediaQuery.addListener(onSystemChange);
            }
        }

        applyChartDefaults();
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () { bindControls(); });
        } else {
            bindControls();
        }
    }

    var ThemeManager = {
        STORAGE_KEY: STORAGE_KEY,
        init: init,
        setPreference: setPreference,
        getPreference: getPreference,
        getTheme: getTheme,
        resolveTheme: resolveTheme,
        getChartColors: getChartColors,
        applyChartDefaults: applyChartDefaults,
        registerChart: registerChart,
        refreshCharts: refreshCharts,
        bindControls: bindControls,
        syncControls: syncControls
    };

    global.KwalitecTheme = ThemeManager;
    init();
})(typeof window !== 'undefined' ? window : this);
