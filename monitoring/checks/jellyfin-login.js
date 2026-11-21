// Purpose: Jellyfin login smoke test: sign in, list libraries, read the first 64 KB of a real media file
// Scope: Grafana scripted check on the tailnet probe; runs locally with
//   `k6 run --secret-source=file=<secrets.txt> monitoring/checks/jellyfin-login.js`
// Overview: Proves auth, the library database and the NAS media mount all work, not just that the pod
//   answers. Uses the read-only `homelab-monitor` user; its password comes from the Grafana secret
//   `jellyfin-monitor-password`. Signs out at the end so sessions don't pile up
import http from 'k6/http';
import { check, fail, group } from 'k6';
import secrets from 'k6/secrets';

const BASE = 'https://jellyfin.priv.mlops-club.org';
const CLIENT = 'MediaBrowser Client="homelab-monitor", Device="grafana-sm", DeviceId="homelab-monitor-sm", Version="1"';
export const options = { thresholds: { checks: ['rate==1'] } };

export default async function () {
  const password = await secrets.get('jellyfin-monitor-password');
  let token, userId;
  group('login', () => {
    const r = http.post(`${BASE}/Users/AuthenticateByName`, JSON.stringify({ Username: 'homelab-monitor', Pw: password }),
      { headers: { 'Content-Type': 'application/json', Authorization: CLIENT } });
    if (!check(r, { 'login succeeds': (x) => x.status === 200 && !!x.json('AccessToken') })) fail('login failed');
    token = r.json('AccessToken');
    userId = r.json('User.Id');
  });
  const auth = { headers: { Authorization: `${CLIENT}, Token="${token}"` } };
  let item;
  group('browse', () => {
    const views = http.get(`${BASE}/Users/${userId}/Views`, auth);
    check(views, { 'libraries listed': (x) => x.status === 200 && x.json('Items').length > 0 });
    const items = http.get(`${BASE}/Items?userId=${userId}&Recursive=true&IncludeItemTypes=Movie,Episode,Video,Audio` +
      '&SortBy=DateCreated&SortOrder=Ascending&Limit=1', auth);
    check(items, { 'library has media': (x) => x.status === 200 && x.json('Items').length === 1 });
    item = items.json('Items.0');
  });
  group('stream', () => {
    const kind = item.MediaType === 'Audio' ? 'Audio' : 'Videos';
    const r = http.get(`${BASE}/${kind}/${item.Id}/stream?static=true&mediaSourceId=${item.Id}`,
      { headers: { ...auth.headers, Range: 'bytes=0-65535' }, responseType: 'binary' });
    check(r, { 'media bytes served from NAS': (x) => x.status === 206 && x.body.byteLength === 65536 });
  });
  http.post(`${BASE}/Sessions/Logout`, null, auth);
}
