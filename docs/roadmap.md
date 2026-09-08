# Roadmap e verifiche tenant / Roadmap and tenant verification

[Italiano](#italiano) · [English](#english) · [README](../README.md)

<a id="italiano"></a>

## Italiano

### Implementato nel repository

- Chat FastAPI con frontend locale HTML/CSS/JavaScript, limiti di input,
  cancellazione, errori limitati e rotte upload rifiutate.
- Grounding with Bing Search presente in entrambe le modalità.
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

Il progetto usa attualmente l'API progetto Foundry
`2025-06-01-preview`; le connessioni progetto usano `2026-05-01` e la risorsa
Bing `2020-06-10`. Contratti, supporto regionale e comportamento vanno
riconfermati al momento del deployment. Nessuna voce autorizza a dichiarare
“production ready” il sistema.

### Domini rigorosi ed esclusioni

I siti Bing configurati restano preferenze consultive. Per un filtro rigoroso
servirebbe una configurazione Bing Custom Search pubblicata e verificata oppure
un'architettura Azure AI Search/Foundry IQ Web Knowledge Source con
`allowedDomains` e knowledge base. `--strict-websites` continua a fallire finché
un percorso supportato non viene progettato e convalidato nel tenant.

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
- Grounding with Bing Search in both modes.
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

The project currently uses Foundry project API `2025-06-01-preview`; project
connections use `2026-05-01`, and the Bing resource uses `2020-06-10`.
Contracts, regional support, and behavior must be reconfirmed at deployment
time. Nothing in this list supports a “production ready” claim.

### Strict domains and exclusions

Configured Bing sites remain advisory preferences. Strict filtering would
require a published, verified Bing Custom Search or an Azure AI Search/Foundry
IQ Web Knowledge Source architecture with `allowedDomains` and a knowledge
base. `--strict-websites` continues to fail until a supported path is designed
and tenant-validated.

Crawling, website ingestion, chat upload/attachments, OCR, NFS, source pickers,
automatic localization, gateways, WAF, CAPTCHA, rate limiting, and new paid
services are not roadmap commitments. Any future proposal must state cost,
operational ownership, privacy, and test implications.
