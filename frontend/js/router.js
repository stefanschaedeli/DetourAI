'use strict';

/* ── Pretty URL Router ── */

const Router = (() => {
  const _routes = [
    { pattern: /^\/form\/step\/(\d+)$/,                             handler: '_formStep',       section: 'form-section' },
    { pattern: /^\/form\/?$/,                                       handler: '_form',            section: 'form-section' },
    { pattern: /^\/route-builder\/([a-f0-9]+)$/,                    handler: '_routeBuilder',    section: 'route-builder' },
    { pattern: /^\/accommodation\/([a-f0-9]+)$/,                    handler: '_accommodation',   section: 'accommodation' },
    { pattern: /^\/progress\/([a-f0-9]+)$/,                         handler: '_progress',        section: 'progress' },
    { pattern: /^\/travel\/(\d+)-[^/]+\/(stops|calendar|budget)$/,  handler: '_travelTab',       section: 'travel-guide' },
    { pattern: /^\/travel\/(\d+)(?:-[^/]*)?$/,                      handler: '_travel',          section: 'travel-guide' },
    { pattern: /^\/travels\/?$/,                                    handler: '_travels',         section: null },
    { pattern: /^\/settings\/?$/,                                   handler: '_settings',        section: 'settings-section' },
    { pattern: /^\/?$/,                                             handler: '_form',            section: 'form-section' },
  ];

  const _titles = {
    form:           'Travelman — Reiseplaner',
    routeBuilder:   'Routenplanung — Travelman',
    accommodation:  'Unterkünfte — Travelman',
    progress:       'Planung läuft… — Travelman',
    travels:        'Meine Reisen — Travelman',
    settings:       'Einstellungen — Travelman',
  };

  // Internal flag to prevent pushState during popstate handling
  let _dispatching = false;

  function init() {
    window.addEventListener('popstate', () => {
      _dispatching = true;
      _dispatch(location.pathname);
      _dispatching = false;
    });
    // Dispatch the current URL on load
    _dispatching = true;
    _dispatch(location.pathname);
    _dispatching = false;
  }

  function navigate(path, opts) {
    opts = opts || {};
    if (_dispatching) return;
    const method = opts.replace ? 'replaceState' : 'pushState';
    history[method](null, '', path + location.search);
    _dispatching = true;
    _dispatch(path);
    _dispatching = false;
  }

  function _dispatch(path) {
    // Strip trailing slash for matching (except root)
    const clean = path.length > 1 ? path.replace(/\/$/, '') : path;

    for (const route of _routes) {
      const m = clean.match(route.pattern);
      if (m) {
        _handlers[route.handler](m);
        return;
      }
    }
    // 404 fallback → redirect to /
    history.replaceState(null, '', '/' + location.search);
    _handlers._form([]);
  }

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

  function travelPath(id, title) {
    const slug = slugify(title);
    return slug ? `/travel/${id}-${slug}` : `/travel/${id}`;
  }

  // Toast helper for error messages
  function _toast(msg) {
    // Use existing alert as fallback — could be upgraded to a toast component
    alert(msg);
  }

  // ── Route handlers ──

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
      document.title = 'Reise wird geladen… — Travelman';

      // If the currently loaded result matches, just show it
      if (S.result && S.result._saved_travel_id === id) {
        const title = S.result.custom_name || S.result.title || '';
        document.title = `Reise: ${title} — Travelman`;
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
        document.title = `Reise: ${title} — Travelman`;
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

      // Ensure travel is loaded first
      if (!S.result || S.result._saved_travel_id !== id) {
        showLoading('Reiseplan wird geladen…');
        try {
          const plan = await apiGetTravel(id);
          plan._saved_travel_id = id;
          S.result = plan;
          S.jobId = plan.job_id || null;
          lsSet(LS_RESULT, { jobId: S.jobId, savedAt: new Date().toISOString(), plan });
        } catch (err) {
          hideLoading();
          _toast('Reise nicht gefunden.');
          navigate('/travels', { replace: true });
          return;
        }
        hideLoading();
      }

      const title = S.result.custom_name || S.result.title || '';
      document.title = `Reise: ${title} — Travelman`;
      showTravelGuide(S.result);
      showSection('travel-guide');
      switchGuideTab(tab);
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
