/**
 * sidebar.js — Trip Progress Sidebar
 * IIFE module for displaying trip planning progress as a node-based sidebar.
 */

const Sidebar = (() => {
  // Module-level state
  let _nodes = [];
  const _imageCache = new Map();
  let _overlay = null;
  let _renderedIds = new Set();

  // ─── Phase Detection ───────────────────────────────────────────────────────

  function _detectPhase() {
    if (!S.legs || S.legs.length === 0) return 'hidden';
    const hasStart = S.legs[0]?.start_location;
    const hasEnd = S.legs[S.legs.length - 1]?.end_location;
    if (!hasStart || !hasEnd) return 'hidden';

    if (S.result?.stops?.length > 0) return 'guide';
    if (S.allStops?.length > 0) return 'planning';
    if (S.selectedStops?.length > 0) return 'route-building';
    return 'form';
  }

  // ─── Node Building ─────────────────────────────────────────────────────────

  function _buildNodes(phase) {
    if (phase === 'hidden') return [];

    const firstLeg = S.legs[0];
    const lastLeg = S.legs[S.legs.length - 1];

    const startNode = {
      id: 'start',
      type: 'start',
      name: firstLeg.start_location,
      lat: firstLeg.start_lat || null,
      lng: firstLeg.start_lng || null,
      placeId: firstLeg.start_place_id || null,
      state: 'done',
      nights: null,
      days: null,
      accName: null,
    };

    const endNode = {
      id: 'end',
      type: 'end',
      name: lastLeg.end_location,
      lat: lastLeg.end_lat || null,
      lng: lastLeg.end_lng || null,
      placeId: lastLeg.end_place_id || null,
      state: 'idle',
      nights: null,
      days: null,
      accName: null,
    };

    if (phase === 'form') {
      return [startNode, endNode];
    }

    if (phase === 'route-building') {
      const stopNodes = (S.selectedStops || []).map((stop) => ({
        id: String(stop.id || `stop-${stop.region || stop.name}`),
        type: 'stop',
        name: stop.region || stop.name || 'Stop',
        lat: stop.lat || null,
        lng: stop.lng || stop.lon || null,
        placeId: stop.place_id || stop.placeId || null,
        state: 'idle',
        nights: stop.nights || null,
        days: null,
        accName: null,
      }));
      return [startNode, ...stopNodes, endNode];
    }

    if (phase === 'planning') {
      const stopNodes = (S.allStops || []).map((stop) => ({
        id: String(stop.id || `stop-${stop.name}`),
        type: 'stop',
        name: stop.name || stop.region || 'Stop',
        lat: stop.lat || null,
        lng: stop.lng || stop.lon || null,
        placeId: stop.place_id || stop.placeId || null,
        state: S.result?.stops?.length > 0 ? 'done' : 'loading',
        nights: stop.nights || null,
        days: null,
        accName: null,
      }));
      return [startNode, ...stopNodes, endNode];
    }

    if (phase === 'guide') {
      const stopNodes = (S.result.stops || []).map((stop) => {
        let accName = null;

        // Try pendingSelections first
        if (S.pendingSelections && stop.id in S.pendingSelections) {
          const selIdx = S.pendingSelections[stop.id];
          const allStop = (S.allStops || []).find((s) => s.id === stop.id);
          if (allStop?.accommodations?.[selIdx]?.name) {
            accName = allStop.accommodations[selIdx].name;
          }
        }

        // Fall back to stop.accommodation.name
        if (!accName && stop.accommodation?.name) {
          accName = stop.accommodation.name;
        }

        return {
          id: String(stop.id || `stop-${stop.name}`),
          type: 'stop',
          name: stop.name || stop.region || 'Stop',
          lat: stop.lat || null,
          lng: stop.lng || stop.lon || null,
          placeId: stop.place_id || stop.placeId || null,
          state: 'done',
          nights: stop.nights || null,
          days: stop.days?.length || null,
          accName,
        };
      });
      return [startNode, ...stopNodes, endNode];
    }

    return [startNode, endNode];
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _initials(name) {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function _metaText(node) {
    const parts = [];
    if (node.nights) parts.push(`${node.nights}N`);
    if (node.days) parts.push(`${node.days}T`);
    return parts.join(' · ');
  }

  function _buildPills(node) {
    if (node.state !== 'done' || node.type === 'start' || node.type === 'end') return '';
    const pills = [];
    if (node.accName) {
      pills.push(`<span class="sb-pill sb-pill--acc" title="${esc(node.accName)}">${esc(node.accName)}</span>`);
    }
    if (node.days) {
      pills.push(`<span class="sb-pill sb-pill--days">${node.days} Tag${node.days !== 1 ? 'e' : ''}</span>`);
    }
    return pills.join('');
  }

  // ─── DOM Creation ──────────────────────────────────────────────────────────

  function _createNodeEl(node) {
    const el = document.createElement('div');
    el.className = `sb-node sb-node--${node.type}`;
    el.dataset.id = node.id;
    el.dataset.state = node.state;

    const meta = _metaText(node);
    const pills = _buildPills(node);

    el.innerHTML = `
      <div class="sb-connector-above"></div>
      <div class="sb-node-row">
        <div class="sb-avatar" id="sb-av-${esc(node.id)}">
          <div class="sb-avatar-fallback">${esc(_initials(node.name))}</div>
        </div>
        <div class="sb-node-body">
          <div class="sb-node-name">${esc(node.name)}</div>
          <div class="sb-node-meta"${meta ? '' : ' hidden'}>${esc(meta)}</div>
        </div>
      </div>
      <div class="sb-detail-pills"${pills ? '' : ' hidden'}>${pills}</div>
      <div class="sb-connector-below"></div>
    `;

    return el;
  }

  function _updateNodeEl(el, node) {
    el.dataset.state = node.state;

    const metaEl = el.querySelector('.sb-node-meta');
    if (metaEl) {
      const meta = _metaText(node);
      if (meta) {
        metaEl.textContent = meta;
        metaEl.removeAttribute('hidden');
      } else {
        metaEl.setAttribute('hidden', '');
      }
    }

    const pillsEl = el.querySelector('.sb-detail-pills');
    if (pillsEl) {
      const pills = _buildPills(node);
      if (pills) {
        pillsEl.innerHTML = pills;
        pillsEl.removeAttribute('hidden');
      } else {
        pillsEl.setAttribute('hidden', '');
      }
    }

    const nameEl = el.querySelector('.sb-node-name');
    if (nameEl) nameEl.textContent = node.name;
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  function _render(container) {
    const newIds = new Set(_nodes.map((n) => n.id));

    // Remove nodes no longer in list
    for (const oldId of _renderedIds) {
      if (!newIds.has(oldId)) {
        const el = container.querySelector(`[data-id="${CSS.escape(oldId)}"]`);
        if (el) el.remove();
        _renderedIds.delete(oldId);
      }
    }

    // Update or create nodes
    for (const node of _nodes) {
      const existing = container.querySelector(`[data-id="${CSS.escape(node.id)}"]`);
      if (existing) {
        _updateNodeEl(existing, node);
      } else {
        const newEl = _createNodeEl(node);
        container.appendChild(newEl);
        _renderedIds.add(node.id);
      }
    }

    // Reorder DOM to match _nodes array order
    for (const node of _nodes) {
      const el = container.querySelector(`[data-id="${CSS.escape(node.id)}"]`);
      if (el) container.appendChild(el);
    }
  }

  // ─── Lazy Image Loading ────────────────────────────────────────────────────

  async function _lazyLoadImages(nodes) {
    for (const node of nodes) {
      if (!node.lat && !node.lng && !node.placeId && !node.name) continue;

      const cacheKey = node.id;

      try {
        let imgUrl = null;

        if (_imageCache.has(cacheKey)) {
          imgUrl = _imageCache.get(cacheKey);
        } else {
          if (typeof GoogleMaps === 'undefined' || !GoogleMaps.getPlaceImages) continue;
          const imgs = await GoogleMaps.getPlaceImages(node.name, node.lat, node.lng, 'city', node.placeId);
          imgUrl = Array.isArray(imgs) ? imgs[0] : imgs;
          _imageCache.set(cacheKey, imgUrl);
        }

        if (!imgUrl) continue;

        const avatarEl = document.getElementById(`sb-av-${node.id}`);
        if (!avatarEl) continue;

        // Don't replace if already has an image
        if (avatarEl.querySelector('.sb-avatar-img')) continue;

        const img = document.createElement('img');
        img.className = 'sb-avatar-img';
        img.alt = node.name;
        img.style.opacity = '0';
        img.style.transition = 'opacity 0.3s ease';
        img.onload = () => {
          img.style.opacity = '1';
          const fallback = avatarEl.querySelector('.sb-avatar-fallback');
          if (fallback) avatarEl.replaceChild(img, fallback);
          else if (!avatarEl.contains(img)) avatarEl.appendChild(img);
        };
        img.src = imgUrl;
      } catch (_err) {
        // Silently ignore image loading errors
      }
    }
  }

  // ─── Public: initSidebar ───────────────────────────────────────────────────

  function initSidebar() {
    const sidebar = document.getElementById('trip-sidebar');
    if (!sidebar) return;

    // Create mobile overlay
    if (!_overlay) {
      _overlay = document.createElement('div');
      _overlay.className = 'sidebar-mobile-overlay';
      _overlay.addEventListener('click', () => toggleSidebar());
      document.body.appendChild(_overlay);
    }
  }

  // ─── Public: toggleSidebar ─────────────────────────────────────────────────

  function toggleSidebar() {
    const sidebar = document.getElementById('trip-sidebar');
    if (!sidebar) return;

    const isDesktop = window.innerWidth > 768;

    if (isDesktop) {
      sidebar.classList.toggle('collapsed');
      const collapseBtn = document.getElementById('sidebar-collapse-btn');
      if (collapseBtn) {
        const isExpanded = !sidebar.classList.contains('collapsed');
        collapseBtn.setAttribute('aria-expanded', String(isExpanded));
      }
    } else {
      sidebar.classList.toggle('mobile-open');
      if (_overlay) {
        _overlay.classList.toggle('visible');
      }
    }
  }

  // ─── Public: updateSidebar ─────────────────────────────────────────────────

  function updateSidebar() {
    const phase = _detectPhase();
    _nodes = _buildNodes(phase);

    const sidebar = document.getElementById('trip-sidebar');
    const appLayout = document.querySelector('.app-layout');

    if (phase === 'hidden') {
      if (sidebar) sidebar.setAttribute('hidden', '');
      if (appLayout) appLayout.dataset.sidebarVisible = 'false';
      return;
    }

    if (sidebar) {
      sidebar.removeAttribute('hidden');

      const container = document.getElementById('sidebar-track');
      if (container) {
        _render(container);
        _lazyLoadImages(_nodes);
      }
    }

    if (appLayout) appLayout.dataset.sidebarVisible = 'true';
  }

  // ─── Expose public API ─────────────────────────────────────────────────────

  return { initSidebar, updateSidebar, toggleSidebar };
})();

// ─── Top-level wrappers ───────────────────────────────────────────────────────

function initSidebar()   { Sidebar.initSidebar(); }
function updateSidebar() { Sidebar.updateSidebar(); }
function toggleSidebar() { Sidebar.toggleSidebar(); }
