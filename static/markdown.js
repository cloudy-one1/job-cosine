// static/markdown.js
// 轻量、零依赖、XSS 安全的 Markdown → HTML 渲染器（覆盖本项目用到的子集：
// #/##/### 标题、**粗体**、*斜体*、`代码`、-/* 无序列表、1. 有序列表、空行分段）。
// 用法：给任意容器加 data-md 属性，本脚本在 DOMContentLoaded 时自动把其
// textContent（已由浏览器还原 Jinja 转义）安全渲染为带样式的 HTML。
(function () {
  'use strict';

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function inline(t) {
    return t
      .replace(/`([^`]+?)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>');
  }

  function renderMarkdown(src) {
    if (!src) return '';
    var text = escapeHtml(src);
    var lines = text.split(/\r?\n/);
    var html = '';
    var listType = null; // 'ul' | 'ol' | null

    function closeList() {
      if (listType) { html += '</' + listType + '>'; listType = null; }
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];

      // 标题 # / ## / ###
      var h = line.match(/^(#{1,3})\s+(.*)$/);
      if (h) {
        closeList();
        var lvl = h[1].length;
        html += '<h' + lvl + ' class="md-h md-h' + lvl + '">' + inline(h[2]) + '</h' + lvl + '>';
        continue;
      }

      // 无序列表 - / *
      var ul = line.match(/^\s*[-*]\s+(.*)$/);
      if (ul) {
        if (listType !== 'ul') { closeList(); html += '<ul class="md-ul">'; listType = 'ul'; }
        html += '<li>' + inline(ul[1]) + '</li>';
        continue;
      }

      // 有序列表 1.
      var ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        if (listType !== 'ol') { closeList(); html += '<ol class="md-ol">'; listType = 'ol'; }
        html += '<li>' + inline(ol[1]) + '</li>';
        continue;
      }

      // 空行：段落/列表分隔
      if (line.trim() === '') { closeList(); continue; }

      // 普通段落
      closeList();
      html += '<p class="md-p">' + inline(line) + '</p>';
    }
    closeList();
    return html;
  }

  function renderAll() {
    var nodes = document.querySelectorAll('[data-md]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.__mdRendered) continue;
      // textContent 已还原 Jinja 转义，renderMarkdown 内二次转义保证 XSS 安全
      el.innerHTML = renderMarkdown(el.textContent);
      el.__mdRendered = true;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll);
  } else {
    renderAll();
  }

  window.renderMarkdown = renderMarkdown;
})();
