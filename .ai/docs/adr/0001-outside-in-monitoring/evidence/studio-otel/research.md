# OTel instrumentation research: FastAPI + React SPA -> own Collector -> Grafana Cloud Tempo

Research date: 2026-11-21. Sources are official repos, registries and docs. Where something was
read directly from source code at a tag, the tag is named. "Unverified" marks claims I could not
confirm from a primary source.

---

## 1. `@honeycombio/opentelemetry-web`

### Version and dependencies

- Latest: **1.5.1**, published 2026-09-15 (npm `time.modified` 2026-09-15T13:59Z; GitHub release
  `honeycomb-opentelemetry-web-v1.5.1` 2026-09-15T14:22Z).
  https://www.npmjs.com/package/@honeycombio/opentelemetry-web ,
  https://github.com/honeycombio/honeycomb-opentelemetry-web/releases
- **peerDependencies**: `@opentelemetry/auto-instrumentations-web: ^0.65.0`,
  `@opentelemetry/context-zone: ^2.0.0`.
  - **Gotcha:** for 0.x, `^0.65.0` means `>=0.65.0 <0.66.0`. The latest
    `@opentelemetry/auto-instrumentations-web` is **0.70.1** (2026-11-12), so install
    `@opentelemetry/auto-instrumentations-web@0.65` explicitly. 0.65.0 depends on
    `instrumentation-fetch ^0.220.0`, `instrumentation-document-load ^0.65.0`,
    `instrumentation-user-interaction ^0.64.0` and `instrumentation-xml-http-request ^0.220.0`.
- Main dependencies (pinned with `~`): `@opentelemetry/api ~1.9.1`, `sdk-trace-web ~2.9.0`,
  `sdk-trace-base ~2.9.0`, `resources ~2.9.0`, `core ~2.9.0`, `exporter-trace-otlp-http ~0.220.0`,
  `web-common ~0.220.0`, `instrumentation ~0.220.0`, `semantic-conventions ^1.43.0`,
  `web-vitals ^6.1.0`, `ua-parser-js ^1.0.37`, plus metrics and logs OTLP/HTTP exporters
  `^0.220.0` and `@opentelemetry/browser-instrumentation ^0.6.0`. Upstream experimental packages
  are now at 0.301.x, so the distro is several releases behind upstream.
- The README still says it is "built with" OTel JS 2.0.1 / 0.203.0 / semconv 1.37.0 and is compatible
  with auto-instrumentations-web ~0.49.0. That text is stale: package.json is what's current.

### Constructor options (`HoneycombOptions`, from `src/types.ts` on main)

`HoneycombOptions extends Partial<WebSDKConfiguration>`. Fields:

| Option | Notes (from source) |
|---|---|
| `apiKey`, `tracesApiKey`, `metricsApiKey`, `logsApiKey` | Optional. When set, the SDK adds the `x-honeycomb-team` header. With no key, no team header is sent. |
| `endpoint` | Default `https://api.honeycomb.io`. The SDK **appends `/v1/traces`, `/v1/metrics` and `/v1/logs`** (`maybeAppendPath`) unless the URL already ends with that path. |
| `tracesEndpoint`, `metricsEndpoint`, `logsEndpoint` | Used **verbatim**, with nothing appended. Each falls back to `endpoint`+path, and then to the **Honeycomb default**. |
| `headers`, `tracesHeaders`, `metricsHeaders`, `logsHeaders` | Extra exporter headers. |
| `dataset`, `metricsDataset` | Only for classic keys. |
| `serviceName` (default `unknown_service`), `serviceVersion` | |
| `spanProcessors: SpanProcessor[]` | Appended after the built-in processors (see below). |
| `traceExporter`, `traceExporters[]`, `disableDefaultTraceExporter` | |
| `metricExporters[]`, `disableDefaultMetricExporter` | |
| `logExporters[]`, `logRecordProcessors[]`, `disableDefaultLogExporter` | |
| `timeout` (10000), `tracesTimeout`, `metricsTimeout`, `logsTimeout` | |
| `sampleRate` (default 1) | A whole number N: 1-in-N sampling. 0 drops everything. |
| `sampler` | Overrides the DeterministicSampler. |
| `debug`, `logLevel` (DiagLogLevel, default DEBUG) | |
| `resourceAttributes` | Merged into the Resource. |
| `disableBrowserAttributes` | Turns off BrowserAttributesSpanProcessor and the browser resource. |
| `localVisualizations` | Logs Honeycomb trace links. Needs an apiKey. Don't use it in prod or with a custom collector. |
| `skipOptionsValidation` | Suppresses the "missing API key/service name" console warnings. |
| `entryPageAttributes: false \| EntryPageConfig` | Defaults `{path, hash, hostname, referrer: true; url, search: false}`. |
| `webVitalsInstrumentationConfig` | Default `{enabled: true}`. **Auto-added by the SDK.** |
| `globalErrorsInstrumentationConfig` | Default enabled. Emits `exception` spans for uncaught errors and unhandled rejections. |
| `navigationTimingInstrumentationConfig` | Default **disabled**. Emits a `browser.navigation_timing` **log record**. |
| `resourceTimingInstrumentationConfig` | Default **disabled**. Emits a `browser.resource_timing` log record per resource. |
| `sessionProvider: SessionProvider` | Replaces the default session-id provider. |
| WebSDK fields: `contextManager`, `textMapPropagator`, `instrumentations`, `resource`, `resourceDetectors`, `autoDetectResources`, `idGenerator`, `spanLimits` | Passed to the tracer provider. |

Source: https://github.com/honeycombio/honeycomb-opentelemetry-web/blob/main/packages/honeycomb-opentelemetry-web/src/types.ts ,
`util.ts`, `http-json-exporter.ts`, `composite-exporter.ts`, `honeycomb-otel-sdk.ts`, `validate-options.ts`.

### Exporting to a non-Honeycomb collector (no API key)

- The README's "Send to an OpenTelemetry Collector" example is
  `{ endpoint: "http(s)://<your-collector-url>", serviceName, skipOptionsValidation: true }`.
  https://github.com/honeycombio/honeycomb-opentelemetry-web/blob/main/packages/honeycomb-opentelemetry-web/README.md
- `apiKey` is optional. With no key, `configureHeaders` adds no `x-honeycomb-team` header.
- `validateOptionsWarnings` skips its warnings when `skipOptionsValidation` is set, **or** when
  `new URL(tracesEndpoint ?? endpoint)` parses and the hostname does not end with `.honeycomb.io`.
  A **relative** endpoint such as `/otlp` fails `new URL()`, so the warnings would fire. Set
  `skipOptionsValidation: true` or pass an absolute URL.
- Relative URLs themselves are OK for export. `@opentelemetry/otlp-exporter-base@0.220.0`
  `validateUserProvidedUrl` does `new URL(url, globalThis.location?.href)`, so `/otlp/v1/traces`
  resolves against the page origin. Hash routes do not affect this.
- **Pitfall:** metrics and logs exporters are **on by default**. If you set only `tracesEndpoint`,
  `getMetricsEndpoint` and `getLogsEndpoint` fall back to `https://api.honeycomb.io/v1/{metrics,logs}`.
  Use one of these instead:
  - `endpoint: window.location.origin + '/otlp'`. This posts to `/otlp/v1/traces`,
    `/otlp/v1/metrics` and `/otlp/v1/logs`.
  - `tracesEndpoint: '/otlp/v1/traces'` with `disableDefaultMetricExporter: true` and
    `disableDefaultLogExporter: true`. The log exporter carries the navigation and resource timing
    events if you enable them.
- The trace exporter is `OTLPTraceExporter` from `@opentelemetry/exporter-trace-otlp-http`, i.e.
  **OTLP/HTTP JSON**. The collector's OTLP HTTP receiver accepts JSON.
- Recommended config for this project:

  ```ts
  new HoneycombWebSDK({
    endpoint: `${window.location.origin}/otlp`,      // -> /otlp/v1/traces
    serviceName: 'xtra-studio-web',
    skipOptionsValidation: true,
    disableDefaultMetricExporter: true,              // unless /otlp/v1/metrics is wired
    instrumentations: [getWebAutoInstrumentations({ /* fetch/xhr/document-load/user-interaction opts */ })],
    // do NOT also push `new WebVitalsInstrumentation()`: the SDK already adds it (see below)
  }).start();
  ```

- **Duplicate web vitals gotcha:** `HoneycombWebSDK`'s constructor pushes `new WebVitalsInstrumentation(...)`
  unless `webVitalsInstrumentationConfig.enabled === false`. The README's getting-started snippet
  *also* passes `new WebVitalsInstrumentation()` in `instrumentations`, which would register it
  twice. Configure it through `webVitalsInstrumentationConfig` only.

### Web vitals: emitted as **spans**, not span events

From `src/web-vitals-autoinstrumentation.ts` (main) and the attribute constants in `src/semantic-attributes.ts`:

- Instrumentation scope: `@honeycombio/instrumentation-web-vitals`.
- `vitalsToTrack` default `['CLS', 'LCP', 'INP', 'TTFB', 'FCP']`. It uses `web-vitals/attribution`
  (v6), via `onCLS`, `onLCP`, `onINP`, `onTTFB` and `onFCP`.
- **Span name = `metric.name`**, i.e. exactly `CLS`, `LCP`, `INP`, `TTFB`, `FCP` (uppercase).
  Each span is created with `tracer.startSpan(name, {startTime})` and ended at the computed end time.
  INP uses `startActiveSpan`. With `inp.includeTimingsAsSpans: true`, child spans are created for
  each LoAF entry, named after `perfEntry.name`, and for each script entry.
- These are standalone root spans (their own traces), so they are not children of a page-load span.
- Common attributes per vital `<v>` ∈ {`cls`,`lcp`,`inp`,`fcp`,`ttfb`}:
  `<v>.id`, `<v>.value`, `<v>.delta`, `<v>.rating`, `<v>.navigation_type`, `<v>.navigation_id`,
  `<v>.navigation_url`, `<v>.navigation_start_time`, `<v>.navigation_interaction_id`.
- CLS: `cls.largest_shift_target`, `cls.element`, `cls.largest_shift_time`, `cls.largest_shift_value`,
  `cls.load_state`, `cls.had_recent_input`, plus `cls.element.data.<attr>`.
- LCP: `lcp.element`, `lcp.url`, `lcp.time_to_first_byte`, `lcp.resource_load_delay`,
  `lcp.resource_load_duration`, `lcp.element_render_delay`, `lcp.resource_load_time`,
  plus `lcp.element.data.<attr>`.
- INP: `inp.input_delay`, `inp.interaction_target`, `inp.interaction_time`, `inp.interaction_type`,
  `inp.load_state`, `inp.next_paint_time`, `inp.presentation_delay`, `inp.processing_duration`,
  `inp.duration`, `inp.element`, `inp.event_type`, plus `inp.element.data.<attr>`.
  - LoAF timing spans add `inp.timing.duration`, `inp.timing.entryType`, `inp.timing.name`,
    `inp.timing.renderStart` and `inp.timing.startTime`.
  - Script spans add `inp.timing.script.entry_type`, `.start_time`, `.execution_start`,
    `.duration`, `.forced_style_and_layout_duration`, `.invoker`, `.pause_duration`,
    `.source_url`, `.source_function_name`, `.source_char_position` and `.window_attribution`.
- FCP: `fcp.time_to_first_byte`, `fcp.time_since_first_byte`, `fcp.load_state`.
- TTFB: `ttfb.waiting_duration`, `ttfb.dns_duration`, `ttfb.connection_duration`,
  `ttfb.request_duration`, `ttfb.cache_duration`, `ttfb.waiting_time`, `ttfb.dns_time`,
  `ttfb.connection_time`, `ttfb.request_time`.
- Per-vital options: `applyCustomAttributes(vital, span)` and `dataAttributes: string[]`
  (LCP/CLS/INP), plus web-vitals `ReportOpts` such as `reportAllChanges`.
- Note: these names are Honeycomb-specific. OTel semconv defines a `browser.web_vital` **event**
  with `browser.web_vital.*` attributes instead (see section 3).

### Session handling

- `configureSpanProcessors` builds the processor list in this order:
  `BrowserAttributesSpanProcessor` (unless `disableBrowserAttributes`), then `BaggageSpanProcessor`,
  then `createSessionSpanProcessor(options.sessionProvider || defaultSessionProvider)` from
  `@opentelemetry/web-common`, then user `spanProcessors`.
- The web-common SessionSpanProcessor sets **`session.id`** on every span at start
  (`ATTR_SESSION_ID = 'session.id'`).
- **Default provider** (`default-session-provider.ts`): `new RandomIdGenerator().generateTraceId()`
  is called **once at module load**. That gives a 32-hex-char id that lasts for **the life of the JS
  page context**. A reload or new tab gives a new id, there is no persistence, and there is no
  inactivity timeout. The README says "'session.id' on every span, generated on page load". For a
  hash-routed SPA this means one session per hard load.
- For longer-lived sessions, pass `sessionProvider` built from web-common **0.220.0** exports:
  `createSessionManager({ sessionIdGenerator: createDefaultSessionIdGenerator(), sessionStore:
  createLocalStorageSessionStore(), maxDuration /*seconds*/, inactivityTimeout /*seconds*/ })`.
  This persists in `localStorage` key `opentelemetry-session`. `SessionManager` is also a
  `SessionPublisher` (observers for session start and end). Exports were verified in the npm
  tarball of web-common@0.220.0.

### Attributes added automatically

- **Resource** (`browser-attributes-resource.ts`): `user_agent.original`, `browser.mobile`,
  `browser.touch_screen_enabled`, `browser.language`, `browser.name`, `browser.version`
  (ua-parser-js), `device.type`, `network.effectiveType`, `screen.width`, `screen.height`,
  `screen.size` (`small` ≤768, `medium` ≤1024, `large` above that).
- **Resource** (`entry-page-resource.ts`): `entry_page.path`, `entry_page.hash`,
  `entry_page.hostname`, `entry_page.referrer`. `entry_page.url` and `entry_page.search` are off by default.
- **Resource** (`honeycomb-resource.ts`): `honeycomb.distro.version`,
  `honeycomb.distro.runtime_version='browser'`, `telemetry.distro.name='@honeycombio/opentelemetry-web'`,
  `telemetry.distro.version`. Also `service.name` and `service.version`, plus the default resource
  (`telemetry.sdk.*`).
- **Per span** (`BrowserAttributesSpanProcessor.onStart`): `browser.width`, `browser.height`,
  `page.hash`, `page.url` (full href, which includes the hash route), `page.route` (pathname),
  `page.hostname`, `page.search`, `url.path` (pathname), `browser.page.visibility`.
  - For hash routes, `page.route` / `url.path` stay `/`. The route lives in `page.hash`.
- **Sampler**: the `DeterministicSampler` adds the span attribute **`SampleRate`** (the integer N) to
  every sampled span. It wraps AlwaysOn (N=1), AlwaysOff (N=0) or `TraceIdRatioBasedSampler(1/N)`.
- **Exceptions** (global errors instrumentation): span named `exception` with `exception.type`,
  `exception.message`, `exception.stacktrace` and `exception.structured_stacktrace.{columns,lines,functions,urls}`.
  There is also an exported `recordException(error, attributes?, tracer?, applyCustomAttributesOnSpan?)` helper.

### Propagation (traceparent and baggage)

- The SDK does not inject headers itself. **Injection is done by `@opentelemetry/instrumentation-fetch`
  and `instrumentation-xml-http-request`** (via `getWebAutoInstrumentations`).
- In `fetch.ts` `_addHeaders`, injection is skipped unless `web.shouldPropagateTraceHeaders(spanUrl,
  propagateTraceHeaderCorsUrls)`. The config comment reads: "urls which should include trace headers when origin
  doesn't match". So **same-origin requests get `traceparent` automatically**, and
  `propagateTraceHeaderCorsUrls` is only needed for cross-origin URLs.
  https://github.com/open-telemetry/opentelemetry-js/blob/main/experimental/packages/opentelemetry-instrumentation-fetch/src/fetch.ts
- Default propagator: the WebTracerProvider's `register()` default is the W3C composite
  (`tracecontext` + `baggage`). So **baggage is propagated** if you put entries in context. This
  follows OTel JS defaults; I didn't re-read the provider source because the file has moved.
  Unverified at file level. Honeycomb also adds a `BaggageSpanProcessor` that copies **all** baggage
  entries from the parent context onto each span as attributes.
- Other fetch options: `ignoreUrls`, `clearTimingResources`, `applyCustomAttributesOnSpan`,
  `requestHook`, `ignoreNetworkEvents` (network timing is added as span events by default, so set
  it to true for fewer, wider spans), `measureRequestSize`. **Add `ignoreUrls: [/\/otlp\//]`** so
  the exporter's own POSTs aren't traced. (Upstream excludes exporter URLs in some versions;
  unverified for fetch 0.220.)

### Sampling

- `sampleRate` (int N) gives head sampling through DeterministicSampler. It sets the `SampleRate` attribute.
- Alternatively pass any `sampler`. The SDK warns when it is overridden.

---

## 2. Honeycomb guidance: wide events and few spans

### Official Honeycomb agent skills (Claude Code / Codex / Cursor plugin)

- Repo: **https://github.com/honeycombio/agent-skills** ("official honeycomb skills repository").
  Last commit 2026-11-20.
  - The README's install commands say `claude plugin marketplace add honeycombio/agent-skill`
    (singular), followed by `claude plugin install honeycomb`. The singular name likely redirects.
  - Docs: https://docs.honeycomb.io/integrations/agent-skills/ . MCP: https://docs.honeycomb.io/integrations/mcp/
- Contents: 9 skills (`observability-fundamentals`, `otel-instrumentation`, `otel-genai-instrumentation`,
  `otel-migration`, `beeline-migration`, `query-patterns`, `metrics-queries`,
  `production-investigation`, `slos-and-triggers`, `create-honeycomb-board`), agents
  `honeycomb-investigator` and `instrumentation-advisor`, and the command `/honeycomb-setup`.
- Key files:
  - `honeycomb/skills/otel-instrumentation/SKILL.md`
  - `.../references/wide-event-attributes.md`, the "canonical attribute catalog", from
    *Observability Engineering* 2nd ed., ch. 6
  - `.../references/python.md`
  - `.../references/custom-instrumentation.md`
  - `honeycomb/skills/observability-fundamentals/SKILL.md`

### Concrete rules (quoted or paraphrased from the skills and blog posts)

1. **A span is a wide event.** "In OpenTelemetry, a **span** is a wide event" (observability-fundamentals).
   Emit one wide event per unit of work (request or job) and put the context on it.
2. **Prefer attributes on existing spans over new child spans.** "When in doubt, prefer
   **attributes on existing spans** over creating new child spans." "Adding Attributes to Existing
   Spans (Highest Impact)" (otel-instrumentation SKILL.md). Jessica Kerr: "Attributes are the best,
   and also the cheapest."
3. **When to create a span: is it interesting *and* aggregable?** Yes for HTTP handlers, DB queries,
   external calls, cache lookups, queue pub/consume, and business transactions. No for helpers, loop
   iterations, getters, pure-CPU validation, or orchestration whose duration is just the sum of its
   children. "Too many spans: A trace with millions of 2ms spans is far too detailed ... Roll them up."
   Remove test or debug spans.
4. **Timing attributes instead of child spans**, e.g. `auth.duration_ms` and `payload_parse.duration_ms`
   on the parent span.
5. **Roll-up stats on the parent**, e.g. `stats.http_requests_count`,
   `stats.postgres_query_count` and `stats.*_duration_ms`.
6. **Errors**: `error=true`, span status ERROR, `exception.type/message/stacktrace`, plus a static,
   greppable **`exception.slug`** per throw site and an optional low-cardinality error category.
   For new code the skill prefers **Logs-API exception events** (`event.name=exception`) over
   `record_exception` span events.
7. **Span events**: Kerr's AI-prompt advice is "Do not create span events, they're expensive." Use a
   log, correlated to the trace, for point-in-time events.
8. **Naming**: dot-separated namespaces; follow semconv where it exists. "**Custom attributes**:
   Use your own namespace (`app.`, `checkout.`, `mycompany.`)" (SKILL.md). Martin Thwaites: library
   attributes get a unique prefix, org-wide ones `<org>.*`, application-specific ones **`app.*`**.
   Avoid team- or service-specific namespaces, and share constants in a library. Kerr suggests
   `<application>.<module>.<field>`.
9. **Attribute catalog** (wide-event-attributes.md):
   - service metadata (`service.name/environment/team/slack_channel`)
   - infra (`instance.*`)
   - orchestration (`container.*`, `k8s.*`, `cloud.*`)
   - build/deploy (`service.version`, `service.build.git_hash`,
     `service.build.deployment.age_minutes/trigger/user`)
   - feature flags (`feature_flag.<name>`)
   - runtime versions
   - HTTP (`http.route`, `http.route.param.*`, parsed UA)
   - timings, async stats, errors
   - user (`user.id/type/auth_method/team.id/org.id/age_days`)
   - rate limits, caching, localization, operational metrics (`uptime_sec`, `metrics.memory_mb`, ...)
10. **Instrument for 3am questions**: who is affected, what changed, where the bottleneck is.
11. **Sampling**: start unsampled. If needed, use uniform head sampling and record the rate. Prefer
    "wider, more context-rich events and a higher sample rate" (Morrell).
12. **Mark the main span** (`main = true`) for easy querying (Morrell). "Wrapping absolutely
    everything in its own span is the most common failure mode."
13. **Python/FastAPI**: use programmatic SDK init for ASGI apps, not the CLI, and call
    `FastAPIInstrumentor.instrument_app(app)` **after** routers are mounted. The skill's
    `configure_opentelemetry()` returns early ("no-op when unconfigured") if
    `OTEL_EXPORTER_OTLP_ENDPOINT` is unset (references/python.md).
14. **Frontend** (Winston Hearn): session-level context goes in resource attributes, dynamic
    context (auth state, customer/team id) in a span processor, and span-specific context in
    instrumentation hooks such as `applyCustomAttributesOnSpan`. Honeycomb charges per event
    regardless of attribute count, and up to 2,000 attributes per span are allowed.

### Canonical posts

- Jessica Kerr, "Span or Attribute? in OpenTelemetry custom instrumentation", 2026-05-07.
  https://honeycomb.io/blog/span-or-attribute-opentelemetry-custom-instrumentation
- Martin Thwaites, "OpenTelemetry Best Practices #1: Naming", updated 2024-08-26.
  https://www.honeycomb.io/blog/opentelemetry-best-practices-naming
- Winston Hearn, "High-cardinality instrumentation / wide events for frontend apps", updated 2025-02-24.
  https://www.honeycomb.io/blog/high-cardinality-instrumentation-wide-events-frontend-apps
- Charity Majors, "Is it time to version observability? (Signs point to yes)" (Observability 2.0,
  SREcon24 Americas, 2024). https://charity.wtf/p/is-it-time-to-version-observability-signs-point-to-yes ,
  https://www.honeycomb.io/blog/time-to-version-observability-signs-point-to-yes
- Jeremy Morrell, "A Practitioner's Guide to Wide Events", 2024-10-22.
  https://jeremymorrell.dev/blog/a-practitioners-guide-to-wide-events/
- Honeycomb, "Structured events are the basis of observability".
  https://www.honeycomb.io/blog/structured-events-basis-observability
- Docs: https://docs.honeycomb.io/send-data/standardize/add-custom-instrumentation ,
  https://docs.honeycomb.io/get-started/observability/concepts/instrumentation

---

## 3. OpenTelemetry semantic conventions: **v1.45.0** (released 2026-11-02)

- Release: https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.45.0 . Earlier releases:
  1.44.0 (2026-08-04), 1.43.0 (2026-07-03).
- Stability values below were extracted from `model/**/*.yaml` in the v1.45.0 tarball. Some
  namespaces now use the new `definition/2` file format.
- **Big structural change:** GenAI, client-side and mainframe conventions have **moved out** to separate repos.
  - In v1.45.0, `gen_ai.*` (104 attributes) and `enduser.*` carry the deprecation note "Moved to the
    OpenTelemetry GenAI / Client-Side semantic conventions repository".
  - https://github.com/open-telemetry/semantic-conventions-genai (v0.1.0, 2026-11-21) and
    https://github.com/open-telemetry/semantic-conventions-client-side (created 2026-08-26,
    v0.1.0-dev 2026-10-27; its `model/` contains `browser` and `enduser`).
  - `browser.*` and `session.*` are still in the core repo at 1.45.0 and are not marked deprecated.

| Attribute | Stability in v1.45.0 | Notes |
|---|---|---|
| `user.id`, `user.name`, `user.full_name`, `user.email`, `user.hash` | development | user registry |
| `user.roles` | development | string[] |
| `enduser.id`, `enduser.role`, `enduser.pseudo.id` | **deprecated** (moved to the client-side repo) | `enduser.scope` deprecated (obsoleted) |
| `session.id`, `session.previous_id` | development | `session.start` / `session.end` events are in model/session/events.yaml |
| `browser.brands`, `browser.platform`, `browser.mobile`, `browser.language` | development | |
| `browser.document.url.full` | development | |
| `browser.web_vital.name` (enum `cls`, `fcp`, `inp`, `lcp`, `ttfb` ...), `.value`, `.delta`, `.id`, `.rating`, `.navigation_type` | development | used by **event `browser.web_vital`** (development) |
| `user_agent.original` | **stable** | |
| `user_agent.name`, `.version`, `.os.name`, `.os.version`, `.synthetic.type` | development | |
| `url.full`, `url.path`, `url.query`, `url.fragment` | **stable** | |
| `url.template` | development | |
| `http.request.method`, `http.response.status_code`, `http.route` | **stable** | |
| metric `http.server.request.duration` | **stable** | |
| `server.address`, `client.address` | **stable** | |
| `service.name`, `service.version`, `service.namespace`, `service.instance.id` | **stable** | `service.criticality` alpha |
| `deployment.environment.name` | **stable** | `deployment.environment` deprecated, renamed to `.name` |
| `deployment.id`, `deployment.name`, `deployment.status` | development | |
| `vcs.ref.head.name`, `vcs.ref.head.revision`, `vcs.repository.url.full`, `vcs.repository.name`, `vcs.owner.name`, `vcs.provider.name` | release_candidate | also `vcs.ref.head.type`, `vcs.ref.base.*`, `vcs.change.id/state/title` |
| `cicd.pipeline.name`, `cicd.pipeline.run.id`, `cicd.pipeline.run.url.full`, `cicd.pipeline.run.state`, `cicd.pipeline.result`, `cicd.pipeline.action.name`, `cicd.pipeline.task.*`, `cicd.system.component` | release_candidate | |
| `cicd.worker.id`, `cicd.worker.name`, `cicd.worker.state`, `cicd.worker.url.full` | release_candidate | |
| "who triggered" a pipeline | **no attribute exists** | No `cicd.*` triggerer or actor attribute in 1.45.0, so use `app.*`. The Honeycomb catalog uses `service.build.deployment.user` and `.trigger`. |
| `k8s.namespace.name`, `k8s.pod.name`, `k8s.pod.uid`, `k8s.deployment.name`, `k8s.node.name`, `k8s.container.name` | **stable** | |
| `container.image.name`, `container.image.tags`, `container.image.repo_digests` | **stable** | `container.image.id` development |
| `host.name`, `host.id`, `host.arch`, `host.type`, `host.ip` | development | |
| `process.pid`, `process.runtime.name`, `process.runtime.version`, `process.runtime.description`, `process.command*`, `process.executable.name` | release_candidate | |
| `code.function.name`, `code.file.path`, `code.line.number`, `code.column.number`, `code.stacktrace` | **stable** | `code.function`, `code.filepath`, `code.lineno` and `code.namespace` are deprecated |
| `exception.type`, `exception.message`, `exception.stacktrace` | **stable** | `exception.escaped` deprecated |
| `error.type` | **stable** | `error.message` deprecated |
| `db.system.name`, `db.namespace`, `db.collection.name`, `db.operation.name`, `db.query.text`, `db.query.summary`, `db.response.status_code` | **stable** | `db.system` deprecated, renamed to `db.system.name` |
| `gen_ai.*` | **deprecated in core and moved** to semantic-conventions-genai v0.1.0 | In the new repo: `gen_ai.operation.name` (values include `chat`, `generate_content`, `text_completion`, `embeddings`, `retrieval`, `create_agent`, `invoke_agent`, `execute_tool`, `invoke_workflow`, `invoke_runner`, `plan`, `*_memory`), `gen_ai.agent.id`, `.name`, `.description`, `.version`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `gen_ai.conversation.id`. All development. |
| `app.*` | development, **reserved for mobile/client app semconv** | `app.build_id`, `app.installation.id`, `app.screen.*`, `app.widget.*`, `app.jank.*`, `app.crash.id`; events `app.crash`, `app.jank`, `app.screen.click`, `app.widget.click` |

- **Caution on `app.*`:** Honeycomb recommends `app.` for custom application attributes, but semconv
  now defines several `app.*` names for client apps. Custom `app.<domain>.*` keys are fine as long as
  they don't collide with `app.screen.*`, `app.widget.*`, `app.build_id`, `app.installation.id`,
  `app.jank.*` or `app.crash.*`. A product prefix (e.g. `xtra.*`) avoids the overlap entirely.
- **Web vitals convention:** semconv models web vitals as a **`browser.web_vital` event** (log or event
  record) with `browser.web_vital.{name,value,delta,id,rating,navigation_type}`. Honeycomb's distro
  emits **spans** named `LCP` etc. with `lcp.*` attributes. To be semconv-aligned you could copy the
  values in `applyCustomAttributes`, e.g. `span.setAttribute('browser.web_vital.name','lcp')`.

---

## 4. Python

### Versions (PyPI)

| Package | Latest | Uploaded |
|---|---|---|
| opentelemetry-sdk / exporter-otlp-proto-http | 1.45.2 | 2026-10-29 |
| opentelemetry-instrumentation-fastapi | 0.66b2 | 2026-10-29 |
| opentelemetry-instrumentation-asgi | 0.66b2 | 2026-10-29 |
| opentelemetry-instrumentation-httpx | 0.66b2 | 2026-10-29 |
| opentelemetry-distro | 0.66b2 | 2026-10-29 |
| opentelemetry-processor-baggage | 0.66b2 | 2026-10-29 |
| opentelemetry-instrumentation-logging | 0.66b2 | 2026-10-29 |
| azure-core | 1.41.0 | 2026-05-07 |
| azure-core-tracing-opentelemetry | 1.0.0b13 | 2026-05-01 |

All require Python >=3.10.

### FastAPI instrumentation (source: contrib tag v0.66b2, `instrumentation/opentelemetry-instrumentation-fastapi/.../__init__.py`)

- `FastAPIInstrumentor.instrument_app(app, server_request_hook=None, client_request_hook=None,
  client_response_hook=None, tracer_provider=None, meter_provider=None, excluded_urls=None,
  http_capture_headers_server_request=None, http_capture_headers_server_response=None,
  http_capture_headers_sanitize_fields=None, exclude_spans: list[Literal["receive","send"]] | None = None)`.
- The global `FastAPIInstrumentor().instrument(**kwargs)` accepts the same kwargs.
  `_InstrumentedFastAPI` applies them to apps created afterwards.
- **Exclude URLs:** env `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS="client/.*/info,healthcheck"` (or
  `OTEL_PYTHON_EXCLUDED_URLS` for all instrumentations). It's a comma-separated list of regexes
  matched with search against the full URL. You can also pass `excluded_urls=` to `instrument_app`.
- **Drop the internal ASGI `http send` / `http receive` spans:** `exclude_spans=["receive", "send"]`.
  This is a kwarg only; there is **no env var**. In the ASGI middleware it sets
  `exclude_receive_span` and `exclude_send_span`.
- `server_request_hook(span, scope)` is called with the **server span** for each request. That's
  the place for wide-event attributes, although `trace.get_current_span()` inside the handler
  works too.
- Span name: `"{METHOD} {route}"` (e.g. `GET /api/items/{item_id}`), with `http.route` set.
  Header capture uses env `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`,
  `..._SERVER_RESPONSE` and `..._SANITIZE_FIELDS`.
- **Sync route handlers:** FastAPI runs them in a threadpool via `anyio.to_thread`. OTel context is
  carried by contextvars, which Starlette copies into the worker thread, so `get_current_span()`
  inside a sync `def` handler returns the server span. This is standard behaviour; I didn't verify
  it at source level for this version. Background threads you start yourself need
  `contextvars.copy_context()` or explicit context passing.

### httpx

- `opentelemetry-instrumentation-httpx` 0.66b2: `HTTPXClientInstrumentor().instrument()` covers all
  clients, or use `instrument_client(client)`. It supports sync and async, and has
  `request_hook`/`response_hook`. https://pypi.org/project/opentelemetry-instrumentation-httpx/

### Zero-code `opentelemetry-instrument` with uvicorn

- OTel docs (https://opentelemetry.io/docs/zero-code/python/troubleshooting/):
  - Uvicorn is listed as supporting **traces and logs but not metrics** under pre-fork.
  - "specifying more than one `--workers` may break the generation of metrics."
  - Gunicorn with `uvicorn.workers.UvicornWorker` supports all signals.
  - The alternative is to initialise OTel inside each worker after fork.
  - The reloader caveat is documented for Flask debug mode. Uvicorn `--reload` likewise spawns a
    subprocess; that's my inference, not documented.
- `opentelemetry-distro` 0.66b2 `_configure` sets defaults `OTEL_TRACES_EXPORTER=otlp`,
  `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp` and **`OTEL_EXPORTER_OTLP_PROTOCOL=grpc`**.
  For OTLP/HTTP, set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`.
- Honeycomb's skill recommends **programmatic init for FastAPI**.

### Baggage span processor

- `pip install opentelemetry-processor-baggage`, then
  `from opentelemetry.processor.baggage import BaggageSpanProcessor, ALLOW_ALL_BAGGAGE_KEYS` and
  `tracer_provider.add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))`.
- Or pass a predicate such as `lambda k: k.startswith("app.")`.
- There is also a `BaggageLogProcessor`.
- Warning from the README: baggage goes into all outgoing HTTP headers, so don't put secrets in it.
  https://github.com/open-telemetry/opentelemetry-python-contrib/tree/v0.66b2/processor/opentelemetry-processor-baggage

### `OTEL_SDK_DISABLED` and no-op when unconfigured

- In opentelemetry-sdk 1.45.2, `sdk/trace/__init__.py` `TracerProvider.__init__` reads
  `OTEL_SDK_DISABLED`; `"true"` (case-insensitive) sets `self._disabled`. `get_tracer()` then
  returns `NoOpTracer()`. Instrumentations still wrap the app, but the spans are non-recording.
- A no-op pattern when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset: skip creating the TracerProvider and
  skip instrumentation entirely (the Honeycomb skill does exactly this). The API's default
  ProxyTracerProvider then yields non-recording spans, so `trace.get_current_span().set_attribute(...)`
  calls are harmless no-ops.
- `OTEL_TRACES_EXPORTER=none` is also honoured by the SDK configurator (`names.lower() == "none"`).

### Azure SDK tracing

- **Native OTel in azure-core ≥ 1.33.0 (2025-04-03).** Requirements: `opentelemetry-api` is
  installed, `settings.tracing_implementation` is **not** set, and `settings.tracing_enabled = True`
  (env `AZURE_TRACING_ENABLED`). Adds `azure.core.instrumentation.get_tracer` and `TracingOptions`
  (per-operation enable and attributes).
  https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/core/azure-core/CHANGELOG.md
  - Not every client library uses the native tracer yet (unverified per library).
- **Plugin route:** `azure-core-tracing-opentelemetry` 1.0.0b13 (pre-release), enabled with
  `settings.tracing_implementation = "opentelemetry"` or env `AZURE_SDK_TRACING_IMPLEMENTATION=opentelemetry`.
  https://pypi.org/project/azure-core-tracing-opentelemetry/
- **Span volume:**
  - One INTERNAL span per public client method. Nested internal spans are suppressed (b10), and
    INTERNAL spans under INTERNAL/CLIENT/PRODUCER parents are suppressed (b12).
  - One CLIENT HTTP span per HTTP request from `DistributedTracingPolicy`. Retries add requests.
  - Paged or chunked operations (blob list, large downloads) produce one HTTP span per page or chunk.
  - Other HTTP instrumentation such as requests is suppressed under Azure spans, which avoids duplicates.
  - For "few spans", leave Azure tracing off and record counts and durations as attributes. Enable
    it only per operation if needed.

---

## 5. Grafana Cloud

### Free tier (pricing page fetched 2026-11-21: https://grafana.com/pricing/)

- Metrics: 10k active series/month, 14-day retention.
- Logs: 50 GB ingested/month, 14 days.
- **Traces: 50 GB ingested/month, 14 days.**
- Profiles: 50 GB/month, 14 days.
- Users: 3 active Grafana users, 3 Grafana Assistant AI users, 3 IRM users.
- Application Observability: 2,232 host hours/month. Kubernetes Monitoring: 2,232 host hours and
  37,944 container hours. Frontend Observability (Faro): 50k sessions. k6: 500 VUh. Synthetics: 100k
  API and 10k browser executions.
- Pro: $19/month platform fee. Traces are priced per GB processed ($0.05), written ($0.40) and
  retained ($0.10). Retention is 30 days for logs, traces and profiles and 13 months for metrics.
- **Trace billing** (https://grafana.com/docs/grafana-cloud/platform/pricing-and-usage/traces/): billed on
  GB processed, written and retained. "Processed" is measured when Grafana Cloud receives the data,
  before Adaptive Traces. Spans discarded for exceeding limits are not billed. The docs don't say
  whether this is compressed or uncompressed size (unverified).
- **Trace limits**: ingestion 500,000 B/s, burst 500,000 B, `max_bytes_per_trace` 3,000,000 B. The
  docs also say "default limit ... 5MB", which is inconsistent.
  https://grafana.com/docs/grafana-cloud/platform/pricing-and-usage/usage-limits/

### OTLP gateway and auth

- Endpoint: `https://otlp-gateway-<REGION/zone>.grafana.net/otlp`. SDKs and collectors append
  `/v1/traces`. Copy the exact host from the stack's **OpenTelemetry tile**, because it varies by region.
  https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/
- Auth: HTTP **Basic**, with username = **stack (instance) ID** and password = a **Cloud Access
  Policy token** with `traces:write` (plus `metrics:write` and `logs:write` if needed).
  - Terraform `grafana_cloud_stack` exposes `otlp_url`: "The username is the stack's ID (`id`
    attribute of this resource)".
  - Scope reference: https://grafana.com/docs/grafana-cloud/send-data/traces/set-up/add-access-policy/
  - Use OTLP/**HTTP** to `/otlp/v1/traces`; gRPC isn't accepted on that path (troubleshooting doc).

### Creating the access policy and token

- **Terraform** (provider `grafana/grafana` latest **v4.55.0**, 2026-11-13):
  - Resources `grafana_cloud_access_policy` (`region`, `name`, `scopes`,
    `realm { type = "org"|"stack", identifier, label_policy{selector} }`, optional `conditions{allowed_subnets}`)
    and `grafana_cloud_access_policy_token` (`region`, `access_policy_id = <policy>.policy_id`,
    `name`, optional `expires_at`). The token value is in the `token` attribute (sensitive).
  - The **provider must be authenticated with a Cloud Access Policy token**
    (`cloud_access_policy_token`, env `GRAFANA_CLOUD_ACCESS_POLICY_TOKEN`) whose own scopes include
    `accesspolicies:read`, `accesspolicies:write` and `accesspolicies:delete`. A stack service
    account token (the Grafana instance API) **cannot** do this.
  - Docs: https://github.com/grafana/terraform-provider-grafana/blob/main/docs/resources/cloud_access_policy.md ,
    `.../cloud_access_policy_token.md`, `docs/index.md`.
- **grafana.com API**:
  - `POST https://www.grafana.com/api/v1/accesspolicies?region=<region>` with body
    `{name, displayName?, scopes:[...], realms:[{type:"stack", identifier:"<stackId>", labelPolicies?}], conditions?}`.
  - `POST https://www.grafana.com/api/v1/tokens?region=<region>` with body
    `{accessPolicyId, name, displayName?, expiresAt?}`. With no `expiresAt`, the token doesn't expire.
  - Both use `Authorization: Bearer <cloud access policy token>`. The access-policies endpoint is
    rate-limited to 600/hour.
  - https://grafana.com/docs/grafana-cloud/developer-resources/api-reference/cloud-api/

### TraceQL (Tempo)

Docs: https://grafana.com/docs/tempo/latest/traceql/ . Tempo docs now also exist for v3.0.x.

- Scopes: `span.<attr>`, `resource.<attr>`, unscoped `.<attr>`, plus `event.`, `link.` and
  `instrumentation.` scopes.
- Intrinsics: `name`/`span:name`, `status`/`span:status`, `duration`/`span:duration`, `kind`,
  `trace:rootService`, `trace:rootName`, `trace:duration`.
- Examples: `{ resource.service.name = "api" && span.http.route = "/items/{id}" && span.http.response.status_code >= 500 }`
  and `{ } | select(span.app.user.id, resource.service.version)`. `select()` adds columns to the
  search results.
- **TraceQL metrics functions**: `rate()`, `count_over_time()`, `sum_over_time(attr)`,
  `min_over_time(attr)`, `max_over_time(attr)`, `avg_over_time(attr)`,
  `quantile_over_time(attr, .99, .9, .5)`, `histogram_over_time(attr)`, `compare({filter}, topN?)`,
  and `topk(n)` / `bottomk(n)`. All except `compare` take `by (...)`.
  - Example: `{ span:name = "GET /:endpoint" } | quantile_over_time(span:duration, .99) by (span.http.route)`.
  - Comparison operators and arithmetic across parenthesised sub-queries are supported.
  - https://grafana.com/docs/tempo/latest/traceql/metrics-queries/functions/
- **Max range in Grafana Cloud: 24 hours.** "TraceQL metrics can query metrics for a time range of 24
  hours"; longer ranges need Support. OSS default: `query_frontend.metrics.max_duration` = 24h.
  https://grafana.com/docs/grafana-cloud/send-data/traces/configure/metrics-generator/
- **Free tier:** no exclusion found. Traces Drilldown, included in Cloud, is built on TraceQL
  metrics. One Grafana doc snippet still calls TraceQL metrics "public preview". I couldn't confirm
  free-tier availability explicitly (unverified).
- **Dashboards (Tempo datasource query model)**, from
  https://github.com/grafana/grafana-tempo-datasource/blob/main/src/dataquery.ts . The Tempo
  datasource plugin has moved out of grafana/grafana into its own repo.
  - `queryType`: `'traceql' | 'traceqlSearch' | 'serviceMap' | 'upload' | 'nativeSearch' | 'traceId' | 'clear'`.
  - Other fields: `query` (the TraceQL string), `limit`, `spss`, `step`, `tableType: 'traces' | 'spans' | 'raw'`,
    `metricsQueryType: 'range' | 'instant'`, `filters[]`, `groupBy[]`, `serviceMapQuery`.
  - Metrics panel: `{queryType:"traceql", query:"{...} | rate() by (...)", metricsQueryType:"range", step:"1m"}`.
  - Trace table panel: `{queryType:"traceql", query:"{...}", tableType:"traces", limit:20}`.
- **Datasource UID:** Grafana Cloud's provisioned traces datasource is commonly UID
  `grafanacloud-traces`. **Unverified**: confirm with `GET /api/datasources` or the datasource settings page.

### Application Observability and span metrics

- Metrics generation (span metrics and service graphs) is **disabled by default**. Enable it in
  Application Observability → Configuration → System, or via Support. Generated series go to the
  stack's Prometheus and "are billed like regular metrics" (active series).
  https://grafana.com/docs/grafana-cloud/send-data/traces/configure/metrics-generator/
- Application Observability is billed per **host hour**. A host is an OS instance that sent signals
  in the last 15 minutes; containers are not hosts. The free tier includes 2,232 host hours/month.
  - Customers starting on or after **2026-02-13**: $0.025/host-hour plus telemetry at standard rates.
  - Legacy customers: $0.04/host-hour, including 1.5 active series and 0.02 GB of traces per host-hour.
  - https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/pricing/ (via search summary)
  - Alternative: compute RED with TraceQL metrics on demand and skip span metrics generation.

---

## 6. Collector config patterns (collector core v0.165.0 2026-11-06, contrib v0.165.1 2026-11-09)

### Component type renames

From each component's `metadata.yaml`. Old names still work as `deprecated_type`.

- `otlphttp` exporter → **`otlp_http`**
- `basicauth` extension → **`basic_auth`** (beta)
- `k8sattributes` → **`k8s_attributes`** (stable for traces, metrics and logs; semconv 1.45.0)
- `resourcedetection` → **`resource_detection`**
- Unchanged: `resource` (beta), `transform` (beta), `attributes`, `filter` (alpha), `tail_sampling`,
  `batch` (beta), `memory_limiter`, `otlp` receiver.

### k8s_attributes

Source: https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/k8sattributesprocessor/README.md

- Default metadata: `k8s.namespace.name`, `k8s.pod.name`, `k8s.pod.uid`, `k8s.pod.start_time`,
  `k8s.deployment.name`, `k8s.node.name`.
  - `k8s.deployment.name` is derived from the ReplicaSet name by trimming the hash, so it needs **no
    ReplicaSet informer or RBAC** unless `k8s.deployment.uid` or deployment/replicaset label
    extraction is enabled.
  - Optional metadata: `k8s.pod.ip`, `k8s.pod.hostname`, `k8s.replicaset.*`, `container.image.name`,
    `container.image.tag`, `k8s.container.name`, `service.namespace/name/version/instance.id`, and more.
    The processor emits **`container.image.tag`** (singular), while the semconv registry defines
    `container.image.tags` (string[]).
  - `otel_annotations: true` reads `resource.opentelemetry.io/*` pod annotations.
- `passthrough: false` (default) means the processor does the lookups itself.
- `filter.namespace: <ns>` limits the informers to one namespace.
- `pod_association` is a list of `sources` (up to 4, all must match):
  - `from: connection` uses the peer IP. **It must run before `batch`/`tail_sampling`.**
  - `from: resource_attribute, name: k8s.pod.ip | k8s.pod.uid | (k8s.pod.name + k8s.namespace.name)`.
  - With no rules configured, association is by connection IP only.
- **Namespace-scoped RBAC:** a `Role` and `RoleBinding` in the workload namespace with
  `pods: get, watch, list`. Add `apps/replicasets` only when ReplicaSet lookup is needed (README
  example also lists `deployments`, `statefulsets`, `daemonsets`, `batch/jobs`, `cronjobs`,
  `autoscaling/hpas`). Requires `filter.namespace`.
  - With only a Role, the processor **cannot read cluster-scoped `namespaces`/`nodes`**, so no
    namespace or node labels and no `k8s.cluster.uid`.
  - Cluster-wide: a `ClusterRole` with `pods`, `namespaces` (and `nodes`) `get/watch/list`, plus `replicasets` as needed.
- **Browser spans through a proxy:** the connection IP is the ingress or proxy pod, not the browser.
  - With `from: connection` and a namespace filter, a proxy pod in another namespace simply won't
    match, so no attributes are added.
  - But if the proxy runs **in the watched namespace** (e.g. the backend pod forwards `/otlp`), browser
    spans would be tagged with that pod's metadata.
  - Fixes:
    - (a) Associate only by `resource_attribute` (`k8s.pod.uid` or `k8s.pod.ip`), set on the backend
      via the downward API (`OTEL_RESOURCE_ATTRIBUTES=k8s.pod.uid=$(POD_UID)`). Browser resources
      lack it and won't match.
    - (b) Run separate receivers or pipelines (e.g. `otlp/browser` on another port or path, or a
      `routing` connector on `service.name`) and apply `k8s_attributes` only to the backend pipeline.

### resource / transform for deployment attributes

- `resource` processor: `attributes: [{key: deployment.environment.name, value: prod, action: upsert},
  {key: service.version, value: ${env:GIT_SHA}, action: insert}, {key: vcs.ref.head.revision, ...}]`.
  Actions are insert, update, upsert, delete, hash and extract.
- `transform` processor (OTTL), e.g.:

  ```yaml
  trace_statements:
    - context: resource
      statements:
        - set(attributes["deployment.environment.name"], "prod")
  ```

  Conditional statements are possible, for example only for `service.name == "web"`.
- Honeycomb's skill example still uses the legacy `deployment.environment` key; prefer `.name`.

### Export to Grafana Cloud

```yaml
extensions:
  basic_auth/grafana:            # (deprecated alias: basicauth/grafana)
    client_auth:
      username: "${env:GRAFANA_CLOUD_STACK_ID}"
      password: "${env:GRAFANA_CLOUD_OTLP_TOKEN}"   # or password_file (watched for rotation)
exporters:
  otlp_http/grafana:             # (deprecated alias: otlphttp/grafana)
    endpoint: https://otlp-gateway-prod-us-east-0.grafana.net/otlp
    auth:
      authenticator: basic_auth/grafana
service:
  extensions: [basic_auth/grafana]
```

basic_auth also supports `username_file`/`password_file` (watched for changes) and `secret_provider`.
https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/basicauthextension

### OTLP receiver: CORS and paths

- `receivers.otlp.protocols.http.cors: { allowed_origins: [...], allowed_headers: [...], max_age: 7200 }`.
  - **Don't use `["*"]`**: the response sets `Access-Control-Allow-Credentials: true`, so use
    `https://*` style patterns instead.
  - With the browser posting **same-origin** to `/otlp/v1/traces` through a reverse proxy, no CORS
    is needed.
- The proxy must strip `/otlp` (the receiver's default path is `/v1/traces`), or set
  `protocols.http.traces_url_path: /otlp/v1/traces` (also `metrics_url_path` and `logs_url_path`).
- `max_request_body_size` defaults to 20 MiB, checked on the decompressed size.
- Sources: https://github.com/open-telemetry/opentelemetry-collector/blob/main/config/confighttp/README.md ,
  https://github.com/open-telemetry/opentelemetry-collector/blob/main/receiver/otlpreceiver/README.md
