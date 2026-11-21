// Purpose: Audiobookshelf login smoke test over the public internet: sign in, browse, read 64 KB of an audiobook
// Scope: Grafana scripted check on public probes against books.mlops-club.org (Cloudflare, tunnel, Traefik);
//   runs locally with `k6 run --secret-source=file=<secrets.txt> monitoring/checks/audiobookshelf-login.js`
// Overview: Exercises the path listeners use. The `homelab-monitor` guest user can stream but not download,
//   upload or edit, and its password comes from the Grafana secret `audiobookshelf-monitor-password`.
//   Reads a byte range of the oldest book's first audio file, which proves the NAS mount serves media
import http from 'k6/http';
import { check, fail, group } from 'k6';
import secrets from 'k6/secrets';

const BASE = 'https://books.mlops-club.org';
export const options = { thresholds: { checks: ['rate==1'] } };

export default async function () {
  const password = await secrets.get('audiobookshelf-monitor-password');
  let auth;
  group('login', () => {
    const r = http.post(`${BASE}/login`, JSON.stringify({ username: 'homelab-monitor', password }),
      { headers: { 'Content-Type': 'application/json', 'x-return-tokens': 'true' } });
    if (!check(r, { 'login succeeds': (x) => x.status === 200 && !!x.json('user.id') })) fail('login failed');
    auth = { headers: { Authorization: `Bearer ${r.json('user.accessToken') || r.json('user.token')}` } };
  });
  let itemId, ino;
  group('browse', () => {
    const libs = http.get(`${BASE}/api/libraries`, auth);
    check(libs, { 'libraries listed': (r) => r.status === 200 && r.json('libraries').length > 0 });
    const lib = libs.json('libraries').find((l) => l.mediaType === 'book');
    const items = http.get(`${BASE}/api/libraries/${lib.id}/items?limit=1&sort=addedAt`, auth);
    check(items, { 'library has books': (r) => r.status === 200 && r.json('results').length === 1 });
    itemId = items.json('results.0.id');
    const item = http.get(`${BASE}/api/items/${itemId}?expanded=1`, auth);
    check(item, { 'book has audio': (r) => r.status === 200 && r.json('media.audioFiles').length > 0 });
    ino = item.json('media.audioFiles.0.ino');
  });
  group('stream', () => {
    const r = http.get(`${BASE}/api/items/${itemId}/file/${ino}`,
      { headers: { ...auth.headers, Range: 'bytes=0-65535' }, responseType: 'binary' });
    check(r, { 'audio bytes served from NAS': (x) => x.status === 206 && x.body.byteLength === 65536 });
  });
  http.post(`${BASE}/logout`, null, auth);
}
