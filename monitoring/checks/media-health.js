// Purpose: Multi-step k6 check across the private media services, no credentials needed
// Scope: Grafana POC test 2 (how a scripted check is counted). Runs locally with `k6 run` and as a
//   Grafana scripted check on the tailnet probe. Login smoke tests replace it once monitoring users exist
import http from 'k6/http';
import { check, group } from 'k6';

export const options = { thresholds: { checks: ['rate==1'] } };

export default function () {
  group('jellyfin', () => {
    const health = http.get('https://jellyfin.priv.mlops-club.org/health');
    check(health, { 'jellyfin healthy': (r) => r.status === 200 && r.body.includes('Healthy') });
    const info = http.get('https://jellyfin.priv.mlops-club.org/System/Info/Public');
    check(info, { 'jellyfin reports a version': (r) => r.status === 200 && !!r.json('Version') });
  });
  group('immich', () => {
    const ping = http.get('https://photos.priv.mlops-club.org/api/server/ping');
    check(ping, { 'immich pong': (r) => r.status === 200 && r.json('res') === 'pong' });
    const ver = http.get('https://photos.priv.mlops-club.org/api/server/version');
    check(ver, { 'immich reports a version': (r) => r.status === 200 && r.json('major') !== undefined });
  });
  group('navidrome', () => {
    const ping = http.get('https://navidrome.priv.mlops-club.org/rest/ping?f=json');
    // Without credentials Subsonic answers 200 with an auth error: proves the server is up and routing
    check(ping, { 'navidrome answers subsonic': (r) => r.status === 200 && !!r.json('subsonic-response') });
  });
}
