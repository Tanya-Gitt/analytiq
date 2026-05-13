/**
 * Analytiq React Native SDK
 * React Native 0.72+  |  iOS 13+, Android API 21+
 *
 * Usage:
 *   import Analytiq from './analytiq_react_native';
 *
 *   // Initialize once (e.g. in App.tsx)
 *   await Analytiq.configure({ apiKey: 'YOUR_API_KEY', host: 'https://your-domain.com' });
 *
 *   Analytiq.track('button_tapped', { screen: 'home' });
 *   Analytiq.identify('user-123', { email: 'alice@example.com', plan: 'pro' });
 *   Analytiq.screen('Settings');
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

interface Config {
  apiKey: string;
  host?:  string;
}

interface EventPayload {
  type:         string;
  event?:       string;
  userId?:      string;
  anonymousId:  string;
  properties:   Record<string, unknown>;
}

const ANON_KEY = 'analytiq_anon_id';

class AnalytiqClient {
  private apiKey:      string = '';
  private host:        string = 'https://app.analytiq.io';
  private userId:      string | undefined;
  private anonymousId: string = '';
  private ready:       Promise<void>;

  constructor() {
    this.ready = Promise.resolve();
  }

  async configure(config: Config): Promise<void> {
    this.apiKey = config.apiKey;
    this.host   = (config.host ?? 'https://app.analytiq.io').replace(/\/$/, '');

    this.ready = (async () => {
      let id = await AsyncStorage.getItem(ANON_KEY);
      if (!id) {
        id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        await AsyncStorage.setItem(ANON_KEY, id);
      }
      this.anonymousId = id;
    })();

    await this.ready;
  }

  identify(userId: string, traits: Record<string, unknown> = {}): void {
    this.userId = userId;
    this.enqueue({ type: 'identify', userId, anonymousId: this.anonymousId, properties: traits });
  }

  track(event: string, properties: Record<string, unknown> = {}): void {
    this.enqueue({
      type: 'track', event,
      userId:      this.userId,
      anonymousId: this.anonymousId,
      properties,
    });
  }

  screen(name: string, properties: Record<string, unknown> = {}): void {
    this.enqueue({
      type: 'page', event: name,
      userId:      this.userId,
      anonymousId: this.anonymousId,
      properties:  { ...properties, name },
    });
  }

  reset(): void {
    this.userId = undefined;
  }

  private enqueue(payload: EventPayload): void {
    this.ready.then(() => {
      fetch(`${this.host}/api/ingest/${this.apiKey}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      }).catch(err => console.warn('[Analytiq] ingest error:', err));
    });
  }
}

export default new AnalytiqClient();
