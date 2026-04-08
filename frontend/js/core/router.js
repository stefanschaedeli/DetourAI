'use strict';

// Router — pattern-matched pretty URL router using History API.
// Reads: S (state.js), t (i18n.js), showSection, showLoading, hideLoading, lsGet, lsSet, LS_RESULT, LS_ROUTE, goToStep, showTravelGuide, activateGuideTab, activateStopDetail, activateDayDetail, openTravelsDrawer, openSettingsPage, apiGetTravel, apiGetShared.
// Provides: Router.init, Router.navigate, Router.slugify, Router.travelPath.

const Router = (() => {
  // ---------------------------------------------------------------------------
  // Route table — ordered patterns matched against location.pathname
  // ---------------------------------------------------------------------------
  const _routes = [
    { pattern: /^\/form\/step\/(\d+)$/,                             handler: '_formStep',       section: 'form-section' },
    { pattern: /^\/form\/?$/,                                       handler: '_form',            section: 'form-section' },
    { pattern: /^\/route-builder\/([a-f0-9]+)$/,                    handler: '_routeBuilder',    section: 'route-builder' },
    { pattern: /^\/accommodation\/([a-f0-9]+)$/,                    handler: '_accommodation',   section: 'accommodation' },
    { pattern: /^\/progress\/([a-f0-9]+)$/,                         handler: '_progress',        section: 'progress' },
    { pattern: /^\/travel\/(\d+)(?:-[^/]+)?\/stops\/(\d+)$/,         handler: '_travelStopDetail', section: 'travel-guide' },
    { pattern: /^\/travel\/(\d+)(?:-[^/]+)?\/days\/(\d+)$/,          handler: '_travelDayDetail',  section: 'travel-guide' },
    { pattern: /^\/travel\/(\d+)(?:-[^/]+)?\/(stops|calendar|budget|days)$/,  handler: '_travelTab',       section: 'travel-guide' },
    { pattern: /^\/travel\/(\d+)(?:-[^/]*)?$/,                      handler: '_travel',          section: 'travel-guide' },
    { pattern: /^\/travels\/?$/,                                    handler: '_travels',         section: null },
    { pattern: /^\/settings\/?$/,                                   handler: '_settings',        section: 'settings-section' },
    { pattern: /^\/?$/,                                             handler: '_form',            section: 'form-section' },
  ];

  const _titles = {
    get form()          { return t('app.title'); },
    get routeBuilder()  { return t('route_builder.title') + ' — DetourAI'; },
    get accommodation() { return t('router.accommodation_title'); },
    get progress()      { return t('router.progress_title'); },
    get travels()       { return t('header.my_travels') + ' — DetourAI'; },
    get settings()      { return t('settings.page_title') + ' — DetourAI'; },
  };

  // Internal flag to prevent re-entrant dispatch (including across async handlers)
  let _dispatching = false;

  // ---------------------------------------------------------------------------
  // Public API — init, navigate, slugify, travelPath
  // ---------------------------------------------------------------------------

  /** Attach popstate listener and dispatch the current URL on page load. */
  function init() {
    window.addEventListener('popstate', () => {
      _dispatch(location.pathname);
    });
    // Dispatch the current URL on load
    _dispatch(location.pathname);
  }

  /** Push or replace a URL and dispatch the matching route handler. */
  function navigate(path, opts) {
    opts = opts || {};
    const method = opts.replace ? 'replaceState' : 'pushState';
    // Preserve share token in URL when in shared mode
    let qs = location.search;
    if (S.sharedMode && S.shareToken && !path.includes('?share=') && !qs.includes('share=')) {
      qs = '?share=' + encodeURIComponent(S.shareToken);
    }
    history[method](null, '', path + qs);
    if (_dispatching || opts.skipDispatch) return;  // URL updated but no re-dispatch
    _dispatch(path);
  }

  async function _dispatch(path) {
    if (_dispatching) return;
    _dispatching = true;
    try {
      // Strip trailing slash for matching (except root)
      const clean = path.length > 1 ? path.replace(/\/$/, '') : path;

      for (const route of _routes) {
        const m = clean.match(route.pattern);
        if (m) {
          await _handlers[route.handler](m);
          return;
        }
      }
      // 404 fallback → redirect to /
      history.replaceState(null, '', '/' + location.search);
      _handlers._form([]);
    } finally {
      _dispatching = false;
    }
  }

  /** Convert a title string to a URL-safe ASCII slug (max 50 chars). */
  function slugify(text) {
    if (!text) return '';
    return text
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/[-\s]+/g, '-')
      .replace(/^-|-$/g, '')
      .substring(0, 50);
  }

  /** Build the canonical /travel/{id}-{slug} path for a saved trip. */
  function travelPath(id, title) {
    const slug = slugify(title);
    return slug ? `/travel/${id}-${slug}` : `/travel/${id}`;
  }

  // Toast helper for error messages
  function _toast(msg) {
    // Use existing alert as fallback — could be upgraded to a toast component
    alert(msg);
  }

  // ---------------------------------------------------------------------------
  // Route handlers — one per URL pattern, called by _dispatch
  // ---------------------------------------------------------------------------

  const _handlers = {
    _form() {
      document.title = _titles.form;
      showSection('form-section');
    },

    _formStep(m) {
      document.title = _titles.form;
      showSection('form-section');
      const n = parseInt(m[1], 10);
      if (n >= 1 && n <= 6) goToStep(n);
    },

    _routeBuilder(m) {
      const jobId = m[1];
      if (!S.jobId || S.jobId !== jobId) {
        _toast('Diese Planungssitzung ist abgelaufen.');
        navigate('/', { replace: true });
        return;
      }
      document.title = _titles.routeBuilder;
      showSection('route-builder');
    },

    _accommodation(m) {
      const jobId = m[1];
      if (!S.jobId || S.jobId !== jobId) {
        _toast('Diese Planungssitzung ist abgelaufen.');
        navigate('/', { replace: true });
        return;
      }
      document.title = _titles.accommodation;
      showSection('accommodation');
    },

    _progress(m) {
      const jobId = m[1];
      if (!S.jobId || S.jobId !== jobId) {
        // Check localStorage for a cached result with this jobId
        const cached = lsGet(LS_ROUTE);
        if (cached && cached.jobId === jobId) {
          S.jobId = jobId;
        } else {
          _toast('Diese Planungssitzung ist abgelaufen.');
          navigate('/', { replace: true });
          return;
        }
      }
      document.title = _titles.progress;
      showSection('progress');
    },

    async _travel(m) {
      const id = parseInt(m[1], 10);
      document.title = t('travels.loading_trip');

      // Shared view detection
      const shareToken = new URLSearchParams(location.search).get('share');
      if (shareToken) {
        S.sharedMode = true;
        S.shareToken = shareToken;
        showLoading(t('travels.loading_trip'));
        try {
          const plan = await apiGetShared(shareToken);
          plan._saved_travel_id = id;
          S.result = plan;
          const title = plan.custom_name || plan.title || '';
          document.title = `Reise: ${title} — DetourAI`;
          showTravelGuide(plan);
          showSection('travel-guide');
        } catch (err) {
          // Show error page with safe static content (no user input)
          const el = document.getElementById('guide-content');
          if (el) {
            el.textContent = '';
            const wrapper = document.createElement('div');
            wrapper.className = 'shared-error-page';
            const card = document.createElement('div');
            card.className = 'shared-error-card';
            const h = document.createElement('h2');
            h.textContent = 'Link ungueltig';
            const p = document.createElement('p');
            p.textContent = t('router.shared_link_invalid');
            card.appendChild(h);
            card.appendChild(p);
            wrapper.appendChild(card);
            el.appendChild(wrapper);
          }
          showSection('travel-guide');
        } finally {
          hideLoading();
        }
        return;
      }

      // Reset shared mode for non-shared views
      S.sharedMode = false;
      S.shareToken = null;

      // If the currently loaded result matches, just show it
      if (S.result && S.result._saved_travel_id === id) {
        const title = S.result.custom_name || S.result.title || '';
        document.title = `Reise: ${title} — DetourAI`;
        // Reset drill state when navigating back to overview URL (browser back/forward)
        activeTab = 'overview';
        _activeDayNum = null;
        _activeStopId = null;
        showTravelGuide(S.result);
        showSection('travel-guide');
        return;
      }

      // Load from API
      showLoading('Reiseplan wird geladen…');
      try {
        const plan = await apiGetTravel(id);
        plan._saved_travel_id = id;
        S.result = plan;
        S.jobId = plan.job_id || null;
        lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
        const title = plan.custom_name || plan.title || '';
        document.title = `Reise: ${title} — DetourAI`;
        // Reset drill state for fresh load
        activeTab = 'overview';
        _activeDayNum = null;
        _activeStopId = null;
        showTravelGuide(plan);
        showSection('travel-guide');
      } catch (err) {
        _toast('Reise nicht gefunden.');
        navigate('/travels', { replace: true });
      } finally {
        hideLoading();
      }
    },

    async _travelTab(m) {
      const id = parseInt(m[1], 10);
      const tab = m[2];

      // Share token detection
      const shareToken = new URLSearchParams(location.search).get('share');
      if (shareToken) { S.sharedMode = true; S.shareToken = shareToken; }

      // Ensure travel is loaded first
      if (!S.result || S.result._saved_travel_id !== id) {
        showLoading(t('travels.loading_trip'));
        try {
          const plan = S.sharedMode ? await apiGetShared(S.shareToken) : await apiGetTravel(id);
          plan._saved_travel_id = id;
          S.result = plan;
          if (!S.sharedMode) {
            S.jobId = plan.job_id || null;
            lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
          }
        } catch (err) {
          hideLoading();
          _toast('Reise nicht gefunden.');
          navigate('/travels', { replace: true });
          return;
        }
        hideLoading();
      }

      const title = S.result.custom_name || S.result.title || '';
      document.title = `Reise: ${title} — DetourAI`;
      // Reset drill state when navigating to a tab URL directly
      _activeStopId = null;
      _activeDayNum = null;
      showSection('travel-guide');
      activateGuideTab(tab);
    },

    async _travelStopDetail(m) {
      const id = parseInt(m[1], 10);
      const stopId = parseInt(m[2], 10);

      // Share token detection
      const shareToken = new URLSearchParams(location.search).get('share');
      if (shareToken) { S.sharedMode = true; S.shareToken = shareToken; }

      // Ensure travel is loaded first
      if (!S.result || S.result._saved_travel_id !== id) {
        showLoading(t('travels.loading_trip'));
        try {
          const plan = S.sharedMode ? await apiGetShared(S.shareToken) : await apiGetTravel(id);
          plan._saved_travel_id = id;
          S.result = plan;
          if (!S.sharedMode) {
            S.jobId = plan.job_id || null;
            lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
          }
        } catch (err) {
          hideLoading();
          _toast('Reise nicht gefunden.');
          navigate('/travels', { replace: true });
          return;
        }
        hideLoading();
      }

      const title = S.result.custom_name || S.result.title || '';
      document.title = `Reise: ${title} — DetourAI`;
      showSection('travel-guide');
      activateStopDetail(stopId);
    },

    async _travelDayDetail(m) {
      const id = parseInt(m[1], 10);
      const dayNum = parseInt(m[2], 10);

      // Share token detection
      const shareToken = new URLSearchParams(location.search).get('share');
      if (shareToken) { S.sharedMode = true; S.shareToken = shareToken; }

      // Ensure travel is loaded first
      if (!S.result || S.result._saved_travel_id !== id) {
        showLoading(t('travels.loading_trip'));
        try {
          const plan = S.sharedMode ? await apiGetShared(S.shareToken) : await apiGetTravel(id);
          plan._saved_travel_id = id;
          S.result = plan;
          if (!S.sharedMode) {
            S.jobId = plan.job_id || null;
            lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
          }
        } catch (err) {
          hideLoading();
          _toast('Reise nicht gefunden.');
          navigate('/travels', { replace: true });
          return;
        }
        hideLoading();
      }

      const title = S.result.custom_name || S.result.title || '';
      document.title = `Reise: ${title} — DetourAI`;
      showSection('travel-guide');
      activateDayDetail(dayNum);
    },

    _travels() {
      document.title = _titles.travels;
      openTravelsDrawer();
    },

    _settings() {
      document.title = _titles.settings;
      openSettingsPage();
    },
  };

  return { init, navigate, slugify, travelPath };
})();
