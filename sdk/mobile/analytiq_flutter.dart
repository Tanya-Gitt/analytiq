/// Analytiq Flutter SDK
/// Dart 3.0+  |  Flutter 3.10+
///
/// Usage:
///   import 'analytiq_flutter.dart';
///
///   // Initialize once (e.g. in main())
///   await Analytiq.configure(apiKey: 'YOUR_API_KEY', host: 'https://your-domain.com');
///
///   Analytiq.track('button_tapped', properties: {'screen': 'home'});
///   Analytiq.identify('user-123', traits: {'email': 'alice@example.com', 'plan': 'pro'});
///   Analytiq.screen('Settings');

library analytiq;

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class Analytiq {
  static const _anonKey = 'analytiq_anon_id';

  static String  _apiKey      = '';
  static String  _host        = 'https://app.analytiq.io';
  static String? _userId;
  static String  _anonymousId = '';

  // ── Configuration ──────────────────────────────────────────────────────

  static Future<void> configure({
    required String apiKey,
    String host = 'https://app.analytiq.io',
  }) async {
    _apiKey = apiKey;
    _host   = host.endsWith('/') ? host.substring(0, host.length - 1) : host;

    final prefs = await SharedPreferences.getInstance();
    String? id  = prefs.getString(_anonKey);
    if (id == null) {
      id = DateTime.now().millisecondsSinceEpoch.toString() +
           '-' +
           (Object().hashCode.abs()).toRadixString(16);
      await prefs.setString(_anonKey, id);
    }
    _anonymousId = id;
  }

  // ── Public API ─────────────────────────────────────────────────────────

  static void identify(String userId, {Map<String, dynamic> traits = const {}}) {
    _userId = userId;
    _enqueue({
      'type':        'identify',
      'userId':      userId,
      'anonymousId': _anonymousId,
      'properties':  traits,
    });
  }

  static void track(String event, {Map<String, dynamic> properties = const {}}) {
    _enqueue({
      'type':        'track',
      'event':       event,
      if (_userId != null) 'userId': _userId,
      'anonymousId': _anonymousId,
      'properties':  properties,
    });
  }

  static void screen(String name, {Map<String, dynamic> properties = const {}}) {
    _enqueue({
      'type':        'page',
      'event':       name,
      if (_userId != null) 'userId': _userId,
      'anonymousId': _anonymousId,
      'properties':  {'name': name, ...properties},
    });
  }

  static void reset() => _userId = null;

  // ── Internal ───────────────────────────────────────────────────────────

  static void _enqueue(Map<String, dynamic> payload) {
    http
        .post(
          Uri.parse('$_host/api/ingest/$_apiKey'),
          headers: {'Content-Type': 'application/json'},
          body:    jsonEncode(payload),
        )
        .catchError(
          (e) => print('[Analytiq] ingest error: $e'),
        );
  }
}
