// Package analytiq provides a server-side Go client for Analytics Platform.
//
// Usage:
//
//	client := analytiq.New("YOUR_API_KEY",
//	    analytiq.WithHost("https://your-host.com"),
//	)
//	err := client.Track(ctx, "purchase", analytiq.Opts{
//	    UserID:     "u_123",
//	    Properties: map[string]any{"sku": "P1", "price": 29.99},
//	})
package analytiq

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client sends analytics events to the ingest endpoint.
// Safe for concurrent use.
type Client struct {
	url  string
	http *http.Client
}

// Option configures a [Client].
type Option func(*config)

type config struct {
	host       string
	httpClient *http.Client
}

// WithHost overrides the base URL.
// Default: https://your-analytics-host.com
func WithHost(host string) Option {
	return func(c *config) { c.host = host }
}

// WithHTTPClient replaces the default *http.Client (useful for testing).
func WithHTTPClient(hc *http.Client) Option {
	return func(c *config) { c.httpClient = hc }
}

// New creates a Client for the given API key.
func New(apiKey string, opts ...Option) *Client {
	cfg := &config{
		host:       "https://your-analytics-host.com",
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
	for _, o := range opts {
		o(cfg)
	}
	return &Client{
		url:  strings.TrimRight(cfg.host, "/") + "/api/ingest/" + apiKey,
		http: cfg.httpClient,
	}
}

// ── Opts ──────────────────────────────────────────────────────────────────────

// Opts holds optional fields for Track and Page calls.
type Opts struct {
	UserID      string
	AnonymousID string
	Properties  map[string]any
}

// ── Public methods ────────────────────────────────────────────────────────────

// Track records a named action performed by a user.
func (c *Client) Track(ctx context.Context, event string, opts Opts) error {
	return c.send(ctx, ingestPayload{
		Type:        "track",
		Event:       event,
		UserID:      opts.UserID,
		AnonymousID: opts.AnonymousID,
		Properties:  opts.Properties,
	})
}

// Identify associates traits (email, plan, etc.) with a user.
func (c *Client) Identify(ctx context.Context, userID string, traits map[string]any) error {
	return c.send(ctx, ingestPayload{
		Type:       "identify",
		UserID:     userID,
		Properties: traits,
	})
}

// Page records a page view.
func (c *Client) Page(ctx context.Context, opts Opts) error {
	return c.send(ctx, ingestPayload{
		Type:        "page",
		UserID:      opts.UserID,
		AnonymousID: opts.AnonymousID,
		Properties:  opts.Properties,
	})
}

// ── internals ─────────────────────────────────────────────────────────────────

type ingestPayload struct {
	Type        string         `json:"type"`
	Event       string         `json:"event,omitempty"`
	UserID      string         `json:"userId,omitempty"`
	AnonymousID string         `json:"anonymousId,omitempty"`
	Properties  map[string]any `json:"properties,omitempty"`
}

// Error is returned when the server responds with a non-2xx status.
type Error struct {
	Status  int
	Message string
}

func (e *Error) Error() string {
	return fmt.Sprintf("analytiq: HTTP %d: %s", e.Status, e.Message)
}

func (c *Client) send(ctx context.Context, p ingestPayload) error {
	body, err := json.Marshal(p)
	if err != nil {
		return fmt.Errorf("analytiq: marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("analytiq: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("analytiq: request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		var apiErr struct {
			Detail string `json:"detail"`
		}
		msg := string(raw)
		if json.Unmarshal(raw, &apiErr) == nil && apiErr.Detail != "" {
			msg = apiErr.Detail
		}
		return &Error{Status: resp.StatusCode, Message: msg}
	}
	return nil
}
