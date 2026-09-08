# Policy di sicurezza / Security policy

[Italiano](#italiano) · [English](#english) ·
[Progettazione della sicurezza](docs/security.md)

Azure Bing Assistant è un progetto indipendente, non un prodotto Microsoft
ufficiale. / Azure Bing Assistant is an independent project, not an official
Microsoft product.

<a id="italiano"></a>

## Italiano

### Segnalare una vulnerabilità

Segnalare privatamente al proprietario del repository o al canale di sicurezza
approvato dall'organizzazione. Non aprire issue pubbliche con credenziali,
identificatori tenant, endpoint, documenti, dati personali, dettagli di exploit
o istruzioni che aumentino il rischio.

Quando è sicuro farlo, includere:

- versione/commit interessato e configurazione rilevante senza segreti;
- impatto e prerequisiti;
- passaggi minimi di riproduzione;
- contenimento o correzione suggeriti.

Non viene dichiarata una finestra pubblica di supporto o una SLA. Il maintainer
valuterà la segnalazione nel canale privato disponibile. Se una credenziale è
esposta, ruotarla/revocarla immediatamente, contenere l'accesso e seguire il
processo incidenti; eliminare una riga Git non è una bonifica sufficiente.

### Responsabilità critiche del cliente

Il chatbot non richiede login visitatore e una nuova distribuzione è
intenzionalmente pubblica. Il cliente deve:

1. decidere l'accesso e proteggere, se necessario, pagina, `/api/chat` e ogni
   endpoint backend diretto;
2. non considerare CORS o `Referer` controlli di accesso;
3. verificare separatamente eventuale Easy Auth/rete esistente: il template
   incrementale non la disabilita o elimina;
4. gestire costi e abusi con limiti, budget, alert e monitoraggio adeguati;
5. completare valutazioni di privacy, compliance, threat model, content safety,
   accessibilità, retention e incident response.

Il repository non fornisce garanzie di conformità o residenza geografica e non
installa gateway, WAF, CAPTCHA o rate limiter. Bing può trattare dati fuori dai
confini Azure descritti nella [guida di sicurezza](docs/security.md#italiano).

### Confini da preservare

- Operatore e backend usano `DefaultAzureCredential`/Managed Identity e ruoli
  minimi; le credenziali dell'operatore non vanno distribuite.
- Accesso Blob anonimo, Shared Key e autenticazione locale Search restano
  disabilitati.
- Documenti, web e output modello sono non attendibili; non inserire HTML del
  modello nel DOM.
- Non committare `.env`, stato azd, token, chiavi, connection string, file
  parametri, ARM JSON, dati tenant o documenti.
- La chiave Bing resta nella connessione gestita Foundry e non deve diventare
  input, output, setting o log.

Prima dell'uso eseguire test, Bicep build/what-if, dependency e access review e
verifiche nel tenant. API preview, quote, modelli, strumenti, ruoli e policy
regionali non sono attestati da questo repository.

---

<a id="english"></a>

## English

### Report a vulnerability

Report privately to the repository owner or the organization's approved
security channel. Do not open public issues containing credentials, tenant
identifiers, endpoints, documents, personal data, exploit details, or
instructions that increase risk.

When safe, include:

- affected version/commit and relevant configuration without secrets;
- impact and prerequisites;
- minimal reproduction steps;
- suggested containment or remediation.

No public support window or SLA is claimed. The maintainer will assess the
report through the available private channel. If a credential is exposed,
rotate/revoke it immediately, contain access, and follow the incident process;
deleting a Git line is not sufficient remediation.

### Critical customer responsibilities

The chatbot requires no visitor login, and a new deployment is intentionally
public. The customer must:

1. decide access and, when required, protect the page, `/api/chat`, and every
   direct backend endpoint;
2. not treat CORS or `Referer` as access controls;
3. assess existing Easy Auth/networking separately: the incremental template
   does not disable or delete it;
4. manage cost and abuse with suitable limits, budgets, alerts, and monitoring;
5. complete privacy, compliance, threat-model, content-safety, accessibility,
   retention, and incident-response reviews.

The repository provides no compliance or geographic-residency guarantee and
installs no gateway, WAF, CAPTCHA, or rate limiter. Bing may process data outside
the Azure boundaries described in the [security guide](docs/security.md#english).

### Boundaries to preserve

- Operator and backend use `DefaultAzureCredential`/Managed Identity and
  least-privilege roles; operator credentials must not be deployed.
- Anonymous Blob access, Shared Key, and Search local authentication remain
  disabled.
- Documents, web content, and model output are untrusted; do not inject model
  HTML into the DOM.
- Do not commit `.env`, azd state, tokens, keys, connection strings, parameter
  files, ARM JSON, tenant data, or documents.
- The Bing key stays in the managed Foundry connection and must not become an
  input, output, setting, or log value.

Before use, run tests, Bicep build/what-if, dependency and access review, and
tenant verification. Preview APIs, quotas, models, tools, roles, and regional
policy are not attested by this repository.
