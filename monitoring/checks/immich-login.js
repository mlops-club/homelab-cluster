// Purpose: Immich login smoke test: sign in, find the canary photo, load its thumbnail and original from the NAS
// Scope: Grafana scripted check on the tailnet probe; runs locally with
//   `k6 run --secret-source=file=<secrets.txt> monitoring/checks/immich-login.js`
// Overview: `homelab-monitor@mlops-club.org` is a non-admin user with a 0-byte quota. Its library holds one
//   generated canary image, so the test never reads personal photos. Password comes from the Grafana
//   secret `immich-monitor-password`. Signs out at the end
import http from 'k6/http';
import { check, fail, group } from 'k6';
import secrets from 'k6/secrets';

const BASE = 'https://photos.priv.mlops-club.org/api';
export const options = { thresholds: { checks: ['rate==1'] } };

export default async function () {
  const password = await secrets.get('immich-monitor-password');
  let auth;
  group('login', () => {
    const r = http.post(`${BASE}/auth/login`, JSON.stringify({ email: 'homelab-monitor@mlops-club.org', password }),
      { headers: { 'Content-Type': 'application/json' } });
    if (!check(r, { 'login succeeds': (x) => x.status === 201 && !!x.json('accessToken') })) fail('login failed');
    auth = { headers: { Authorization: `Bearer ${r.json('accessToken')}`, 'Content-Type': 'application/json' } };
  });
  let id;
  group('browse', () => {
    const r = http.post(`${BASE}/search/metadata`, JSON.stringify({ size: 1 }), auth);
    check(r, { 'canary photo found': (x) => x.status === 200 && x.json('assets.items').length === 1 });
    id = r.json('assets.items.0.id');
  });
  group('stream', () => {
    const thumb = http.get(`${BASE}/assets/${id}/thumbnail?size=preview`, { ...auth, responseType: 'binary' });
    check(thumb, { 'thumbnail served': (x) => x.status === 200 && x.body.byteLength > 1000 });
    const orig = http.get(`${BASE}/assets/${id}/original`,
      { headers: { ...auth.headers, Range: 'bytes=0-65535' }, responseType: 'binary' });
    check(orig, { 'original bytes served from NAS': (x) => x.status === 206 && x.body.byteLength === 65536 });
  });
  http.post(`${BASE}/auth/logout`, null, auth);
}
