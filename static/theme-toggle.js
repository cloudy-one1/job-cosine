/* ============================================================
   theme-toggle.js — 第二前端风格（深色 SaaS）切换器
   1) 风格切换：直接 toggle theme-dark class（免刷新），并派发 theme:changed 事件供图表重绘。
   2) 语义色切换器：仅深色（html.theme-dark）下挂载，
      在 Cyan / Pink / Gold / Purple 间切换 --accent-from/--accent-to，
      状态存 sessionStorage，全站强调色联动。
   纯前端，不依赖任何后端。
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 1. 风格切换 ---------- */
  function isDark() {
    return document.documentElement.classList.contains('theme-dark');
  }

  function updateToggleLabel() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.textContent = isDark() ? '☀ 浅色风' : '🌙 深色风';
  }

  function bindToggle() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    updateToggleLabel();
    btn.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark';
      try { localStorage.setItem('theme', next); } catch (e) {}
      // 免刷新实时切换：直接 toggle class，CSS 秒级生效
      document.documentElement.classList.toggle('theme-dark');
      updateToggleLabel();
      var nowDark = isDark();
      // 深色时挂载语义色切换器，浅色时移除
      if (nowDark) {
        mountAccentSwitcher();
      } else {
        var sw = document.getElementById('accent-switcher');
        if (sw) sw.remove();
      }
      // 通知图表页面重绘 ECharts
      window.dispatchEvent(new CustomEvent('theme:changed', { detail: { isDark: nowDark } }));
    });
  }

  /* ---------- 2. 语义色切换器（仅深色下） ---------- */
  var ACCENTS = {
    cyan:   { from: '#5DE0E6', to: '#B48CFF', label: 'Cyan' },
    pink:   { from: '#FF6EC7', to: '#B48CFF', label: 'Pink' },
    gold:   { from: '#FFB84D', to: '#FF6EC7', label: 'Gold' },
    purple: { from: '#B48CFF', to: '#5DE0E6', label: 'Purple' }
  };

  function setAccent(name) {
    var a = ACCENTS[name] || ACCENTS.cyan;
    var root = document.documentElement.style;
    root.setProperty('--accent-from', a.from);
    root.setProperty('--accent-to', a.to);
    document.querySelectorAll('[data-accent-btn]').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-accent-btn') === name);
    });
    try { sessionStorage.setItem('_theme_accent', name); } catch (e) {}
  }

  function mountAccentSwitcher() {
    if (document.getElementById('accent-switcher')) return;
    var bar = document.createElement('div');
    bar.id = 'accent-switcher';
    bar.innerHTML =
      '<span class="lbl">语义色</span>' +
      '<button data-accent-btn="cyan" style="background:#5DE0E6"></button>' +
      '<button data-accent-btn="pink" style="background:#FF6EC7"></button>' +
      '<button data-accent-btn="gold" style="background:#FFB84D"></button>' +
      '<button data-accent-btn="purple" style="background:#B48CFF"></button>';
    document.body.appendChild(bar);
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('[data-accent-btn]');
      if (b) setAccent(b.getAttribute('data-accent-btn'));
    });
    var saved = null;
    try { saved = sessionStorage.getItem('_theme_accent'); } catch (e) {}
    setAccent(saved || 'cyan');
  }

  function init() {
    bindToggle();
    if (isDark()) mountAccentSwitcher();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
