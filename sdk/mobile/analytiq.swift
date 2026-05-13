// Analytiq iOS/macOS SDK
// Swift 5.9+  |  iOS 13+, macOS 10.15+, tvOS 13+, watchOS 6+
//
// Usage:
//   import Analytiq
//
//   // Initialize once in AppDelegate / @main
//   Analytiq.configure(apiKey: "YOUR_API_KEY", host: "https://your-domain.com")
//
//   // Track an event
//   Analytiq.track("button_tapped", properties: ["screen": "home"])
//
//   // Identify a user
//   Analytiq.identify("user-123", traits: ["email": "alice@example.com", "plan": "pro"])
//
//   // Page view
//   Analytiq.page("Settings")

import Foundation

public final class Analytiq: @unchecked Sendable {

    // ── Configuration ──────────────────────────────────────────────────────

    private static var shared: Analytiq?

    private let apiKey: String
    private let host:   String
    private let queue  = DispatchQueue(label: "com.analytiq.sdk", qos: .utility)
    private let session: URLSession

    private var userId:      String?
    private var anonymousId: String

    private init(apiKey: String, host: String) {
        self.apiKey   = apiKey
        self.host     = host.hasSuffix("/") ? String(host.dropLast()) : host
        let cfg       = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest  = 10
        cfg.timeoutIntervalForResource = 30
        self.session  = URLSession(configuration: cfg)

        // Stable anonymous ID persisted across launches
        let anonKey = "analytiq_anon_id"
        if let stored = UserDefaults.standard.string(forKey: anonKey) {
            self.anonymousId = stored
        } else {
            let id = UUID().uuidString
            UserDefaults.standard.set(id, forKey: anonKey)
            self.anonymousId = id
        }
    }

    // ── Public API ─────────────────────────────────────────────────────────

    public static func configure(apiKey: String, host: String = "https://app.analytiq.io") {
        shared = Analytiq(apiKey: apiKey, host: host)
    }

    public static func identify(_ userId: String, traits: [String: Any] = [:]) {
        guard let sdk = shared else { return }
        sdk.queue.async {
            sdk.userId = userId
            sdk.send(type: "identify", event: nil, userId: userId, properties: traits)
        }
    }

    public static func track(_ event: String, properties: [String: Any] = [:]) {
        guard let sdk = shared else { return }
        sdk.queue.async {
            sdk.send(type: "track", event: event, userId: sdk.userId, properties: properties)
        }
    }

    public static func page(_ name: String, properties: [String: Any] = [:]) {
        guard let sdk = shared else { return }
        sdk.queue.async {
            var props = properties
            props["name"] = name
            sdk.send(type: "page", event: name, userId: sdk.userId, properties: props)
        }
    }

    public static func reset() {
        guard let sdk = shared else { return }
        sdk.queue.async {
            sdk.userId = nil
            let id = UUID().uuidString
            sdk.anonymousId = id
            UserDefaults.standard.set(id, forKey: "analytiq_anon_id")
        }
    }

    // ── Internal ───────────────────────────────────────────────────────────

    private func send(type: String, event: String?, userId: String?, properties: [String: Any]) {
        var body: [String: Any] = [
            "type":        type,
            "anonymousId": anonymousId,
            "properties":  properties,
        ]
        if let event  = event  { body["event"]  = event }
        if let userId = userId { body["userId"] = userId }

        guard
            let url  = URL(string: "\(host)/api/ingest/\(apiKey)"),
            let data = try? JSONSerialization.data(withJSONObject: body)
        else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody   = data
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        session.dataTask(with: req) { _, _, error in
            if let error = error {
                print("[Analytiq] ingest error: \(error.localizedDescription)")
            }
        }.resume()
    }
}
