// Purpose: Navidrome login smoke test: authenticate, browse, read the first 64 KB of a real track
// Scope: Grafana scripted check on the tailnet probe; runs locally with
//   `k6 run --secret-source=file=<secrets.txt> monitoring/checks/navidrome-login.js`
// Overview: Uses the Subsonic API the mobile apps use, with salted-token auth (md5(password + salt)),
//   so the password never crosses the wire. Read-only `homelab-monitor` user; password from the Grafana
//   secret `navidrome-monitor-password`
import http from 'k6/http';
import crypto from 'k6/crypto';
import { check, fail, group } from 'k6';
import secrets from 'k6/secrets';

const BASE = 'https://navidrome.priv.mlops-club.org/rest';
export const options = { thresholds: { checks: ['rate==1'] } };
const ok = (r) => r.status === 200 && r.json('subsonic-response.status') === 'ok';

export default async function () {
  const password = await secrets.get('navidrome-monitor-password');
  const salt = Math.random().toString(36).slice(2, 12);
  const q = `u=homelab-monitor&t=${crypto.md5(password + salt, 'hex')}&s=${salt}&v=1.16.1&c=homelab-monitor&f=json`;
  let song;
  group('login', () => {
    if (!check(http.get(`${BASE}/ping?${q}`), { 'login succeeds': ok })) fail('login failed');
  });
  group('browse', () => {
    const folders = http.get(`${BASE}/getMusicFolders?${q}`);
    check(folders, { 'music folders listed': (r) => ok(r) && r.json('subsonic-response.musicFolders.musicFolder').length > 0 });
    const albums = http.get(`${BASE}/getAlbumList2?type=alphabeticalByName&size=1&${q}`);
    check(albums, { 'library has albums': (r) => ok(r) && r.json('subsonic-response.albumList2.album').length === 1 });
    const album = http.get(`${BASE}/getAlbum?id=${albums.json('subsonic-response.albumList2.album.0.id')}&${q}`);
    check(album, { 'album has tracks': (r) => ok(r) && r.json('subsonic-response.album.song').length > 0 });
    song = album.json('subsonic-response.album.song.0');
  });
  group('stream', () => {
    const r = http.get(`${BASE}/stream?id=${song.id}&format=raw&${q}`,
      { headers: { Range: 'bytes=0-65535' }, responseType: 'binary' });
    check(r, { 'track bytes served from NAS': (x) => x.status === 206 && x.body.byteLength === 65536 });
  });
}
