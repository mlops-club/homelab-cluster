<!-- Purpose: "What this check does" report for the audiobookshelf-browser check, shown in a collapsed row on the public Homelab status dashboard
     Scope: Rendered by templatefile() in monitoring/terraform/status_dashboard.tf; ${img} and ${repo} are filled there -->

**Synthetic browser check, every 20 min from Grafana's Oregon and Ohio probes.** A real Chromium browser loads the public sign-in page, so this is the one check that renders the UI. It records page-load timing (first contentful paint, largest contentful paint, time to first byte) as a listener would see it.

| # | Step | What the browser does | Passes when |
|---|---|---|---|
| 1 | Open the site | `goto https://books.mlops-club.org/login`, wait for the network to go idle | page loads |
| 2 | See the sign-in form | wait for the password field | the field is visible |
| 3 | Confirm it's Audiobookshelf | read the page title | title contains "audiobookshelf" |

<img src="${img}/audiobookshelf-1-login.jpg" width="49%">

**Bar height** is the full page load in a browser. A red bar means the sign-in page didn't render from the internet. Script: [audiobookshelf-browser.js](${repo}/monitoring/checks/audiobookshelf-browser.js)
