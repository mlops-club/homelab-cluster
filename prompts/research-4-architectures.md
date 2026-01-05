I want to do the following to get traffic into my k3s cluster for internal clients on a tailnet.

1. resolve DNS name to IP (cloudflare, probably A record)
2. send network packets to IP inside of VPN (tailscale)
3. terminate TLS (traefik and cloudflared tunnel)
4. route decrypted packets to destination pod (traefik)

Here's the architecture I want:

1. deploy two instances of traefik
  1. one reachable at `*.priv.mlops-club.org`
  2. the other reachable at `*.pub.mlops-club.org`
2. priv should be reachable only via the tailnet
   - it will need to act as a TLS/SSL termination point, ideally using a certificate issued by cloudflare (if this is possible)
3. pub should be reachable via a cloudflared tunnel

Objectives:

1. [ ] propose 4 possible architectures to achieve the above; include
  - a diagram of all components
    - [ ] indicate where TLS termination happens--especially if it happens at a different place for public and private
  - any kubernetes operators that will be used
  - an example kubernetes manifest for a
    - [ ] a public service
    - [ ] a private service
    demonstrating what the experience would be for developers to deploy a service behind traefik in both cases
  - [ ] cite specific portions of online resources providing evidence that the proposed solutions are possible
  - [ ] tradeoffs, pros, and cons
2. [ ] create a minimal version of the public architecture
  1. [ ] deploy traefik, disregard TLS/SSL for now
  2. [ ] add a `nginx-deployment/manifest-public-cloudflare-traefik.yaml` to deploy a service that is reachable via a cloudflared tunnel, but is routed to traefik at `nginx.pub.mlops-club.org`
3. [ ] create a minimal version of the private architecture
  1. [ ] deploy traefik, disregard TLS/SSL for now
  2. [ ] add a `nginx-deployment/manifest-internal-tailscale-traefik.yaml` to deploy a service that is reachable via a tailscale IP, but is routed to traefik at `nginx.priv.mlops-club.org`; disregard TLS termination for now
3. [ ] add support for TLS termination

Hint:

1. use cloudflared tunnel to handle TLS termination for the public path
2. use traefik to handle TLS termination for the private path

Preferences:

1. As few manual steps as possible:
  - ideal: no manual steps at all
  - less ideal: only one-time manual steps, e.g. for core infrastructure like procuring TLS certs for traefik, but no manual steps for individual services behind traefik
  - worst: manual steps for individual services behind traefik
2. free; no paid services (e.g. ensure usage of tailscale and cloudflare falls into the free tier, note that `mlops-club.org` is registered with cloudflare, so that expense can be ignored)

Planning notes:
1. ignore any existing operators and manifests and scripts present in this repository; this is a chance to explore other divergent, potentially better approaches than the one taken so far
2. Search the internet extensively for all of the following sources to inform the planning process
  - forum conversations and threads
  - blog posts
  - technical documentation
  - github repositories

Specific resources to consider:
1. Blog: [Using Traefik on Kubernetes over Tailscale](https://joshrnoll.com/using-traefik-on-kubernetes-over-tailscale/)
2. GitHub repo: [Traefik with Cloudflare tunnel](https://github.com/filip-lebiecki/k3s-install/tree/main). Method for exposing services publicly via a cloudflare tunnel.