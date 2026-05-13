# Server-side SDKs

Send events from your backend to the Analytics Platform.
All SDKs wrap the same HTTP endpoint — `POST /api/ingest/{org_api_key}` — and have zero required external dependencies.

---

## Python

```bash
pip install ./sdk/python          # local dev
# or once published:
pip install analytiq
```

```python
from analytiq import Analytics

client = Analytics("YOUR_API_KEY", host="https://your-host.com")

client.track("purchase",
    user_id="u_123",
    properties={"sku": "PROD-1", "price": 29.99, "currency": "USD"})

client.identify("u_123", {"email": "alice@example.com", "plan": "pro"})

client.page(user_id="u_123", properties={"url": "/checkout"})
```

**Async (FastAPI / asyncio):**
```python
from analytiq import AsyncAnalytics

async with AsyncAnalytics("YOUR_API_KEY", host="https://your-host.com") as client:
    await client.track("signup", user_id="u_456")
```

---

## Node.js / TypeScript

```bash
npm install ./sdk/node            # local dev
# or once published:
npm install @analytiq/node
```

```typescript
import { Analytics } from '@analytiq/node';

const client = new Analytics('YOUR_API_KEY', { host: 'https://your-host.com' });

await client.track('purchase', {
  userId: 'u_123',
  properties: { sku: 'PROD-1', price: 29.99 },
});

await client.identify('u_123', { email: 'alice@example.com', plan: 'pro' });

await client.page({ userId: 'u_123', properties: { url: '/checkout' } });
```

---

## Go

```bash
go get github.com/your-org/analytiq-go
```

```go
import "github.com/your-org/analytiq-go/analytiq"

client := analytiq.New("YOUR_API_KEY",
    analytiq.WithHost("https://your-host.com"),
)

err := client.Track(ctx, "purchase", analytiq.Opts{
    UserID:     "u_123",
    Properties: map[string]any{"sku": "PROD-1", "price": 29.99},
})

err = client.Identify(ctx, "u_123", map[string]any{
    "email": "alice@example.com",
    "plan":  "pro",
})

err = client.Page(ctx, analytiq.Opts{UserID: "u_123"})
```

---

## Ruby

```bash
gem build sdk/ruby/analytiq.gemspec && gem install analytiq-0.1.0.gem
# or in Gemfile:
gem 'analytiq', path: './sdk/ruby'
```

```ruby
require 'analytiq'

client = Analytiq::Client.new('YOUR_API_KEY', host: 'https://your-host.com')

client.track('purchase',
  user_id: 'u_123',
  properties: { sku: 'PROD-1', price: 29.99 })

client.identify('u_123', email: 'alice@example.com', plan: 'pro')

client.page(user_id: 'u_123', properties: { url: '/checkout' })
```

---

## Event types

| Type       | Required fields | Optional fields                      |
|------------|----------------|--------------------------------------|
| `track`    | `event`        | `userId`, `anonymousId`, `properties`|
| `identify` | `userId`       | `properties` (treated as traits)     |
| `page`     | —              | `userId`, `anonymousId`, `properties`|

`properties` accepts any JSON-serialisable key-value map (max 50 keys, 3 levels deep).

## Finding your API key

Settings → **API Key** → copy the key shown. Pass it as the first argument to the SDK constructor.
