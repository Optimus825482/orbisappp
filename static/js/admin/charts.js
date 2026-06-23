/**
 * ORBIS Admin — Vanilla SVG charts
 * Sparkline · Area+Line chart · Bar chart
 * Theme-aware (re-renders on theme change).
 *
 * API:
 *   window.OrbisCharts.sparkline(el, values, { color })
 *   window.OrbisCharts.lineChart(el, series, { xLabels, height })
 *   window.OrbisCharts.barChart(el, bars, { xLabels, height })
 */
(function () {
  'use strict';

  var root = document.documentElement;

  function themeColor(name) {
    return getComputedStyle(root).getPropertyValue('--' + name).trim();
  }
  function color(name) {
    return themeColor(name);
  }

  function fmt(n) {
    if (n === null || n === undefined) return '';
    var abs = Math.abs(n);
    if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (abs >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return String(Math.round(n));
  }

  // ─── Sparkline ────────────────────────────────────────
  function sparkline(el, values, opts) {
    if (!el || !values || !values.length) return;
    opts = opts || {};
    var w = el.clientWidth || 200;
    var h = opts.height || 36;
    var stroke = opts.color || color('primary');
    var fillColor = stroke;

    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var range = max - min || 1;
    var stepX = w / (values.length - 1 || 1);

    var pts = values.map(function (v, i) {
      var x = i * stepX;
      var y = h - ((v - min) / range) * (h - 4) - 2;
      return [x, y];
    });

    var pathD = pts.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
    var areaD = pathD + ' L' + w + ',' + h + ' L0,' + h + ' Z';
    var last = pts[pts.length - 1];

    el.innerHTML =
      '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" width="100%" height="' + h + '" aria-hidden="true">' +
        '<defs><linearGradient id="spark-' + el.id + '" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0%" stop-color="' + fillColor + '" stop-opacity="0.18"/>' +
          '<stop offset="100%" stop-color="' + fillColor + '" stop-opacity="0"/>' +
        '</linearGradient></defs>' +
        '<path d="' + areaD + '" fill="url(#spark-' + el.id + ')"/>' +
        '<path d="' + pathD + '" fill="none" stroke="' + stroke + '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>' +
        '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="2.5" fill="' + stroke + '" stroke="' + color('bg') + '" stroke-width="1.5"/>' +
      '</svg>';
  }

  // ─── Line / Area chart ────────────────────────────────
  function lineChart(el, series, opts) {
    if (!el) return;
    opts = opts || {};
    var w = el.clientWidth || 600;
    var h = opts.height || 240;
    var padding = { top: 16, right: 16, bottom: 28, left: 44 };
    var xLabels = opts.xLabels || [];

    var allValues = series.reduce(function (acc, s) { return acc.concat(s.values); }, []);
    var minY = Math.min.apply(null, allValues);
    var maxY = Math.max.apply(null, allValues);
    if (minY === maxY) { minY -= 1; maxY += 1; }
    var yRange = maxY - minY;

    function xPos(i) {
      return padding.left + (i / (xLabels.length - 1 || 1)) * (w - padding.left - padding.right);
    }
    function yPos(v) {
      return padding.top + (1 - (v - minY) / yRange) * (h - padding.top - padding.bottom);
    }

    // Y grid lines (4)
    var yTicks = [];
    for (var t = 0; t < 4; t++) {
      yTicks.push(minY + yRange * (t / 3));
    }
    var yGrid = yTicks.map(function (v) {
      return '<line x1="' + padding.left + '" x2="' + (w - padding.right) + '" y1="' + yPos(v) + '" y2="' + yPos(v) + '" class="chart-grid-line"/>' +
             '<text x="' + (padding.left - 8) + '" y="' + (yPos(v) + 3) + '" text-anchor="end" class="chart-axis-text">' + fmt(v) + '</text>';
    }).join('');

    // X labels (sparse — first, mid, last)
    var xStep = Math.max(1, Math.floor(xLabels.length / 5));
    var xText = xLabels.map(function (lbl, i) {
      if (i !== 0 && i !== xLabels.length - 1 && i % xStep !== 0) return '';
      return '<text x="' + xPos(i) + '" y="' + (h - 8) + '" text-anchor="middle" class="chart-axis-text">' + lbl + '</text>';
    }).join('');

    // Series paths
    var seriesSvg = series.map(function (s) {
      var c = color(s.color) || color('primary');
      var pts = s.values.map(function (v, i) { return [xPos(i), yPos(v)]; });
      var path = pts.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
      var area = path + ' L' + pts[pts.length - 1][0] + ',' + (h - padding.bottom) + ' L' + pts[0][0] + ',' + (h - padding.bottom) + ' Z';
      var last = pts[pts.length - 1];
      return '<path d="' + area + '" fill="' + c + '" fill-opacity="0.10"/>' +
             '<path d="' + path + '" fill="none" stroke="' + c + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
             '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="3" fill="' + c + '" stroke="' + color('bg') + '" stroke-width="2"/>';
    }).join('');

    el.innerHTML =
      '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" width="100%" height="' + h + '" role="img" aria-label="' + (opts.label || 'Grafik') + '">' +
        yGrid + seriesSvg + xText +
      '</svg>';
  }

  // ─── Bar chart (horizontal) ──────────────────────────
  function barChart(el, bars, opts) {
    if (!el) return;
    opts = opts || {};
    var w = el.clientWidth || 600;
    var h = opts.height || 240;
    var padding = { top: 12, right: 16, bottom: 28, left: 140 };
    var maxVal = Math.max.apply(null, bars.map(function (b) { return b.value; }));
    if (maxVal === 0) maxVal = 1;
    var rowH = (h - padding.top - padding.bottom) / (bars.length || 1);

    var labelText = bars.map(function (b, i) {
      var y = padding.top + i * rowH + rowH / 2;
      return '<text x="' + (padding.left - 8) + '" y="' + (y + 3) + '" text-anchor="end" class="chart-axis-text">' + (b.label || '') + '</text>';
    }).join('');

    var barsSvg = bars.map(function (b, i) {
      var y = padding.top + i * rowH + rowH * 0.2;
      var barH = rowH * 0.6;
      var barW = (b.value / maxVal) * (w - padding.left - padding.right);
      var c = color(b.color) || color('primary');
      return '<rect x="' + padding.left + '" y="' + y + '" width="' + Math.max(barW, 1) + '" height="' + barH + '" fill="' + c + '" rx="3"/>' +
             '<text x="' + (padding.left + barW + 6) + '" y="' + (y + barH / 2 + 3) + '" class="chart-axis-text">' + fmt(b.value) + '</text>';
    }).join('');

    el.innerHTML =
      '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" width="100%" height="' + h + '" role="img" aria-label="' + (opts.label || 'Bar grafiği') + '">' +
        labelText + barsSvg +
      '</svg>';
  }

  // ─── Re-render on theme change ───────────────────────
  // ÖNEMLİ: themechange listener sadece data-chart-original attribute'u olan
  // elemanları render eder. Sayfa JS'i sonradan data-chart'i override etmişse,
  // o elemanı tekrar çizme (live API call'ı içeriğini ezerdik).
  document.addEventListener('orbis:themechange', function () {
    var els = document.querySelectorAll('[data-chart-original]');
    els.forEach(function (el) {
      try {
        var data = JSON.parse(el.getAttribute('data-chart-original'));
        if (data.type === 'sparkline') sparkline(el, data.values, data.opts);
        else if (data.type === 'line') lineChart(el, data.series, data.opts);
        else if (data.type === 'bar') barChart(el, data.bars, data.opts);
      } catch (e) {}
    });
  });

  // ─── Initial render: data-chart attribute'u olan tüm elemanları çiz ─
  // (data-chart-original'a kopyala ki themechange ezmesin)
  function initialRender() {
    var els = document.querySelectorAll('[data-chart]');
    els.forEach(function (el) {
      try {
        var data = JSON.parse(el.getAttribute('data-chart'));
        el.setAttribute('data-chart-original', el.getAttribute('data-chart'));
        if (data.type === 'sparkline') sparkline(el, data.values, data.opts);
        else if (data.type === 'line') lineChart(el, data.series, data.opts);
        else if (data.type === 'bar') barChart(el, data.bars, data.opts);
      } catch (e) {}
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialRender);
  } else {
    initialRender();
  }

  // ─── Public API ──────────────────────────────────────
  window.OrbisCharts = {
    sparkline: sparkline,
    line: lineChart,        // alias
    lineChart: lineChart,
    bar: barChart,          // alias
    barChart: barChart
  };

  // Reduced motion → no animation on chart entry
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.classList.add('reduce-motion');
  }
})();
