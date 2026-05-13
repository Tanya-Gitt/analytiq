# frozen_string_literal: true

# Analytics Platform — Ruby Server SDK
#
# Zero gem dependencies — uses stdlib Net::HTTP.
#
# Usage:
#   require 'analytiq'
#   client = Analytiq::Client.new('YOUR_API_KEY', host: 'https://your-host.com')
#   client.track('purchase', user_id: 'u_123', properties: { sku: 'P1', price: 29.99 })
#   client.identify('u_123', email: 'alice@example.com', plan: 'pro')
#   client.page(user_id: 'u_123', properties: { url: '/checkout' })

require 'json'
require 'net/http'
require 'uri'

module Analytiq
  VERSION = '0.1.0'

  # Raised when the server returns a non-2xx response.
  class Error < StandardError
    attr_reader :status

    def initialize(status, message)
      super("HTTP #{status}: #{message}")
      @status = status
    end
  end

  class Client
    # @param api_key [String]  Your org's API key from the Settings page.
    # @param host    [String]  Base URL of the analytics server.
    # @param timeout [Integer] Request timeout in seconds (default 10).
    def initialize(api_key, host: 'https://your-analytics-host.com', timeout: 10)
      @url     = URI("#{host.chomp('/')}/api/ingest/#{api_key}")
      @timeout = timeout
    end

    # Record a named action performed by a user.
    #
    # @param event       [String]
    # @param user_id     [String, nil]
    # @param anonymous_id [String, nil]
    # @param properties  [Hash]
    def track(event, user_id: nil, anonymous_id: nil, properties: {})
      send_payload(
        type:        'track',
        event:       event,
        userId:      user_id,
        anonymousId: anonymous_id,
        properties:  properties
      )
    end

    # Associate traits (email, plan, etc.) with a user.
    #
    # @param user_id [String]
    # @param traits  [Hash]  keyword arguments become the traits hash
    def identify(user_id, **traits)
      send_payload(
        type:       'identify',
        userId:     user_id,
        properties: traits
      )
    end

    # Record a page view.
    #
    # @param user_id     [String, nil]
    # @param anonymous_id [String, nil]
    # @param properties  [Hash]
    def page(user_id: nil, anonymous_id: nil, properties: {})
      send_payload(
        type:        'page',
        userId:      user_id,
        anonymousId: anonymous_id,
        properties:  properties
      )
    end

    private

    def send_payload(payload)
      # Strip nil values
      clean = payload.reject { |_, v| v.nil? }
      body  = JSON.generate(clean)

      http = Net::HTTP.new(@url.host, @url.port)
      http.use_ssl     = @url.scheme == 'https'
      http.open_timeout = @timeout
      http.read_timeout = @timeout

      request = Net::HTTP::Post.new(@url.path)
      request['Content-Type'] = 'application/json'
      request.body = body

      response = http.request(request)

      return if response.is_a?(Net::HTTPSuccess)

      begin
        detail = JSON.parse(response.body)['detail'] || response.body
      rescue StandardError
        detail = response.body
      end

      raise Error.new(response.code.to_i, detail)
    end
  end
end
