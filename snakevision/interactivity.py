"""JavaScript interactivity helpers for snakevision.

This module contains functions to generate the JavaScript code needed for
interactive SVG output in snakevision. This includes play/pause/reset controls,
hover effects, and click-to-show metadata popups.
"""

def javascript(payload: str) -> str:
    """Return the self-contained JavaScript used by interactive SVG output.

    The Python side computes layout-specific constants and serializes them into
    `payload`. The JavaScript uses those constants to build controls and hover
    layers at runtime. Building interactive elements in JS keeps the generated
    SVG smaller and ensures those elements appear above the original rendered
    DAG in SVG stacking order.
    """
    return r"""
(function () {
  'use strict';

  var CFG = __PAYLOAD__;
  var svg = document.documentElement;
  var NS = 'http://www.w3.org/2000/svg';
  var NODES = CFG.graph.nodes;
  var EDGES = CFG.graph.edges;
  var HAS_RULE_METADATA = !!CFG.hasRuleMetadata;

  var reducedMotion = (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );

  var paused = true;

  var playIcon = null;
  var pauseIcon = null;
  var hlLayer = null;
  var hlEdgePaths = [];
  var hlNodeRings = {};
  var nodeCircleEls = {};
  var origEdgeEls = [];
  var ancestorMap = {};
  var directParentMap = {};

  var rulePanel = null;
  var rulePanelBg = null;
  var rulePanelTitle = null;
  var rulePanelBody = null;

  function packetLayer() {
    return document.getElementById('packet-animation-layer');
  }

  function setPacketsVisible(visible) {
    var layer = packetLayer();
    if (layer) {
      layer.setAttribute('visibility', visible ? 'visible' : 'hidden');
    }
  }

  function setPaused(nextPaused) {
    paused = nextPaused;

    if (!paused && !reducedMotion) {
      setPacketsVisible(true);
    }

    if (paused || reducedMotion) {
      if (typeof svg.pauseAnimations === 'function') svg.pauseAnimations();
    } else {
      if (typeof svg.unpauseAnimations === 'function') svg.unpauseAnimations();
    }

    var btn = document.getElementById('play-pause-btn');

    if (playIcon && pauseIcon) {
      playIcon.setAttribute('display', paused ? '' : 'none');
      pauseIcon.setAttribute('display', paused ? 'none' : '');
    }

    if (btn) {
      btn.setAttribute('aria-label', paused ? 'Play animation' : 'Pause animation');
    }
  }

  function togglePlayPause() {
    if (reducedMotion) return;
    setPaused(!paused);
  }

  function resetPackets() {
    /*
     * Reset means "clear the visible packets and return animation time to the
     * beginning". We also pause so users can restart intentionally.
     */
    setPaused(true);

    if (typeof svg.setCurrentTime === 'function') {
      try {
        svg.setCurrentTime(0);
      } catch (_err) {
        /* Some SVG hosts may not support setting current time. */
      }
    }

    setPacketsVisible(false);
  }

  function buildPlayPauseButton() {
    var cx = CFG.btnCx, cy = CFG.btnCy, r = CFG.btnR;

    var btn = document.createElementNS(NS, 'g');
    btn.setAttribute('id', 'play-pause-btn');
    btn.setAttribute('role', 'button');
    btn.setAttribute('aria-label', 'Play animation');
    btn.setAttribute('tabindex', '0');

    var bg = document.createElementNS(NS, 'circle');
    bg.setAttribute('id', 'btn-bg');
    bg.setAttribute('cx', String(cx));
    bg.setAttribute('cy', String(cy));
    bg.setAttribute('r', String(r));
    bg.setAttribute('fill', '#222');
    bg.setAttribute('opacity', '0.72');
    btn.appendChild(bg);

    var s = r * 0.42;

    playIcon = document.createElementNS(NS, 'polygon');
    playIcon.setAttribute(
      'points',
      (cx - s * 0.6) + ',' + (cy - s) + ' ' +
      (cx + s) + ',' + cy + ' ' +
      (cx - s * 0.6) + ',' + (cy + s)
    );
    playIcon.setAttribute('fill', 'white');
    btn.appendChild(playIcon);

    pauseIcon = document.createElementNS(NS, 'g');
    pauseIcon.setAttribute('display', 'none');

    var bw = r * 0.22, bh = r * 0.50, gap = r * 0.18;

    var leftBar = document.createElementNS(NS, 'rect');
    leftBar.setAttribute('x', String(cx - gap - bw));
    leftBar.setAttribute('y', String(cy - bh));
    leftBar.setAttribute('width', String(bw));
    leftBar.setAttribute('height', String(bh * 2));
    leftBar.setAttribute('fill', 'white');
    pauseIcon.appendChild(leftBar);

    var rightBar = document.createElementNS(NS, 'rect');
    rightBar.setAttribute('x', String(cx + gap));
    rightBar.setAttribute('y', String(cy - bh));
    rightBar.setAttribute('width', String(bw));
    rightBar.setAttribute('height', String(bh * 2));
    rightBar.setAttribute('fill', 'white');
    pauseIcon.appendChild(rightBar);

    btn.appendChild(pauseIcon);

    btn.addEventListener('click', togglePlayPause);
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        togglePlayPause();
      }
    });

    svg.appendChild(btn);
  }

  function buildResetButton() {
    var x = CFG.resetBtnX;
    var y = CFG.resetBtnY;
    var w = CFG.resetBtnW;
    var h = CFG.resetBtnH;

    var btn = document.createElementNS(NS, 'g');
    btn.setAttribute('id', 'reset-packets-btn');
    btn.setAttribute('role', 'button');
    btn.setAttribute('aria-label', 'Reset and clear visible packets');
    btn.setAttribute('tabindex', '0');

    var bg = document.createElementNS(NS, 'rect');
    bg.setAttribute('id', 'reset-btn-bg');
    bg.setAttribute('x', String(x));
    bg.setAttribute('y', String(y));
    bg.setAttribute('width', String(w));
    bg.setAttribute('height', String(h));
    bg.setAttribute('rx', '5');
    bg.setAttribute('ry', '5');
    bg.setAttribute('fill', '#222');
    bg.setAttribute('opacity', '0.72');
    btn.appendChild(bg);

    var label = document.createElementNS(NS, 'text');
    label.setAttribute('x', String(x + w / 2));
    label.setAttribute('y', String(y + h / 2 + 2.2));
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-family', 'sans-serif');
    label.setAttribute('font-size', '6');
    label.setAttribute('font-weight', 'bold');
    label.setAttribute('fill', 'white');
    label.textContent = 'reset';
    btn.appendChild(label);

    btn.addEventListener('click', resetPackets);
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        resetPackets();
      }
    });

    svg.appendChild(btn);
  }

  function buildAncestorMap() {
    var map = {};
    Object.keys(NODES).forEach(function (nid) { map[nid] = {}; });

    Object.keys(NODES).forEach(function (nid) {
      var visited = {};
      var queue = [nid];
      visited[nid] = true;

      while (queue.length) {
        var curr = queue.shift();

        EDGES.forEach(function (edge) {
          if (edge.to === curr && !visited[edge.from]) {
            visited[edge.from] = true;
            map[nid][edge.from] = true;
            queue.push(edge.from);
          }
        });
      }
    });

    return map;
  }

  function buildDirectParentMap() {
    var map = {};
    Object.keys(NODES).forEach(function (nid) { map[nid] = {}; });

    EDGES.forEach(function (edge) {
      map[edge.to][edge.from] = true;
    });

    return map;
  }

  function buildHighlightLayer() {
    var packetLayerEl = packetLayer();

    ancestorMap = buildAncestorMap();
    directParentMap = buildDirectParentMap();

    hlLayer = document.createElementNS(NS, 'g');
    hlLayer.setAttribute('id', 'highlight-layer');
    hlLayer.setAttribute('class', 'highlight-layer');

    if (packetLayerEl) svg.insertBefore(hlLayer, packetLayerEl);
    else svg.appendChild(hlLayer);

    EDGES.forEach(function (edge, idx) {
      var srcColor = NODES[edge.from].color || '#ffffff';

      var path = document.createElementNS(NS, 'path');
      path.setAttribute('class', 'hl-edge');
      path.setAttribute('d', edge.path);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', srcColor);
      path.setAttribute('stroke-width', '4');
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('opacity', '0');

      hlLayer.appendChild(path);
      hlEdgePaths[idx] = path;
    });

    Object.keys(NODES).forEach(function (nid) {
      var node = NODES[nid];

      var ring = document.createElementNS(NS, 'circle');
      ring.setAttribute('class', 'hl-ring');
      ring.setAttribute('cx', String(node.x));
      ring.setAttribute('cy', String(node.y));
      ring.setAttribute('r', String((node.r || 6) + 2.25));
      ring.setAttribute('fill', 'none');
      ring.setAttribute('stroke', node.color || '#ffffff');
      ring.setAttribute('stroke-width', '2.75');
      ring.setAttribute('opacity', '0');

      hlLayer.appendChild(ring);
      hlNodeRings[nid] = ring;
    });

    svg.querySelectorAll('line, path').forEach(function (el) {
      if (el.closest('#highlight-layer') || el.closest('#packet-animation-layer')) return;

      var stroke = (el.getAttribute('stroke') || '').toLowerCase();
      if (!stroke || stroke === 'none' || stroke === 'white' || stroke === '#ffffff') return;

      var dash = (el.getAttribute('stroke-dasharray') || '').trim();
      if (dash && dash !== 'none' && dash !== '0') return;

      origEdgeEls.push(el);
      el.setAttribute('class', (el.getAttribute('class') || '') + ' dag-orig-edge');
    });

    var nodesAbove = document.createElementNS(NS, 'g');
    nodesAbove.setAttribute('id', 'nodes-above-layer');

    if (packetLayerEl) svg.insertBefore(nodesAbove, packetLayerEl);
    else svg.appendChild(nodesAbove);

    var circleEls = [];

    svg.querySelectorAll('circle[id]').forEach(function (el) {
      var nid = el.getAttribute('id');
      if (!NODES[nid]) return;
      circleEls.push({ el: el, nid: nid });
    });

    circleEls.forEach(function (item) {
      var el = item.el;
      var nid = item.nid;
      var sibling = el.nextElementSibling;

      el.setAttribute('class', 'dag-node-circle');
      el.style.cursor = 'pointer';
      nodeCircleEls[nid] = el;

      el.addEventListener('mouseenter', function () { onNodeHover(nid); });
      el.addEventListener('mouseleave', onNodeUnhover);

      if (HAS_RULE_METADATA) {
        el.addEventListener('click', function (e) {
          e.stopPropagation();
          showRulePanel(nid);
        });
      }

      nodesAbove.appendChild(el);

      if (sibling && sibling.tagName && sibling.tagName.toLowerCase() === 'text') {
        nodesAbove.appendChild(sibling);
      }
    });
  }

  function onNodeHover(hoveredId) {
    var ancestors = ancestorMap[hoveredId] || {};
    var directParents = directParentMap[hoveredId] || {};
    var relevant = Object.assign({}, ancestors);
    relevant[hoveredId] = true;

    EDGES.forEach(function (edge, idx) {
      var on = relevant[edge.from] && relevant[edge.to];
      hlEdgePaths[idx].setAttribute('opacity', on ? '0.9' : '0');
    });

    Object.keys(NODES).forEach(function (nid) {
      hlNodeRings[nid].setAttribute('opacity', directParents[nid] ? '1' : '0');
    });

    origEdgeEls.forEach(function (el) {
      el.setAttribute('opacity', '0.06');
    });

    Object.keys(nodeCircleEls).forEach(function (nid) {
      nodeCircleEls[nid].setAttribute('opacity', relevant[nid] ? '1' : '0.2');
    });
  }

  function onNodeUnhover() {
    EDGES.forEach(function (_edge, idx) {
      hlEdgePaths[idx].setAttribute('opacity', '0');
    });

    Object.keys(NODES).forEach(function (nid) {
      hlNodeRings[nid].setAttribute('opacity', '0');
    });

    Object.keys(nodeCircleEls).forEach(function (nid) {
      nodeCircleEls[nid].setAttribute('opacity', '1');
    });

    origEdgeEls.forEach(function (el) {
      el.setAttribute('opacity', '1');
    });
  }

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function wrapRuleText(text, maxChars) {
    var output = [];

    String(text || '').replace(/\t/g, '    ').split(/\r?\n/).forEach(function (line) {
      if (line.length <= maxChars) {
        output.push(line);
        return;
      }

      var indentMatch = line.match(/^\s*/);
      var indent = indentMatch ? indentMatch[0] : '';
      var remaining = line;

      while (remaining.length > maxChars) {
        var cut = remaining.lastIndexOf(' ', maxChars);
        if (cut <= Math.max(8, indent.length)) cut = maxChars;

        output.push(remaining.slice(0, cut));
        remaining = indent + '  ' + remaining.slice(cut).trimStart();
      }

      output.push(remaining);
    });

    return output;
  }

  function buildRulePanel() {
    if (!HAS_RULE_METADATA) return;

    rulePanel = document.createElementNS(NS, 'g');
    rulePanel.setAttribute('id', 'rule-info-panel');
    rulePanel.setAttribute('display', 'none');

    rulePanelBg = document.createElementNS(NS, 'rect');
    rulePanelBg.setAttribute('id', 'rule-info-panel-bg');
    rulePanelBg.setAttribute('x', String(CFG.panelX));
    rulePanelBg.setAttribute('y', String(CFG.panelY));
    rulePanelBg.setAttribute('width', String(CFG.panelW));
    rulePanelBg.setAttribute('height', '80');
    rulePanelBg.setAttribute('rx', '4');
    rulePanelBg.setAttribute('ry', '4');
    rulePanel.appendChild(rulePanelBg);

    rulePanelTitle = document.createElementNS(NS, 'text');
    rulePanelTitle.setAttribute('id', 'rule-info-panel-title');
    rulePanelTitle.setAttribute('x', String(CFG.panelX + 8));
    rulePanelTitle.setAttribute('y', String(CFG.panelY + 13));
    rulePanelTitle.setAttribute('font-size', '6');
    rulePanel.appendChild(rulePanelTitle);

    var close = document.createElementNS(NS, 'text');
    close.setAttribute('id', 'rule-info-panel-close');
    close.setAttribute('x', String(CFG.panelX + CFG.panelW - 12));
    close.setAttribute('y', String(CFG.panelY + 13));
    close.setAttribute('font-size', '8');
    close.textContent = '×';
    close.addEventListener('click', function (e) {
      e.stopPropagation();
      hideRulePanel();
    });
    rulePanel.appendChild(close);

    var divider = document.createElementNS(NS, 'line');
    divider.setAttribute('x1', String(CFG.panelX));
    divider.setAttribute('x2', String(CFG.panelX + CFG.panelW));
    divider.setAttribute('y1', String(CFG.panelY + 20));
    divider.setAttribute('y2', String(CFG.panelY + 20));
    divider.setAttribute('stroke', '#555');
    divider.setAttribute('stroke-width', '0.6');
    rulePanel.appendChild(divider);

    rulePanelBody = document.createElementNS(NS, 'text');
    rulePanelBody.setAttribute('id', 'rule-info-panel-body');
    rulePanelBody.setAttribute('x', String(CFG.panelX + 8));
    rulePanelBody.setAttribute('y', String(CFG.panelY + 30));
    rulePanelBody.setAttribute('font-size', '5');
    rulePanelBody.setAttribute('xml:space', 'preserve');
    rulePanel.appendChild(rulePanelBody);

    svg.appendChild(rulePanel);

    svg.addEventListener('click', function () {
      hideRulePanel();
    });

    rulePanel.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') hideRulePanel();
    });
  }

  function showRulePanel(nodeId) {
    if (!HAS_RULE_METADATA || !rulePanel) return;

    var node = NODES[nodeId] || {};
    var label = node.label || nodeId;
    var body = (typeof node.ruleText === 'string')
      ? node.ruleText
      : 'No rule metadata provided for this node.';

    rulePanelTitle.textContent = label;
    clearChildren(rulePanelBody);

    var maxChars = Math.max(24, Math.floor((CFG.panelW - 18) / 3.1));
    var lines = wrapRuleText(body, maxChars);
    var maxLines = Math.max(1, Math.floor((CFG.panelMaxH - 36) / 6));
    var truncated = false;

    if (lines.length > maxLines) {
      lines = lines.slice(0, maxLines - 1);
      lines.push('…');
      truncated = true;
    }

    lines.forEach(function (line, idx) {
      var tspan = document.createElementNS(NS, 'tspan');
      tspan.setAttribute('x', String(CFG.panelX + 8));
      tspan.setAttribute('dy', idx === 0 ? '0' : '6');
      tspan.textContent = line;
      rulePanelBody.appendChild(tspan);
    });

    var panelH = Math.min(CFG.panelMaxH, 38 + lines.length * 6);
    if (truncated) panelH = Math.min(CFG.panelMaxH, panelH + 2);

    rulePanelBg.setAttribute('height', String(panelH));
    rulePanel.setAttribute('display', '');
  }

  function hideRulePanel() {
    if (rulePanel) rulePanel.setAttribute('display', 'none');
  }

  function addReducedMotionLabel() {
    var label = document.createElementNS(NS, 'text');
    label.setAttribute('x', String(CFG.btnCx));
    label.setAttribute('y', String(CFG.btnCy + CFG.btnR + 8));
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-family', 'sans-serif');
    label.setAttribute('font-size', '6');
    label.setAttribute('fill', '#888');
    label.textContent = 'motion off';
    svg.appendChild(label);
  }

  function init() {
    buildHighlightLayer();
    buildRulePanel();
    buildResetButton();
    buildPlayPauseButton();

    /*
     * Start paused in interactive mode. We do not hide packets initially;
     * pausing at t=0 keeps the initial animation frame available. The reset
     * button explicitly hides currently visible packets.
     */
    setPaused(true);

    if (reducedMotion) {
      addReducedMotionLabel();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
""".replace("__PAYLOAD__", payload)
