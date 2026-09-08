# Progettazione della sicurezza / Security design

[Italiano](#italiano) · [English](#english) ·
[Policy di segnalazione](../SECURITY.md) · [README](../README.md)

<a id="italiano"></a>

## Italiano

### Modello di accesso intenzionale

L'applicazione non implementa login o sessioni per i visitatori. Una nuova
distribuzione rende raggiungibili la pagina, `/api/config`, `/api/chat`,
`/health` e gli altri endpoint App Service senza header `Authorization` o
cookie applicativi.

Questa scelta non protegge automaticamente il servizio:

- il cliente deve decidere se l'accesso debba essere pubblico o limitato;
- qualsiasi policy deve coprire **pagina, `/api/chat` e tutti gli endpoint
  backend diretti**, non soltanto il sito o frame che incorpora la chat;
- CORS e `Referer` non sono autenticazione né controllo di accesso;
- HTTPS protegge il trasporto ma non stabilisce chi può usare il chatbot;
- la rimozione di `authsettingsV2` dal template incrementale non disabilita,
  azzera o elimina Easy Auth o policy di rete già presenti. Il cliente deve
  valutarle e modificarle separatamente.

Il repository non installa gateway, WAF, CAPTCHA, rate limiting o chiavi API.
Ogni richiesta pubblica può consumare token modello e chiamate Bing: limiti,
budget, alert, monitoraggio e risposta agli abusi sono responsabilità del
cliente.

### Identità operatore e servizi

L'accesso dei visitatori non va confuso con le identità Azure:

- l'amministratore usa `az login`, `azd auth login` e
  `DefaultAzureCredential` per discovery, ARM e post-deploy;
- l'App Service usa una Managed Identity `SystemAssigned` con un ruolo runtime
  Foundry;
- in `searchBlob`, la Managed Identity di Search legge Blob e quella del
  progetto Foundry legge l'indice.

L'account Foundry e Search hanno autenticazione locale disabilitata. Lo Storage
disabilita Shared Key e accesso Blob anonimo; il container `documents` è
privato. Gli endpoint di servizio restano pubblici nel template generico, quindi
la rete e gli endpoint privati vanno aggiunti e verificati se richiesti dalla
policy del cliente. Le credenziali dell'operatore non vengono distribuite
nell'app.

### Dati, conversazioni e browser

Il browser invia testo a FastAPI, mai direttamente a Foundry. Conserva solo
l'ultimo `previousResponseId` opaco nella memoria della scheda. Il backend ne
limita lunghezza e caratteri e lo passa invariato a Foundry; non lo decodifica,
firma, associa a un utente, registra o persiste. Non esistono cookie di sessione,
database conversazioni, HMAC, chiavi custom, Redis, lease o lock.

L'ID è simile a un bearer reference: chi può osservare o riutilizzare il valore
potrebbe tentare una continuazione. Usare HTTPS, evitare logging del payload e
applicare all'API l'eventuale policy del cliente. “New chat” cancella l'ID nel
browser. Cancel preserva l'ultimo ID già consegnato; un'operazione remota già
accettata può terminare in best effort.

Messaggi fino a 8.000 caratteri e ID fino a 4.096 sono accettati; richieste non
valide ricevono errori generici. Le rotte di upload più probabili restituiscono
404. Questo limita la superficie, ma non sostituisce controlli di consumo o
sicurezza perimetrale.

### Contenuti e citazioni non attendibili

Documenti, web pubblico, prompt, output del modello e metadati di citazione sono
non attendibili. Il frontend usa `textContent`/nodi di testo. I riferimenti
documentali privati vengono trasformati in etichette generiche e percorsi opachi;
host infrastrutturali Azure noti non vengono restituiti come citazioni.

Gli URL pubblici Bing/web validati sono un'eccezione necessaria ai requisiti di
visualizzazione e si aprono con `noopener noreferrer`. Gli utenti devono
verificare fonti, data e contesto. Né la configurazione Bing né `searchBlob`
dimostrano che uno strumento sia stato usato in una risposta.

### Bing, privacy e conformità

Grounding with Bing Search può inviare query, parametri, configurazione e
credenziali di servizio fuori dai confini geografici e di compliance Azure; il
Microsoft Data Protection Addendum non si applica a tale elaborazione Bing.
Esaminare termini, privacy, idoneità, prezzi e controlli amministrativi correnti.

Questo progetto non certifica conformità, residenza geografica, sicurezza,
accessibilità o idoneità produttiva per università o altre organizzazioni. Il
cliente deve eseguire la propria valutazione legale, privacy, threat model,
content-safety, retention e incident response. Non inserire dati personali,
sensibili o riservati senza una base e controlli approvati.

### Segreti e configurazione

Non committare `.env`, directory azd, token, password, chiavi, connection
string, file parametri, ARM JSON generato, endpoint privati, documenti o export
tenant. La chiave Bing viene risolta all'interno di ARM e scritta solo nella
connessione Foundry gestita; non è input, output o setting applicativo.

I setting `UI_*` sono non segreti. Identificatori di sottoscrizione, resource
group e risorse non sono password ma possono essere dati organizzativi:
condividerli solo nei canali approvati.

### Verifica prima dell'uso

1. Eseguire test, compilazione Bicep, what-if e dependency review.
2. Verificare target, ruoli minimi, quota, regioni, API preview e policy modello.
3. Testare la policy cliente su pagina e chiamata diretta a `/api/chat`.
4. Verificare budget/alert, carico, contenuti, citazioni, accessibilità e mobile.
5. Per `searchBlob`, verificare accesso privato, indicizzatore, errori e
   retention dei documenti.
6. Definire diagnostica, logging senza payload sensibili, cancellazione,
   backup/export e procedura incidenti.

Sono verifiche da eseguire nel tenant: il repository non dichiara che siano già
state completate.

---

<a id="english"></a>

## English

### Intentional access model

The application implements no visitor login or session. A new deployment makes
the page, `/api/config`, `/api/chat`, `/health`, and other App Service endpoints
reachable without an `Authorization` header or application cookie.

This choice does not automatically protect the service:

- the customer decides whether access should be public or restricted;
- any policy must cover the **page, `/api/chat`, and every direct backend
  endpoint**, not only the site or frame embedding chat;
- CORS and `Referer` are not authentication or access control;
- HTTPS protects transport but does not identify who may use the chatbot;
- removing `authsettingsV2` from the incremental template does not disable,
  reset, or delete existing Easy Auth or network policy. The customer must
  assess and change it separately.

The repository installs no gateway, WAF, CAPTCHA, rate limiter, or API key.
Every public request can consume model tokens and Bing calls. Limits, budgets,
alerts, monitoring, and abuse response are customer responsibilities.

### Operator and service identities

Visitor access must not be confused with Azure identities:

- the administrator uses `az login`, `azd auth login`, and
  `DefaultAzureCredential` for discovery, ARM, and post-deployment work;
- App Service uses a `SystemAssigned` Managed Identity with a Foundry runtime
  role;
- in `searchBlob`, Search Managed Identity reads Blob and Foundry project
  Managed Identity reads the index.

Foundry and Search local authentication are disabled. Storage disables Shared
Key and anonymous Blob access; the `documents` container is private. Service
endpoints remain public in the generic template, so networking and private
endpoints must be added and verified when customer policy requires them.
Operator credentials are not deployed into the app.

### Data, conversations, and browser

The browser sends text to FastAPI, never directly to Foundry. It keeps only the
latest opaque `previousResponseId` in tab memory. The backend bounds its length
and characters and passes it unchanged to Foundry; it does not decode, sign,
bind to a user, log, or persist it. There is no session cookie, conversation
database, HMAC, custom key, Redis, lease, or lock.

The ID is bearer-like: anyone able to observe or reuse it could attempt a
continuation. Use HTTPS, avoid payload logging, and apply any customer policy to
the API. “New chat” clears the browser value. Cancel preserves the last
delivered ID; a remote operation already accepted may finish on a best-effort
basis.

Messages are limited to 8,000 characters and IDs to 4,096; invalid requests get
generic errors. Likely upload routes return 404. This reduces surface area but
does not replace consumption or perimeter controls.

### Untrusted content and citations

Documents, the public web, prompts, model output, and citation metadata are
untrusted. The frontend uses `textContent`/text nodes. Private-document
references are projected to generic labels and opaque paths; known Azure
infrastructure hosts are not returned as citations.

Validated public Bing/web URLs are an exception required for display and open
with `noopener noreferrer`. Users must verify source, date, and context. Neither
Bing configuration nor `searchBlob` proves a tool was used for a given answer.

### Bing, privacy, and compliance

Grounding with Bing Search may send queries, parameters, configuration, and
service credentials outside Azure compliance and geographic boundaries; the
Microsoft Data Protection Addendum does not apply to that Bing processing.
Review current terms, privacy, eligibility, pricing, and administrative
controls.

This project certifies no compliance, geographic residency, security,
accessibility, or production suitability for universities or other
organizations. Customers must perform their own legal, privacy, threat-model,
content-safety, retention, and incident-response assessments. Do not enter
personal, sensitive, or confidential data without an approved basis and
controls.

### Secrets and configuration

Do not commit `.env`, azd directories, tokens, passwords, keys, connection
strings, parameter files, generated ARM JSON, private endpoints, documents, or
tenant exports. The Bing key is resolved inside ARM and written only to the
managed Foundry connection; it is not an application input, output, or setting.

`UI_*` settings are non-secret. Subscription, resource-group, and resource
identifiers are not passwords but may be organizational data; share them only
through approved channels.

### Pre-use review

1. Run tests, Bicep build, what-if, and dependency review.
2. Verify targets, least-privilege roles, quota, regions, preview APIs, and model
   policy.
3. Test customer policy on both the page and a direct `/api/chat` call.
4. Verify budgets/alerts, load, content, citations, accessibility, and mobile.
5. For `searchBlob`, verify private access, indexer, errors, and document
   retention.
6. Define diagnostics, payload-safe logging, deletion, backup/export, and
   incident procedures.

These checks must be performed in the tenant; the repository does not claim
that they are already complete.
