/**
 * Analytics Platform — Browser JS SDK
 *
 * Tracks user events (track, page, identify) and sends them to the
 * /api/ingest/{org_api_key} endpoint.
 *
 * Features:
 *   - Auto batching (flush every 2s or when queue reaches 20 events)
 *   - Retry with exponential back-off (up to 3 attempts)
 *   - Persistent anonymous_id via localStorage
 *   - Graceful no-op if window/localStorage unavailable (SSR guard)
 *
 * Usage:
 *   <script src="/sdk/analytics.js"></script>
 *   <script>
 *     Analytics.init('YOUR_ORG_API_KEY', {
 *       host: 'https://your-domain.com',  // optional, defaults to same origin
 *     });
 *     Analytics.identify('user-123', { email: 'alice@example.com' });
 *     Analytics.track('Purchase', { sku: 'PROD-1', price: 29.99 });
 *     Analytics.page({ url: window.location.href });
 *   </script>
 */

(function (global) {
  'use strict';

  // ── Constants ───────────────────────────────────────────────────────────────

  var ANON_KEY    = '__analytics_anon_id';
  var USER_KEY    = '__analytics_user_id';
  var BATCH_SIZE  = 20;
  var FLUSH_MS    = 2000;
  var MAX_RETRIES = 3;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function uuid() {
    // Simple UUID v4 (crypto.randomUUID when available, else Math.random fallback)
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getOrCreate(key) {
    try {
      var v = localStorage.getItem(key);
      if (!v) { v = uuid(); localStorage.setItem(key, v); }
      return v;
    } catch (_) {
      return uuid();
    }
  }

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* ignore */ }
  }

  function read(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }

  function now() {
    return new Date().toISOString();
  }

  // ── Retry fetch ─────────────────────────────────────────────────────────────

  function retryFetch(url, body, attempt) {
    attempt = attempt || 1;
    return fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
      keepalive: true,
    }).then(function (res) {
      if (res.status === 429 || res.status >= 500) {
        // Rate limited or server error — back-off and retry
        if (attempt < MAX_RETRIES) {
          return new Promise(function (resolve) {
            setTimeout(function () {
              resolve(retryFetch(url, body, attempt + 1));
            }, Math.pow(2, attempt) * 500); // 500ms, 1s, 2s
          });
        }
      }
      return res;
    });
  }

  // ── Core SDK ─────────────────────────────────────────────────────────────────

  var Analytics = {
    _apiKey:  null,
    _host:    '',
    _queue:   [],
    _timer:   null,
    _userId:  null,

    /**
     * Initialise the SDK.
     * Must be called before track/page/identify.
     *
     * @param {string} apiKey   - Your org API key from the dashboard.
     * @param {object} options  - { host?: string }
     */
    init: function (apiKey, options) {
      this._apiKey = apiKey;
      options = options || {};
      this._host   = (options.host || '').replace(/\/$/, '');
      this._userId = read(USER_KEY);
      this._startTimer();
    },

    /**
     * Associate future events with a known user.
     * @param {string} userId
     * @param {object} [traits]
     */
    identify: function (userId, traits) {
      if (!this._apiKey) return;
      this._userId = userId;
      store(USER_KEY, userId);
      this._enqueue({
        type:       'identify',
        userId:     userId,
        properties: traits || {},
        timestamp:  now(),
      });
    },

    /**
     * Track a named event.
     * @param {string} event
     * @param {object} [properties]
     */
    track: function (event, properties) {
      if (!this._apiKey) return;
      this._enqueue({
        type:        'track',
        event:       event,
        userId:      this._userId,
        anonymousId: getOrCreate(ANON_KEY),
        properties:  properties || {},
        timestamp:   now(),
      });
    },

    /**
     * Track a page view.
     * @param {object} [properties] - defaults to { url, title, referrer }
     */
    page: function (properties) {
      if (!this._apiKey) return;
      var defaults = {
        url:      typeof location !== 'undefined' ? location.href  : '',
        title:    typeof document !== 'undefined' ? document.title : '',
        referrer: typeof document !== 'undefined' ? document.referrer : '',
      };
      this._enqueue({
        type:        'page',
        userId:      this._userId,
        anonymousId: getOrCreate(ANON_KEY),
        properties:  Object.assign({}, defaults, properties || {}),
        timestamp:   now(),
      });
    },

    /**
     * Flush pending events immediately.
     * Called automatically by the timer or when the queue reaches BATCH_SIZE.
     */
    flush: function () {
      if (!this._queue.length || !this._apiKey) return;

      var batch = this._queue.splice(0, BATCH_SIZE);
      var url   = this._host + '/api/ingest/' + encodeURIComponent(this._apiKey);

      // Send each event individually (the ingest endpoint takes one event per call).
      // For bulk ingest performance, the server can be extended with a batch endpoint.
      var self = this;
      batch.forEach(function (event) {
        retryFetch(url, event).catch(function (err) {
          // Network failure — silently discard (never throw in analytics)
          if (typeof console !== 'undefined') {
            console.warn('[Analytics] Failed to send event:', err);
          }
        });
      });
    },

    // ── Private ───────────────────────────────────────────────────────────────

    _enqueue: function (event) {
      this._queue.push(event);
      if (this._queue.length >= BATCH_SIZE) {
        this.flush();
      }
    },

    _startTimer: function () {
      var self = this;
      this._timer = setInterval(function () {
        self.flush();
      }, FLUSH_MS);

      // Flush on page unload (best-effort)
      if (typeof window !== 'undefined') {
        window.addEventListener('visibilitychange', function () {
          if (document.visibilityState === 'hidden') {
            self.flush();
          }
        });
        window.addEventListener('pagehide', function () {
          self.flush();
        });
      }
    },
  };

  // ── Export ───────────────────────────────────────────────────────────────────

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Analytics;           // Node / CommonJS
  } else {
    global.Analytics = Analytics;         // Browser global
  }

}(typeof globalThis !== 'undefined' ? globalThis : this));
