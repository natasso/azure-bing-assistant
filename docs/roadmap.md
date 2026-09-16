# Roadmap e verifiche tenant / Roadmap and tenant verification

[Italiano](#italiano) · [English](#english) · [README](../README.md)

<a id="italiano"></a>

## Italiano

### Implementato nel repository

- Chat FastAPI con frontend locale HTML/CSS/JavaScript, limiti di input,
  cancellazione, errori limitati e rotte upload rifiutate.
- `web_search.filters.allowed_domains` obbligatorio in entrambe le modalità, senza risorsa Bing standalone.
- `off` come sola disattivazione della ricerca documentale.
- `searchBlob` opzionale con Storage, Azure AI Search, indice/indicizzatore e
  strumento Search aggiuntivo; Bing resta disponibile.
- Continuazione Foundry Responses con `previousResponseId` opaco conservato in
  memoria dal browser, senza session store, cookie, HMAC, chiavi o lock.
- Managed Identity e RBAC per Foundry/Search/Blob; Shared Key, accesso Blob
  anonimo e autenticazione locale Search disabilitati.
- Nessun login visitatore gestito dall'app. Nuove distribuzioni pubbliche;
  nessun comando che disabiliti Easy Auth o rete esistente.
- Installer interattivo con discovery Azure, piano, consenso Bing e
  `searchBlob` opt-in; dry-run offline e percorso non interattivo.
- Testi UI configurabili, lista suggerimenti anche vuota e temi chiaro/scuro
  basati sui token `--cp-*`.

“Implementato” descrive il codice e i template presenti, non un'attestazione che
un deployment live o una verifica tenant siano riusciti.

### Verifiche ancora necessarie per ogni tenant

1. Confermare provider, quote, disponibilità regionale,
   modello/versione/SKU/capacità, Marketplace e content filter.
2. Eseguire Bicep build e what-if; verificare role definition e role assignment
   minimi, target e output prima del deploy.
3. Validare end-to-end le API Foundry, la versione agente, Foundry Responses e
   la compatibilità del modello con Grounding with Bing Search.
4. Accettare e rivedere termini, prezzi, privacy, requisiti di visualizzazione
   citazioni e flusso dati Bing fuori dai confini Azure.
5. Definire la policy cliente per pagina e API dirette; testare esplicitamente
   `/api/chat`, rete, DNS e, se richiesti, endpoint privati.
6. Configurare budget, alert, diagnostica, logging senza payload sensibili,
   protezioni antiabuso, retention, incident response e cancellazione.
7. Per `searchBlob`, caricare documenti di prova autorizzati e verificare Managed
   Identity, data source, indicizzatore, errori, conteggio, recupero e retention.
8. Eseguire threat model, review privacy/compliance, accessibilità, browser,
   mobile, tema scuro, carico, resilienza e rollback.

Il progetto usa l'API data-plane Foundry `v1`; le connessioni Search progetto
usano `2026-05-01`. Contratti, supporto regionale e comportamento vanno
riconfermati al momento del deployment. Nessuna voce autorizza a dichiarare
“production ready” il sistema.

### Domini rigorosi ed esclusioni

Il filtro dominio nativo è implementato con classi SDK reali e verificato offline,
con versione agente verificata/fissata e rifiuto di evidenza fuori dominio o
metadati mancanti. Non richiede Search o Custom Search. L'accettazione e
l'enforcement live per modello/regione, incluso `open_page`, restano da provare
manualmente: i test locali non attestano fetch del servizio. Il flag
`--strict-websites` è un alias; il filtro è sempre obbligatorio. Consultare
[migrazione e verifiche](configuration.md#migrazione-e-verifica-manuale-del-filtro).

Crawler, ingestione siti, upload/allegati chat, OCR, NFS, source picker,
localizzazione automatica, gateway, WAF, CAPTCHA, rate limiting e nuovi servizi
a pagamento non sono impegni di roadmap. Qualsiasi proposta futura deve
esplicitare costi, proprietà operativa, privacy e test.

---

<a id="english"></a>

## English

### Implemented in the repository

- FastAPI chat with local HTML/CSS/JavaScript, input limits, cancellation,
  bounded errors, and rejected upload routes.
- Required `web_search.filters.allowed_domains` in both modes, without a standalone Bing resource.
- `off` as document-search off only.
- Optional `searchBlob` with Storage, Azure AI Search, index/indexer, and an
  additional Search tool; Bing remains available.
- Foundry Responses continuation using an opaque browser-memory
  `previousResponseId`, without a session store, cookie, HMAC, key, or lock.
- Managed Identity and RBAC for Foundry/Search/Blob; Shared Key, anonymous Blob
  access, and Search local authentication disabled.
- No application-managed visitor login. New deployments are public; no command
  disables existing Easy Auth or networking.
- Interactive Azure discovery, plan, Bing consent, and opt-in `searchBlob`;
  offline dry-run and a non-interactive path.
- Configurable UI text, an explicitly empty suggestion list, and light/dark
  themes based on `--cp-*` tokens.

“Implemented” describes repository code and templates. It is not evidence that
a live deployment or tenant verification succeeded.

### Verification still required for every tenant

1. Confirm providers, quota, regional availability,
   model/version/SKU/capacity, Marketplace, and content filters.
2. Run Bicep build and what-if; verify least-privilege role definitions and
   assignments, targets, and outputs before deployment.
3. Validate Foundry APIs, agent version, Foundry Responses, and model
   compatibility with Grounding with Bing Search end to end.
4. Accept and review current Bing terms, pricing, privacy, citation-display
   requirements, and data flow outside Azure boundaries.
5. Define customer policy for the page and direct APIs; explicitly test
   `/api/chat`, networking, DNS, and private endpoints when required.
6. Configure budgets, alerts, diagnostics, payload-safe logging, abuse controls,
   retention, incident response, and deletion.
7. For `searchBlob`, upload authorized test documents and verify Managed
   Identity, data source, indexer, errors, count, retrieval, and retention.
8. Perform threat modeling, privacy/compliance review, accessibility, browser,
   mobile, dark-theme, load, resilience, and rollback testing.

The project uses Foundry data-plane API `v1`; Search project connections use `2026-05-01`.
Contracts, regional support, and behavior must be reconfirmed at deployment
time. Nothing in this list supports a “production ready” claim.

### Strict domains and exclusions

Native domain filtering is implemented and checked offline using real SDK classes,
agent-version verification/pinning, and rejection of outside evidence or missing
metadata. No Search or Custom Search setup is required. Live model/region acceptance
and enforcement, including `open_page`, remain manual verification work: local
tests cannot attest service fetches. `--strict-websites` is an alias; restriction
is always required. See [migration and verification](configuration.md#migration-and-manual-filter-verification).

Crawling, website ingestion, chat upload/attachments, OCR, NFS, source pickers,
automatic localization, gateways, WAF, CAPTCHA, rate limiting, and new paid
services are not roadmap commitments. Any future proposal must state cost,
operational ownership, privacy, and test implications.
