# Configuration / Configurazione

[English guide](#english) · [Languages](#languages) · [Italiano](#italiano) · [README](../README.md)

## International university setup

Azure Bing Assistant is intended for universities internationally whose public
portals change frequently. Admissions, deadlines, programmes, student services,
and regulations are maintained by the university on its authoritative websites.
Domain-filtered Bing web grounding can use indexed public pages without first
duplicating that portal content in a separate knowledge base. This reduces
duplicated content maintenance; it does not replace university content owners.
Examples here use fictitious universities, reserved example domains, and
placeholders rather than customer deployment details.

**Public-web limits:** Bing indexing and source availability can lag behind
changes. Neither immediate freshness nor complete crawling/search coverage is
guaranteed. Authenticated pages are not searchable through this path. Not every
model answer uses search, and generated answers can be wrong: open citations,
check dates and content, and use the authoritative university pages for deadlines
and procedures. Do not submit sensitive information.

Start with the [English installation guide](#english), then review:

1. [Languages and native installer inputs](#languages).
2. [Required domain and subdomain policy](#domains-one-at-a-time).
3. [Costs and assumptions](#cost-estimate-en).
4. [Text and visual customization](#customization-en) and [embedding](#embed-chat-en).
5. [Security, privacy, and access responsibilities](security.md#english).

**Safe deployment boundaries remain unchanged.** Authorized public domains are
mandatory; there is no unfiltered web fallback. The wizard requires an explicit
subdomain decision: the native filter includes subdomains, so a host-only/No
policy stops installation before terms or Azure writes. Document search and
Blob Storage are optional and **off by default** (`off`); `searchBlob` adds
administrator-managed, indexed documents and costs, not chat uploads. Bing
terms, costs, and data flow outside Azure compliance/geographic boundaries
require explicit acceptance. Protect the complete UI/API ingress as needed;
CORS is not access control. Validate model/region/tool support and live domain
enforcement before exposing a deployment.

<a id="languages"></a>

## Languages, native labels, and RTL

The same nine packaged locales cover the **full installer and frontend**,
including prompts, help, validation context, summaries, progress, confirmations,
controls, accessibility copy, and generated citation labels:

| Code | Language | Menu label | Native Yes / No | Direction |
|---|---|---|---|---|
| `it` | Italian (default) | Italiano | `sì` / `no` | LTR |
| `en` | English | English | `yes` / `no` | LTR |
| `fr` | French | Français / French | `oui` / `non` | LTR |
| `es` | Spanish | Español / Spanish | `sí` / `no` | LTR |
| `pt` | European Portuguese | Português / Portuguese | `sim` / `não` | LTR |
| `el` | Greek | Ελληνικά / Greek | `ναι` / `όχι` | LTR |
| `he` | Hebrew (Israel) | עברית / Hebrew | `כן` / `לא` | RTL |
| `ar` | Arabic | العربية / Arabic | `نعم` / `لا` | RTL |
| `tr` | Turkish | Türkçe / Turkish | `evet` / `hayır` | LTR |

Italian remains the initial default. Existing Italian/English menu entries
(`it`, `en`) and saved configurations remain compatible; the additional
languages extend the existing choices. A valid saved wizard language becomes
the next default. An explicit `--ui-language` selects the installer language
without a picker. Use **one** code, not the whole list:

```powershell
# Choose one of: it, en, fr, es, pt, el, he, ar, tr
python -m azure_bing_assistant install --ui-language fr
python -m azure_bing_assistant install --help
```

The first command starts the interactive installer; it still requires domain
policy, Bing terms, and final approval before Azure changes. For runtime
configuration, use the same code in `UI_LANGUAGE`, for example `UI_LANGUAGE=he`
or `UI_LANGUAGE=pt`. See [existing deployment updates](#ui-text-en) before
changing an App Service. Code changes/catalog additions require deploying the
updated package; changing a setting on an older package does not add languages.

Yes/no questions accept the native full words above. English `y`/`yes` and
`n`/`no` remain compatibility inputs. Invalid input repeats only the same
question; Enter uses the displayed default. **Terms and final approval always
default to No and require fresh explicit consent**, regardless of language.
Language selection never weakens domain or subdomain enforcement.

For Hebrew and Arabic, the frontend uses right-to-left (RTL) layout while
URLs, code, and technical identifiers remain left-to-right and readable.
On Windows, the Python CLI configures stdin, stdout, and stderr as **UTF-8**,
including redirected output, to support all native scripts. No user environment
configuration is needed for the CLI. Older PowerShell pipeline consumers should
read UTF-8. Use a Unicode-capable terminal and suitable fonts: font coverage and
bidirectional rendering still vary, and RTL terminal layout is not guaranteed.
This encoding behavior does not change the Italian default.
Azure names, SKUs, region identifiers, JSON keys, and provider diagnostics are
not translated, but installer phase/error context is localized.

The central locale registry and nine JSON catalogs under
`src/azure_bing_assistant/locales` are the shared source; frontend translations
are generated from those same catalogs rather than maintained independently.
Keep placeholders and technical identifiers intact when maintaining catalogs,
and regenerate `app/frontend/locales.js` after catalog changes. From the
repository root:

```powershell
python .\scripts\build_frontend_locales.py
python .\scripts\build_frontend_locales.py --check
```

The first command updates the local generated file; `--check` verifies exact
catalog parity without writing. The browser loads this same-origin bundle,
not a third-party translation service. Include the generated artifact in the
deployment package: the server serves it at `/locales.js` and does not regenerate
it at runtime.

The selected language controls the UI and installer, **not the language of all
model responses**: the model remains instructed to answer in the user's
language unless asked otherwise. There is no per-visitor selector or automatic
browser-language selection. Customer `UI_*` overrides and provider-supplied
source titles are literal, not automatically translated; generated citation
labels are localized without changing source URLs.

These are packaged capabilities, not a claim that an existing live university
deployment has been updated or verified in all nine languages. The
documentation is English-first with a retained Italian guide; it is not
translated into all nine languages.

---

<a id="italiano"></a>

## Italiano

<a id="ruoli-it"></a>

### Utenti e amministratori

- **Utente finale:** apre la pagina e usa la chat. Non deve installare software,
  fornire un client ID, registrare un'applicazione o effettuare un login Entra
  gestito da questa applicazione.
- **Amministratore installatore:** accede ad Azure, sceglie risorse e modello,
  accetta termini e costi Bing, distribuisce l'app e, se necessario, gestisce
  documenti, grafica e policy di ingresso.

L'autenticazione dell'operatore (`az login`, `azd auth login`,
`DefaultAzureCredential`) e la Managed Identity del backend sono indipendenti
dall'accesso dei visitatori e restano necessarie.

<a id="installazione-operatore"></a>

### Prerequisiti dell'operatore

- Windows PowerShell e Git.
- Python 3.11 o 3.12.
- Azure CLI e Azure Developer CLI (`azd`).
- Accesso al repository pubblico
  `https://github.com/natasso/azure-bing-assistant`.
- Sottoscrizione Azure a pagamento, provider applicabili registrati, quota del
  modello e autorizzazioni per creare risorse, connessioni e role assignment.
- Visibilità dei ruoli Foundry User (o nome di rollout documentato), Storage
  Blob Data Reader e Search Index Data Reader quando applicabili.
- Sessioni `az` e `azd` con un account autorizzato nello stesso tenant.

L'identità che esegue l'installer deve anche avere **Foundry User** (o permessi
data-plane equivalenti, inclusa la scrittura degli agenti) sul progetto Foundry.
**Owner** o **Contributor** da soli non concedono questi permessi. Il ruolo
assegnato alla Managed Identity dell'app non autorizza l'installatore.
Per un progetto nuovo, un amministratore può concedere il ruolo a uno scope
superiore appropriato prima dell'installazione, oppure al solo progetto dopo la
creazione delle risorse. Attendere la propagazione RBAC, che può richiedere
diversi minuti, poi riprendere con
`python -m azure_bing_assistant deploy --environment <nome-installazione> --ui-language it`.
Questo comando riusa gli output salvati senza ricreare l'infrastruttura.

I nomi di modello, versioni, SKU, capacità, sottoscrizioni e role definition ID
negli esempi non sono valori convalidati: sostituirli con valori reali del tenant.
Azure resta autorevole per disponibilità regionale, quota e compatibilità.

### Preparazione da PowerShell

Eseguire dalla directory in cui si vuole clonare il progetto:

```powershell
git clone https://github.com/natasso/azure-bing-assistant.git
Set-Location .\azure-bing-assistant
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
az login
azd auth login
python -m azure_bing_assistant doctor
```

Se è installato soltanto Python 3.11, sostituire il comando di creazione
dell'ambiente con `py -3.11 -m venv .venv`; attivazione e comandi successivi
restano invariati.

Il repository pubblico può essere clonato senza autenticazione GitHub. Se
PowerShell blocca lo script di attivazione, usare il processo aziendale approvato
oppure eseguire direttamente `.\.venv\Scripts\python.exe -m ...`.

Per sviluppo e test, separatamente:

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

L'entry point installato `azure-bing-assistant` e
`python -m azure_bing_assistant` sono equivalenti.

### Installazione interattiva consigliata

```powershell
python -m azure_bing_assistant install
```

Il wizard:

1. legge da Azure sottoscrizioni abilitate, gruppi di risorse, regioni,
   combinazioni modello/versione/formato/SKU e ruoli;
2. chiede nomi, capacità e domini pubblici autorizzati obbligatori;
3. propone **Siti autorizzati** per impostazione predefinita e chiede se aggiungere
   Blob Storage e Azure AI Search;
4. richiede l'accettazione di costi, termini e flusso dati Bing;
5. mostra un piano e chiede conferma prima delle modifiche.

Alla prima esecuzione il selettore iniziale con nove etichette native propone **Italiano** premendo Invio. La lingua
scelta controlla sia il chatbot sia tutte le domande, gli aiuti, i riepiloghi e
le conferme dell'installer. `--ui-language` accetta uno fra `it`, `en`, `fr`,
`es`, `pt`, `el`, `he`, `ar`, `tr`, salta il selettore e preseleziona la lingua
anche nel comando interattivo. Le voci `it`/`en` restano compatibili; vedere
[lingue, risposte native e RTL](#languages). Nomi Azure, SKU, identificatori regionali,
chiavi JSON e diagnostica tecnica del provider restano invariati; gli errori del
provider sono accompagnati dal contesto della fase nella lingua scelta.
Gli altri argomenti `--ui-*` per testi personalizzati vengono elaborati solo con
`--non-interactive`.

Ogni domanda mostra prima formato, limiti e valore predefinito (se presente).
Un valore non valido richiede **solo lo stesso campo**, mantenendo in memoria le
risposte precedenti senza ripetere le letture Azure già completate. Il nome
tecnico del chatbot e il nome dell'installazione richiedono **3–24 lettere
minuscole, cifre o trattini, iniziando con una lettera**; non vengono corretti
automaticamente. Il titolo pubblico può contenere spazi e si configura
separatamente nei campi `UI_*`. Il gruppo di risorse ammette 1–90 lettere ASCII,
cifre, punti, underscore, parentesi o trattini. Il nome della distribuzione
identifica il percorso del modello sull'endpoint, non il modello di catalogo:
1–128 lettere ASCII, cifre, punti, underscore o trattini, con lettera o cifra
iniziale (es. `chat-model`). Sono controlli locali: esistenza, autorizzazioni,
quota e compatibilità Azure restano da verificare con il servizio.

Esempio di correzione immediata (estratto):

```text
Nome tecnico del chatbot: Università Esempio
Nome tecnico del chatbot deve contenere 3-24 lettere minuscole, cifre o trattini e iniziare con una lettera
Nome tecnico del chatbot: assistente-demo
```

Nei menu, un numero non valido ripropone la stessa scelta; Invio seleziona
la lingua proposta nel menu iniziale; gli altri menu hanno un valore predefinito
solo quando una scelta precedente salvata è ancora disponibile.
Una capacità non valida ripropone solo la capacità, senza sostituirla
silenziosamente con il valore predefinito. Invio nelle domande sì/no accetta il
valore mostrato: termini e conferma finale hanno **sempre No** come predefinito;
il rifiuto interrompe l'installazione.
Ctrl+C/EOF annulla anche durante una correzione. Gli argomenti non interattivi
errati restano errori singoli, senza domande. Riavviare manualmente un wizard
già aperto: con l'installazione editable non serve reinstallare il pacchetto.

#### Riprendere le risposte dell'installer

Solo `install` interattivo salva ogni risposta valida nella bozza JSON versionata
`.azure/installer-draft.json`, relativa alla directory del progetto corrente.
È un **file locale in chiaro, privato ed escluso da Git**: contiene lingua, ID
tenant/sottoscrizione selezionati, nome/scelta di creazione del gruppo, regione,
identità modello/versione/formato/SKU, capacità, nomi tecnici di chatbot,
installazione e distribuzione, scelta Search e regole ordinate dei domini con
policy sottodomini e avanzamento della raccolta. Non contiene credenziali,
token, chiavi, risposte di servizi, ID di conversazioni o consensi; non legge `.env`.
Non introduce sessioni runtime o memoria delle conversazioni.

Dopo un errore o un annullamento, rieseguire lo stesso comando dalla stessa
directory: i campi mostrano i valori precedenti tra parentesi quadre e **Invio**
li riusa dopo convalida. Senza `--ui-language`, la lingua salvata diventa il
predefinito del selettore; un argomento esplicito cambia solo la lingua.
I menu confrontano gli ID con l'individuazione Azure corrente, non gli indici:
una scelta scomparsa viene segnalata e richiede una nuova selezione.
Cambiando tenant/sottoscrizione si eliminano i predefiniti dipendenti delle
risorse; cambiando regione/modello si riconvalidano modello/capacità.
Una capacità salvata fuori dai nuovi limiti viene segnalata, non corretta di nascosto.

I domini vengono riproposti uno alla volta: «aggiungere un altro» propone Sì
finché restano voci salvate, poi No. Un'interruzione non perde le voci ancora da
rivedere; rispondere esplicitamente No tronca invece la lista. Un dominio
modificato non eredita il Sì ai sottodomini di un dominio diverso. Le policy No
restano No e continuano a bloccare l'installazione senza ampliare l'autorizzazione.
**Termini Bing e conferma finale richiedono sempre un nuovo Sì esplicito.**

La bozza resta dopo errori di convalida finale, provider, provisioning o package
deployment, rifiuti, Ctrl+C/EOF; viene eliminata solo dopo la distribuzione completa
riuscita. Un errore nella sola eliminazione produce un avviso locale, non un falso
fallimento Azure. Errori di lettura/salvataggio fermano invece l'installer.
Per ripartire (anche con JSON corrotto o versione non supportata):

```powershell
python -m azure_bing_assistant install --reset-wizard
```

Il comando elimina **solo** la bozza, non ambienti/configurazioni azd o login.
Non è combinabile con `--non-interactive`/`--dry-run`. Questi percorsi, `doctor`,
`plan`, `provision`, `deploy` e `--help` non leggono né scrivono la bozza.
Sono recuperabili solo risposte salvate dopo questa modifica: nessun recupero
retroattivo di una vecchia esecuzione fallita senza bozza. Riavviare manualmente
un wizard già aperto per caricare il codice aggiornato.

#### Domini, uno alla volta

Dopo l'opzione Search, inserire **un solo dominio o URL HTTPS radice**. Il wizard
convalida subito il valore, chiede esplicitamente se includere i sottodomini,
poi se aggiungere un altro dominio. Ripete queste domande fino al No finale
(massimo 100 domini distinti; al limite conclude il riepilogo). Valori vuoti o
non validi vengono richiesti nuovamente. Un duplicato normalizzato non sovrascrive
la scelta precedente: viene mostrata la policy già richiesta e occorre inserire
un dominio diverso, oppure annullare e riavviare per cambiarla.

**Limite del servizio:** `web_search.filters.allowed_domains` include sempre
tutti i sottodomini. **Sì è l'unica policy supportata dal motore attuale.**
No richiede «solo questo host»: il wizard conserva tale intenzione nel riepilogo
e **blocca l'installazione prima dei termini e di qualsiasi scrittura Azure**.
Non trasforma No in Sì, non applica filtri successivi come garanzia di blocco dei
fetch e non attiva servizi alternativi. È quindi una raccolta esplicita della
scelta, **non il supporto operativo dell'esclusione dei sottodomini**.

Le risposte italiane accettate sono `s`, `si`, `sì`, `n`, `no` (anche `y`/`yes`
per compatibilità). Le altre otto lingue accettano le rispettive
[risposte native](#languages). Invio usa il valore mostrato, **sempre No per termini e conferma finale**;
una risposta sì/no non valida ripropone la stessa domanda. EOF o interruzione
annullano senza proseguire. Il wizard già aperto va **riavviato manualmente**
per caricare queste modifiche.

Esempio del segmento domini, due domini con policy supportate:

```text
La ricerca nativa include sempre i sottodomini. È supportato solo Sì; scegliere No blocca l'installazione senza ampliare la policy richiesta. No è la scelta predefinita.
Dominio pubblico autorizzato o URL HTTPS radice: https://Example.ORG/
Includere anche i sottodomini di example.org? [s/N]: sì
Vuoi aggiungere un altro dominio? [s/N]: s
Dominio pubblico autorizzato o URL HTTPS radice: docs.example.net
Includere anche i sottodomini di docs.example.net? [s/N]: sì
Vuoi aggiungere un altro dominio? [s/N]: no
Policy richieste per i domini:
  example.org: con sottodomini
  docs.example.net: con sottodomini
La ricerca nativa web_search basata su Bing è limitata a questi domini, inclusi tutti i loro sottodomini; un sottodominio non autorizza il dominio padre. L'accettazione di modello/regione e i metadati delle fonti richiedono una verifica live manuale.
Accettare costi e termini della ricerca Bing e il flusso dati al di fuori dei confini di conformità/geografici di Azure [s/N]: sì
```

Segue il piano completo e la conferma
`Procedere con la creazione delle risorse e la distribuzione [s/N]:`.
Solo un Sì esplicito autorizza le scritture. Esempio alternativo bloccato:

```text
Dominio pubblico autorizzato o URL HTTPS radice: example.org
Includere anche i sottodomini di example.org? [s/N]: no
La policy solo host per example.org non è supportata; questa scelta bloccherà l'installazione.
Vuoi aggiungere un altro dominio? [s/N]: no
Policy richieste per i domini:
  example.org: solo questo host
Installazione non riuscita (Inserimento dati e individuazione delle risorse): Policy solo host non supportate: example.org. Il filtro nativo web_search.filters.allowed_domains include sempre i sottodomini e non può rispettare queste scelte. Installazione interrotta prima dei termini o della creazione delle risorse; questo installer non ha creato risorse.
```

<a id="capacita-e-avanzamento-it"></a>

La **capacità del modello** propone un valore tra parentesi quadre: premere
**Invio** per mantenerlo o inserire un altro intero positivo. Il wizard usa il
valore predefinito restituito da Azure; se manca, propone **10**, adattato agli
eventuali limiti minimo e massimo dello SKU. Metadati non validi o contraddittori
bloccano il wizard. Per gli SKU Standard è la quota iniziale per la velocità di elaborazione delle
richieste, non il numero di utenti, una garanzia di prestazioni o un budget di
spesa. Azure convalida la quota durante la distribuzione: il valore proposto non
garantisce quota disponibile. Gli altri campi obbligatori e la conferma finale
restano invariati; `--non-interactive` richiede ancora `--model-capacity` esplicito.

La capacità salvata valida ha precedenza sul valore Azure: **1000 resta 1000**,
non viene interpretato come una piccola allocazione test né come causa di un errore.
Il valore predefinito Azure non è una raccomandazione per il carico del cliente.
Prima della domanda, per `Standard`, `GlobalStandard`, `DataZoneStandard`:

- «Esempio test/POC: 10 unità per poche interrogazioni manuali con bassa concorrenza.»
- «Esempio produzione: 100 unità solo come punto di partenza illustrativo, non come capacità garantita.»

Se i limiti SKU escludono 10 o 100, l'esempio viene dichiarato **non applicabile**,
non sostituito con un numero fuori intervallo. Non è un limite utenti, un budget
mensile o un costo PAYG fisso. Produzione richiede picco richieste/minuto,
dimensione del contesto e lavoro simultaneo limitato. **Solo se** 1 unità =
1.000 TPM e 1 RPM: 10 richieste/minuto × 6.000 token stimati per il rate limit
richiedono `max(60, 10) = 60` unità; 25% di margine = 75; 100 offre più margine.
Questo **non** è un rapporto attribuito al modello selezionato: stime del rate
limit e token fatturati differiscono. Verificare rapporti modello, incrementi e
quota disponibile; l'esempio vale solo entro i limiti SKU. Per capacità
riservata/provisioned/PTU gli addebiti sono diversi; Batch ha quote diverse:
seguire provider e dimensionamento dell'organizzazione, non gli esempi PAYG.

**Avanzamento dopo l'approvazione:** `install` mostra cinque fasi: salvataggio
ambiente azd; compilazione Bicep, provisioning ARM e attesa; salvataggio/lettura
output confermati; configurazione Foundry e runtime; pacchetto e distribuzione
app. Esempio: `Fase 2/5 · Creazione delle risorse Azure · in corso · 01:15`.
L'indicatore TTY e il tempo trascorso segnalano attività, non percentuali,
stato Azure verificato ad ogni animazione o tempo residuo. Su output reindirizzato:
righe iniziali/finali e heartbeat ogni 30 secondi, senza ANSI. Tutto su stderr:
il JSON stdout non cambia; dry-run e mancata approvazione non avviano il display.
Una fase termina solo al ritorno dell'operazione; errori/Ctrl+C fermano il display
e conservano la bozza. **Ctrl+C non annulla o elimina operazioni/risorse Azure**:
possono continuare; verificare prima di riprovare.

Per stato ARM terminale Failed/Canceled, l'installer conserva solo codici
ammessi e limitati, alcuni numeri quota riconoscibili e identificatori di
deployment. Non stampa testo provider arbitrario, parametri, header, token,
chiavi o URL con query. Il codice esterno `ResourceDeploymentFailure` **non prova
la causa**: leggere i dettagli nelle operazioni indicate. Esempi generici:

```powershell
az deployment operation sub list --subscription 'example-sub' --name 'chatbot-demo' --output json
az deployment operation group list --subscription 'example-sub' --resource-group 'rg-demo' --name 'foundry' --output json
```

I comandi effettivi usano la distribuzione corrente e, se identificato nella
risposta già ricevuta, il deployment annidato; **non vengono eseguiti automaticamente**.
Output diagnostico manuale da controllare e oscurare prima di condividerlo.
Timeout o stato mancante non diventano una diagnosi quota/conflitto.
Riavviare manualmente un processo già aperto per caricare il codice aggiornato;
con il checkout editable non occorre reinstallare.

Se le operazioni riportano `FlagMustBeSetForRestore`, il nome Foundry appartiene
a un account eliminato ma recuperabile. Un amministratore deve verificare
l'account eliminato e ripristinarlo esplicitamente se deve essere riutilizzato:
non eliminare definitivamente risorse per aggirare l'errore.
Gli errori di preflight compaiono nelle operazioni della distribuzione principale;
un deployment annidato può ancora mostrare un tentativo precedente. Confrontare
sempre le date.

Un timeout di `azd` non prova che il pacchetto sia fallito in Azure. Prima di
rilanciare, distinguere lo stato della build/distribuzione nei log App Service
dall'avvio del processo e dalla risposta di `/health`. L'installer non trasforma
un timeout in successo e non ripete automaticamente il deploy.

Con `azd` precedente a 1.31.2, il tracciamento dell'avvio Linux può restare in
attesa anche dopo una build riuscita. La
[correzione ufficiale in 1.31.2](https://github.com/Azure/azure-dev/blob/azure-dev-cli_1.31.2/cli/azd/CHANGELOG.md)
limita l'attesa senza progressi. Per un successivo deploy necessario, è disponibile
anche la variabile ufficiale, limitata al processo:

```powershell
$previous = $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK
try {
    $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK = 'true'
    python -m azure_bing_assistant deploy --environment <nome-installazione> --ui-language it
} finally {
    $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK = $previous
}
```

`WEB` identifica il servizio `web` di `azure.yaml`. Questo opt-in usa il deploy
ZIP Kudu senza il tracciamento dell'avvio Linux: non disattiva upload/build né i
filtri dei domini. Verificare separatamente `/health` e una risposta della chat;
la sola conclusione del comando non prova che il runtime funzioni. Un valore
della stessa variabile nell'ambiente azd prevale su quello del processo.

### Modalità

| Valore | Significato | Costi principali |
|---|---|---|
| `off` | Ricerca documentale disattivata; Bing e chat attivi | Foundry/modello, Bing, App Service |
| `searchBlob` | Bing più documenti amministrativi indicizzati | Costi precedenti più Storage e Search |

In `off` il Bicep condizionale non crea Storage o Search. In `searchBlob` la
configurazione non prova che esistano documenti leggibili: un amministratore
deve caricarli fuori dalla chat e verificare l'indicizzatore. Non esistono upload
in chat, allegati, OCR, crawler, selettori di fonti o toggle utente.

Anche Search restituisce `url_citation`. Il deploy passa al backend gli esistenti
`STORAGE_ACCOUNT_NAME` e `STORAGE_CONTAINER_NAME`: solo URL HTTPS di quel container
privato, con evidenza Search completata e indice/connessione corrispondenti
all'agente verificato, diventano riferimenti opachi `documents/...`. Con risultati
inline l'URL deve coincidere con `results[].url`; con output separato serve il
`call_id` della chiamata completata, anche nell'envelope `remote_function_call`
con nome nativo Search esatto. Non si deducono relazioni dal testo libero
dell'output. URL documentali diversi o metadati insufficienti non sono esentati
dalla policy web. Nessun URL nelle azioni web è esentato, neppure quello del
container. Non è una verifica live del servizio.

`WEB_GROUNDING_SITES` e `--websites` configurano **domini autorizzati obbligatori**:
domini pubblici o URL HTTPS radice, separati da virgola, massimo 100 distinti.
Maiuscole, punto finale e IDN vengono normalizzati in hostname ASCII, mantenendo
l'ordine ed eliminando duplicati. Ogni dominio include i sottodomini per contratto
Azure; `www.example.org` non autorizza automaticamente `example.org`.
Percorsi non radice, wildcard, IP, localhost/nomi locali, credenziali, porte,
query e frammenti sono rifiutati, non ampliati silenziosamente.
La sintassi separata da virgole resta per CLI non interattiva e variabili
d'ambiente; significa sempre dominio **con sottodomini**, non «solo host».
Il controllo DNS è sintattico: non esegue risoluzioni né fetch dal backend.
`--strict-websites` è solo un alias di compatibilità: non esiste modalità web ampia.

### Migrazione e verifica manuale del filtro

Riavviare un wizard già aperto: il processo esistente ha caricato il vecchio codice.
Per deployment precedenti, aggiornare i domini e usare il comando `deploy` dell'installer
(oppure completare la nuova installazione), **non soltanto ricaricare CSS o eseguire
`azd deploy web`**. Il post-deploy ricrea l'agente con il filtro e sincronizza i setting.
Un vecchio agente Bing non filtrato viene rifiutato dal nuovo runtime.
Avviare **Nuova chat** dopo ogni modifica alla policy: la cronologia remota di un
vecchio `previousResponseId` non viene ripulita retroattivamente.

Il tool è `{"type":"web_search","filters":{"allowed_domains":["example.org"]}}`,
accanto a Search solo se configurato. Nessuna connessione Bing, chiave o risorsa
standalone è necessaria. Il reprovisioning **incrementale non elimina** vecchie
risorse/connessioni Bing del cliente: valutarle separatamente senza cleanup automatico.

Prima di aprire il servizio agli utenti, l'operatore deve:
1. Confermare il supporto di modello/versione/SKU/regione selezionati senza dedurlo
   dalla sola presenza nel catalogo. Accettazione ed enforcement live sono ancora
   da verificare, incluso `open_page`.
2. Verificare la definizione della versione agente: solo `web_search` con lista
   esatta `filters.allowed_domains`, più eventuale `azure_ai_search`.
3. In una nuova chat provare domanda con fonte autorizzata, sottodominio autorizzato,
   assenza di risultati e richieste esplicite a dominio esterno, dominio-suffisso
   ingannevole (`example.org.evil.org`) e redirect esterno.
4. Controllare `consultedSources` e `webSearchUsed` in `/api/chat`. Il backend richiede
   `include=["web_search_call.action.sources"]`, controlla `action.sources`, URL
   `open_page`/`find_in_page`, citazioni e tool restituiti. Metadati assenti, sconosciuti
   o fuori dominio causano `503 source_policy_unverified`, non una risposta parzialmente
   filtrata. Se il servizio non restituisce abbastanza metadati, fermarsi e verificare
   il supporto; non rimuovere il filtro o i controlli per farlo funzionare.
5. Provare un saluto: nessuna ricerca è necessaria (`webSearchUsed=false`); non
   rappresentarlo come risposta grounded. Verificare separatamente i documenti opzionali.

La verifica dell'evidenza è difesa aggiuntiva, non può impedire retroattivamente
un fetch del servizio né provare tutte le affermazioni del modello. Nessuna chiamata
Azure o inferenza live è implicita nei test offline.

<a id="stima-costi-it"></a>

### Stima pubblica dei costi

Questa indicazione usa prezzi pubblici Azure **Consumption in USD**, rilevati il
**7 settembre 2026**, al netto di imposte. Contratti, sconti e crediti possono
produrre prezzi diversi. La base confrontabile è:

Il nuovo percorso nativo resta basato su Bing e soggetto ai relativi termini,
privacy e costi. Le stime e il benchmark storico sotto non sono nuove misure del
filtro nativo: riconfermare i meter/prezzi applicabili, senza dedurre uno SKU G1
o una risorsa standalone dalla tabella storica.

- GPT-5.4 versione `2026-03-05`, `DataZoneStandard` pay-as-you-go, richieste
  sotto 272.000 token, in Sweden Central o West Europe: **$2,75/1M token
  input** e **$16,50/1M token output**;
- Grounding with Bing Search, meter `Search Transactions`: **$14/1.000
  transazioni fatturabili**;
- App Service Basic B1 Linux: **$0,018/ora**, cioè **$13,14** per 730 ore.

Questo è lo scenario primario coerente con il test pratico EU. Non sono
combinati prezzi PTU/Provisioned, Batch, cache, Priority, long-context o Pro. Se
il piano live sceglie un'altra regione o SKU, rifare il calcolo con il relativo
listino invece di trattare questa stima come prezzo esatto universale.

La tabella seguente è un'**ipotesi di pianificazione**, non un costo tipico
verificato. Una conversazione contiene cinque turni domanda-risposta. Per
ciascun turno si assumono 1.500 token input fatturati, inclusi sistema,
cronologia, retrieval e contesto strumenti; 500 token output **totali
fatturati**, incluso il reasoning eventuale; e una transazione Bing fatturabile.
Una domanda italiana di 40-100 parole e una risposta visibile di 250-350 parole
sono solo esempi illustrativi, non un budget token garantito.

```text
modello/turno = 1.500 / 1.000.000 × $2,75
               + 500 / 1.000.000 × $16,50 = $0,012375
Bing/turno(q) = q × $14 / 1.000 = $0,014 × q
totale(N,q) = $13,14 + N × 5 × ($0,012375 + $0,014 × q)
```

Con `q=1` il costo variabile è **$0,026375 per singolo turno Q/A** e
**$0,131875 per conversazione**. Se “chat” indica un solo Q/A, dividere per
cinque solo la parte variabile: il costo fisso mensile non si divide.

| Conversazioni/mese | Fisso | Modello | Bing | Totale | Per conversazione |
|---:|---:|---:|---:|---:|---:|
| 10 | $13,14 | $0,62 | $0,70 | **$14,46** | $1,4459 |
| 100 | $13,14 | $6,19 | $7,00 | **$26,33** | $0,2633 |
| 1.000 | $13,14 | $61,88 | $70,00 | **$145,02** | $0,1450 |
| 10.000 | $13,14 | $618,75 | $700,00 | **$1.331,89** | $0,1332 |
| 100.000 | $13,14 | $6.187,50 | $7.000,00 | **$13.200,64** | $0,1320 |

#### Smoke test live illustrativo

Un singolo test autorizzato dell'**8 settembre 2026** ha inviato cinque domande
generiche sintetiche dall'app, tramite Managed Identity, a
`GPT-5.4 DataZoneStandard` e Bing. L'uso aggregato restituito dall'SDK è stato
**30.410 token input** (media 6.082/turno), **2.463 token output totali** (media
492,6/turno), zero token di reasoning e cinque chiamate Bing completate. I
**2.176 token input cached sono già inclusi nei 30.410** e non vengono sommati
di nuovo. Sono metriche anonime di benchmark sintetico, non analytics pubbliche
di produzione né dati universitari. Per la sola stima, **una transazione
fatturabile per chiamata completata è un proxy**: l'uso fatturabile in fattura
non è stato misurato né verificato.

È soltanto **un campione di una conversazione da cinque turni**, non
statisticamente rappresentativo del traffico studenti: i token cambiano con
cronologia e retrieval. In particolare, questo campione ha usato molto più
input dell'ipotesi di pianificazione di 1.500 token/turno. Per un confronto
prudente si valorizzano tutti i 30.410 token input a $2,75/1M, senza sconto
cache:

```text
modello/campione = 30.410 / 1.000.000 × $2,75
                   + 2.463 / 1.000.000 × $16,50 = $0,124267
Bing/campione (proxy: 1 transazione fatturabile/chiamata completata)
                = 5 × $0,014 = $0,070000
variabile/campione = $0,194267
totale(N) = $13,14 + N × $0,194267
```

Questa è l'**estrapolazione di un singolo test sintetico, non una previsione né
una garanzia di capacità**:

| Ripetizioni campione/mese | Fisso | Modello | Bing | Totale |
|---:|---:|---:|---:|---:|
| 10 | $13,14 | $1,24 | $0,70 | **$15,08** |
| 100 | $13,14 | $12,43 | $7,00 | **$32,57** |
| 1.000 | $13,14 | $124,27 | $70,00 | **$207,41** |
| 10.000 | $13,14 | $1.242,67 | $700,00 | **$1.955,81** |
| 100.000 | $13,14 | $12.426,70 | $7.000,00 | **$19.439,84** |

Il costo variabile di $0,194267 non è una fattura Azure; imposte, crediti,
contratti e sconti sono esclusi. La fattura effettiva può essere inferiore per
effetto della cache, ma qui non si inventa una tariffa cached non documentata.

<a id="scenario-ottimizzato-it"></a>
<a id="stima-mensile-indicativa-it"></a>

#### Stima mensile indicativa

Questa stima adotta un **budget variabile ipotetico di $0,1359869 per
conversazione da cinque scambi domanda-risposta**, più il fisso B1.
È un'ipotesi di pianificazione, non un costo unitario misurato, una tariffa o
una fattura Azure. È distinta dal campione osservato descritto sopra
($0,194267 variabili per conversazione); listini e misure restano invariati.

```text
budget variabile/conversazione = $0,1359869
totale stimato(N) = $13,14 + N × $0,1359869
```

| Conversazioni da 5 turni/mese | Fisso B1 | Variabile stimato | Totale stimato |
|---:|---:|---:|---:|
| 10 | $13,14 | $1,36 | **$14,50** |
| 100 | $13,14 | $13,60 | **$26,74** |
| 1.000 | $13,14 | $135,99 | **$149,13** |
| 10.000 | $13,14 | $1.359,87 | **$1.373,01** |
| 100.000 | $13,14 | $13.598,69 | **$13.611,83** |

Il fisso è **$13,14/mese**, anche con zero conversazioni. L'eventuale fisso
Search di **$73,73/mese** non è incluso nella tabella, come imposte e altre
voci escluse descritte sotto.

Il costo effettivo dipende dal modello scelto, dai token, dalle transazioni Bing,
dalla cache e dal contratto. Verificare i consumi reali prima di definire il budget.
Le misure e il proxy di fatturazione del campione restano documentati
separatamente nella sezione del test osservato.

#### Sensibilità, costi opzionali e riproduzione

Il meter non fattura genericamente una “richiesta Foundry”: fattura una
transazione Bing. La presenza dello strumento non implica una transazione a ogni
turno; un turno agente può invocare Bing zero o più volte. La sensibilità per
0/1/2 transazioni per turno, nell'ipotesi di pianificazione originale,
è rispettivamente **$0/$0,07/$0,14 Bing per
conversazione**, oppure **$0,061875/$0,131875/$0,201875** di costo variabile
totale. Misurare i tool call reali. `DataZoneStandard` limita il trattamento del
modello alla data zone prevista, ma **non** rende EU-only l'elaborazione Bing,
che resta soggetta ai propri termini e confini dati.

Nella stessa ipotesi, se l'output totale fatturato sale da 500 a 1.500 token per
turno, i 1.000 token aggiuntivi costano **$0,0825 per conversazione di cinque turni** e **$8.250/mese
per 100.000 conversazioni**. Reasoning, retrieval e cronologie lunghe possono
superare entrambe le ipotesi.

Come confronto separato, `GlobalStandard` usa **$2,50/1M input** e **$15/1M
output**: con l'ipotesi di pianificazione originale costa **$0,12625 variabili
per conversazione** e
**$12.638,14 totali a 100.000 conversazioni**. Questi valori non sono mescolati
nelle colonne della tabella primaria.

`searchBlob` è separato e non serve per Bing. Azure AI Search Basic con
1 replica × 1 partizione, cioè una search unit, aggiunge almeno **$0,101/ora =
$73,73/730 ore** in ciascuna delle tre regioni confrontate, più Blob Storage e
operazioni dipendenti da quantità e regione. Il retrieval può anche aumentare i
token input. Un'unica replica non è una configurazione SLA; unità, replica e
partizioni aggiuntive cambiano il costo.

Nessuno dei tre profili applica imposte, sconti di listino, contratti o crediti
gratuiti; la stima mensile indicativa usa un budget variabile ipotetico. Sono
esclusi egress, monitoraggio, ulteriori unità, Storage o strumenti a consumo. Non
inventa costi fissi per hosting Foundry, login visitatori, chiavi, session store
o lock, assenti dall'architettura. Non garantisce che un B1 continuo o la quota
modello supportino 100.000 conversazioni: throttling, concorrenza, scaling, SLA
e test di carico sono verifiche distinte. Il calcolo usa `Decimal`, arrotonda
soltanto i valori monetari finali `ROUND_HALF_UP` e si riproduce offline con:

```powershell
python .\scripts\estimate_monthly_cost.py
```

Il comando mostra separatamente l'ipotesi di pianificazione originale, il
campione osservato e la stima mensile indicativa.

Fonti ufficiali: [prezzi Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/),
[modello e disponibilità regionale](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability),
[fatturazione dei token di reasoning](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning),
[prezzi Grounding with Bing](https://www.microsoft.com/en-us/bing/apis),
[conteggio delle transazioni Bing](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools),
[App Service Linux](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/),
[Azure AI Search](https://azure.microsoft.com/en-us/pricing/details/search/) e
[Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
Query Consumption riproducibili: [GPT-5.4 West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=armRegionName%20eq%20%27westeurope%27%20and%20serviceName%20eq%20%27Foundry%20Models%27%20and%20productName%20eq%20%27Azure%20OpenAI%20GPT5%27%20and%20priceType%20eq%20%27Consumption%27%20and%20%28skuName%20eq%20%275.4%20inp%20Dz%27%20or%20skuName%20eq%20%275.4%20opt%20Dz%27%20or%20skuName%20eq%20%275.4%20inp%20Gl%27%20or%20skuName%20eq%20%275.4%20opt%20Gl%27%29),
[Grounding with Bing](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=productName+eq+%27Grounding+with+Bing%27+and+skuName+eq+%27Search%27+and+priceType+eq+%27Consumption%27),
[B1 Linux West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=serviceName+eq+%27Azure+App+Service%27+and+armRegionName+eq+%27westeurope%27+and+productName+eq+%27Azure+App+Service+Basic+Plan+-+Linux%27+and+skuName+eq+%27B1%27+and+priceType+eq+%27Consumption%27) e
[Search Basic West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=serviceName+eq+%27Azure+Cognitive+Search%27+and+armRegionName+eq+%27westeurope%27+and+skuName+eq+%27Basic%27+and+priceType+eq+%27Consumption%27).

### Dry-run e installazione non interattiva

I piani offline non acquisiscono credenziali né contattano Azure:

```powershell
python -m azure_bing_assistant plan --mode off --websites "example.org" --dry-run
python -m azure_bing_assistant plan --mode searchBlob --websites "example.org" --dry-run
```

Anche `install --dry-run` è offline, quindi richiede
`--non-interactive` e tutti i valori. Esempio **da completare prima
dell'esecuzione**:

```powershell
$SubscriptionId = "REPLACE_WITH_SUBSCRIPTION_ID"
$ResourceGroup = "REPLACE_WITH_RESOURCE_GROUP"
$Location = "REPLACE_WITH_AZURE_REGION"
$ModelName = "REPLACE_WITH_MODEL_NAME"
$ModelVersion = "REPLACE_WITH_MODEL_VERSION"
$ModelFormat = "REPLACE_WITH_MODEL_FORMAT"
$ModelSku = "REPLACE_WITH_MODEL_SKU"
$FoundryRoleId = "REPLACE_WITH_FULL_FOUNDRY_ROLE_DEFINITION_RESOURCE_ID"

python -m azure_bing_assistant install `
  --non-interactive `
  --dry-run `
  --mode off `
  --ui-language it `
  --environment chatbot-dev `
  --subscription $SubscriptionId `
  --resource-group $ResourceGroup `
  --create-resource-group `
  --location $Location `
  --model-name $ModelName `
  --model-version $ModelVersion `
  --model-format $ModelFormat `
  --model-sku $ModelSku `
  --model-capacity 10 `
  --deployment-name chat-model `
  --chatbot-name helper `
  --websites "https://docs.example.org" `
  --accept-bing-terms `
  --foundry-user-role-id $FoundryRoleId
```

Solo dopo aver verificato il JSON del piano e i valori, rimuovere `--dry-run`
per autorizzare provisioning e deploy. Usare `--no-create-resource-group` per
un gruppo esistente. Per `searchBlob` aggiungere `--mode searchBlob`,
`--storage-blob-data-reader-role-id <ID_COMPLETO>` e
`--search-index-data-reader-role-id <ID_COMPLETO>`.

### Configurazione installer

`AZURE_ENV_NAME` (`--environment`) è il **nome breve dell’installazione**
(es. `assistente-demo`): un nome interno per salvare la configurazione
dell’installer e ricavare i nomi delle risorse Azure. Può essere diverso dal
gruppo di risorse già scelto e non è il titolo della chat visibile ai visitatori.
Usare 3–24 caratteri: lettere minuscole, cifre o trattini, iniziando con una
lettera. Nel wizard va inserito obbligatoriamente, senza valore predefinito.
Riutilizzarlo per gli aggiornamenti: cambiarlo può generare un insieme separato
di risorse.

| Variabile | Scopo | Default |
|---|---|---|
| `AZURE_ENV_NAME` | Identificatore minuscolo dell'ambiente | `chatbot-dev` |
| `AZURE_LOCATION` | Regione Azure | `westeurope` |
| `AZURE_SUBSCRIPTION_ID` | Sottoscrizione selezionata | nessuno |
| `AZURE_RESOURCE_GROUP` | Gruppo nuovo/esistente | nessuno |
| `CREATE_RESOURCE_GROUP` | Crea il gruppo | `true` |
| `KNOWLEDGE_MODE` | `off` o `searchBlob` | nessuno nel piano; `off` nel wizard |
| `MODEL_NAME`, `MODEL_VERSION`, `MODEL_FORMAT` | Identità modello | nessuno |
| `MODEL_SKU`, `MODEL_CAPACITY` | SKU e capacità | nessuno / `10` |
| `MODEL_DEPLOYMENT_NAME` | Nome deployment di inferenza | nessuno |
| `CHATBOT_NAME` | Identificatore chatbot minuscolo | nessuno |
| `UI_LANGUAGE` | Lingua completa di UI e installer: `it`, `en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr` | `it` |
| `WEB_GROUNDING_SITES` | Domini autorizzati separati da virgola (obbligatori, inclusi sottodomini) | nessuno |
| `BING_TERMS_ACCEPTED` | Accettazione esplicita | `false` |
| `FOUNDRY_USER_ROLE_DEFINITION_ID` | Input installer: Role ID runtime Foundry completo | nessuno |
| `STORAGE_BLOB_DATA_READER_ROLE_DEFINITION_ID` | Role ID Blob opzionale | nessuno |
| `SEARCH_INDEX_DATA_READER_ROLE_DEFINITION_ID` | Role ID Search opzionale | nessuno |

L'installer legge `FOUNDRY_USER_ROLE_DEFINITION_ID`. Dopo la convalida ne salva
il valore nell'ambiente azd come `COGNITIVE_USER_ROLE_DEFINITION_ID`, nome
interno usato dal parametro Bicep; quest'ultimo non è l'input letto
dall'installer.

Non esistono flag o impostazioni di autenticazione visitatore. Vecchi valori
esterni `AUTH_CLIENT_ID`, `AUTH_TENANT_ID` e `AUTH_BYPASS` sono ignorati e non
vengono cancellati automaticamente.

### Precedenza e deploy successivi

- L'installazione iniziale con `--non-interactive` valida i flag e passa anche
  i testi UI al Bicep/App Service.
- Un `deploy` standalone risolve `CHATBOT_NAME`, `WEB_GROUNDING_SITES`,
  `KNOWLEDGE_MODE` e `UI_LANGUAGE` nell'ordine: configurazione esplicita del
  processo/CLI, valori persistiti nell'ambiente azd, poi default sicuri
  (`assistant`, nessun default per i domini obbligatori, `off`, `it`). Omettere `--mode` conserva il valore
  persistito; specificare `--mode off` disattiva solo Search.
- `python -m azure_bing_assistant deploy` convalida gli output, riconfigura gli
  strumenti Foundry, sincronizza solo quei quattro setting App Service e infine
  esegue il deploy del pacchetto. Non è un comando generico per aggiornare tutti
  gli override testuali `UI_*`.
- Per un cambiamento solo HTML/CSS/JavaScript già salvato nel repository, usare
  il packaging azd, che non esegue la riconfigurazione Foundry:

```powershell
$AzdEnvironment = "REPLACE_WITH_AZD_ENVIRONMENT"
azd deploy web --environment $AzdEnvironment --no-prompt
```

Verificare sempre l'ambiente azd selezionato prima di eseguire un comando che
modifica Azure.

<a id="documenti-it"></a>

### Documenti opzionali

In `searchBlob`, Search usa la propria Managed Identity per leggere il container
Blob privato; il progetto Foundry riceve il ruolo di lettura dell'indice. Shared
Key, accesso Blob anonimo e autenticazione locale Search restano disabilitati.

Dopo un'installazione riuscita, il CLI stampa il percorso del container e un
comando equivalente a:

```powershell
az storage blob upload-batch `
  --account-name "REPLACE_WITH_STORAGE_ACCOUNT" `
  --destination documents `
  --source ".\REPLACE_WITH_LOCAL_FOLDER" `
  --auth-mode login
```

L'operatore che carica deve avere **Storage Blob Data Contributor**. Controllare
nel portale Azure lo stato e gli errori dell'indicizzatore, il conteggio dei
documenti e una query di prova autorizzata. La presenza del file nel container
non prova che sia stato indicizzato. Non promettere al pubblico che un documento
sia disponibile finché il recupero non lo conferma.

<a id="personalizzazione-it"></a>

### Personalizzazione di testi e grafica

**In questa guida:** [mappa delle modifiche](#mappa-ui-it) ·
[testi e lingua](#testi-ui-it) · [palette e temi](#palette-ui-it) ·
[bubble e launcher](#bubble-ui-it) · [pannello e leggibilità](#pannello-ui-it) ·
[icone e logo](#icone-ui-it) · [incorporare la chat](#incorporare-chat-it) ·
[header e problemi comuni](#embed-trust-it) ·
[anteprima, deploy e rollback](#verifica-ui-it).

Tutti i testi controllati dall'app sono disponibili in nove lingue:
italiano (`it`), inglese (`en`), francese (`fr`), spagnolo (`es`),
portoghese europeo (`pt`), greco (`el`), ebraico/Israele (`he`), arabo (`ar`),
turco (`tr`). La localizzazione comprende l'intero installer e il frontend:
pagina iniziale, modalità, caricamento/errori, dialogo, controlli, accessibilità,
conversazione, retry e label di fonte/citazione generate. Ebraico e arabo usano
layout RTL, mantenendo leggibili URL e identificatori tecnici LTR.
I cataloghi condivisi generano anche le traduzioni frontend; vedere
[lingue e risposte native](#languages). Il default resta `it`; non esistono
rilevamento del browser o selettore per visitatore. La lingua della UI non
traduce risposte AI, URL, label fornite dal provider o override del cliente.
Le istruzioni chiedono al modello di rispondere nella lingua dell'utente salvo
richiesta diversa; il contenuto resta generativo e va verificato.

<a id="mappa-ui-it"></a>

#### Mappa rapida: cosa modificare

| Obiettivo | Punto di modifica |
|---|---|
| Lingua, nomi, benvenuto, avviso e suggerimenti | setting runtime `UI_LANGUAGE` e `UI_*`, senza cambiare il frontend |
| Colori, bubble dei messaggi, spaziature, font, pannello e launcher flottante | `app/frontend/styles.css` |
| Struttura statica, marchio e SVG del launcher | `app/frontend/index.html` |
| Avatar o markup creati per ogni messaggio | `addMessage()` e `showLoading()` in `app/frontend/app.js`, solo se il CSS non basta |

Non rinominare o rimuovere gli ID usati da `app.js`, in particolare
`#launcher`, `#chat-dialog`, `#close-btn`, `#conversation`, `#chat-form`,
`#message` e `#send-btn`. Conservare binding di localizzazione, etichette
ARIA, focus iniziale e ripristinato, chiusura con Esc, ciclo di Tab, Invio /
Maiusc+Invio e annullamento sicuro della richiesta. Per il contenuto dinamico
usare `textContent` e API DOM, come fa il codice corrente, non `innerHTML`.

<a id="testi-ui-it"></a>

#### Testi configurabili senza modificare il frontend

| Setting App Service | Flag installazione non interattiva | Effetto | Limite |
|---|---|---|---:|
| `UI_LANGUAGE` | `--ui-language <codice>` | Tutti i testi UI incorporati; installer nella stessa lingua | `it`, `en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr` |
| `UI_PRODUCT_NAME` | `--ui-product-name` | Titolo browser e nome prodotto | 80 |
| `UI_ORGANIZATION_NAME` | `--ui-organization-name` | Organizzazione sotto il prodotto | 80 |
| `UI_ASSISTANT_NAME` | `--ui-assistant-name` | Nome nel launcher e nella chat | 80 |
| `UI_WELCOME_TITLE` | `--ui-welcome-title` | Titolo di benvenuto | 120 |
| `UI_WELCOME_SUBTITLE` | `--ui-welcome-subtitle` | Sottotitolo di benvenuto | 240 |
| `UI_DISCLAIMER` | `--ui-disclaimer` | Avviso AI | 320 |
| `UI_SUGGESTED_QUESTIONS` | `--ui-suggestion` ripetibile | Fino a 5 suggerimenti, 160 caratteri ciascuno | 5 |

`--no-ui-suggestions` crea una lista vuota esplicita e non può essere combinato
con `--ui-suggestion`. Tutti i testi devono essere non vuoti e senza caratteri
di controllo; solo la lista dei suggerimenti può essere `[]`.

Per una nuova installazione senza override, cambiare il solo `UI_LANGUAGE`
cambia davvero tutti i default e i controlli incorporati. Gli override
`UI_PRODUCT_NAME`, `UI_ORGANIZATION_NAME`, `UI_ASSISTANT_NAME`,
`UI_WELCOME_TITLE`, `UI_WELCOME_SUBTITLE`, `UI_DISCLAIMER` e
`UI_SUGGESTED_QUESTIONS` restano invece letterali: non vengono tradotti o
azzerati da un cambio lingua.

Cambio lingua diretto su un App Service esistente, senza riconfigurare l'agente:

```powershell
az webapp config appsettings set `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME" `
  --settings UI_LANGUAGE=it `
  --output none
if ($LASTEXITCODE -ne 0) { throw "Aggiornamento lingua non riuscito; riavvio annullato." }
az webapp restart `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME"
```

Sostituire `it` con qualsiasi codice supportato: `it`, `en`, `fr`, `es`, `pt`,
`el`, `he`, `ar`, `tr` (per esempio `UI_LANGUAGE=pt` per portoghese europeo).
Questo presuppone un pacchetto aggiornato contenente i nove cataloghi.
Per inglese usare `UI_LANGUAGE=en`. In alternativa,
`python -m azure_bing_assistant deploy --environment <AMBIENTE> --ui-language en`
usa e persiste la stessa impostazione, ma esegue anche il normale percorso di
riconfigurazione Foundry e packaging. Se `--ui-language` è omesso, un deploy
standalone conserva la lingua persistita.

**Migrazione da versioni precedenti.** Le vecchie installazioni possono avere i
default inglesi salvati come override. Se e solo se quei valori non sono stati
personalizzati, eliminarli intenzionalmente per ereditare i default della
lingua:

```powershell
az webapp config appsettings delete `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME" `
  --setting-names UI_PRODUCT_NAME UI_ORGANIZATION_NAME UI_ASSISTANT_NAME UI_WELCOME_TITLE UI_WELCOME_SUBTITLE UI_DISCLAIMER UI_SUGGESTED_QUESTIONS
```

Poi impostare `UI_LANGUAGE` e riavviare. Non eliminare valori scritti dal
cliente: il normale deploy li conserva e il progetto non tenta di riconoscere o
tradurre automaticamente i vecchi testi.

Esempio facoltativo di branding per **Università Esempio** su un App Service
esistente; è un comando Azure mutativo, quindi rivedere nomi e target prima di
eseguirlo:

```powershell
$SubscriptionId = "REPLACE_WITH_SUBSCRIPTION_ID"
$ResourceGroup = "REPLACE_WITH_RESOURCE_GROUP"
$AppName = "REPLACE_WITH_APP_SERVICE_NAME"
$UiQuestions = @(
  'Quali servizi sono descritti sul sito?'
  'Dove trovo i contatti ufficiali?'
)
$UiSettings = @{
  UI_PRODUCT_NAME = 'Assistente servizi'
  UI_ORGANIZATION_NAME = 'Università Esempio'
  UI_ASSISTANT_NAME = 'Assistente'
  UI_WELCOME_TITLE = 'Come posso aiutarti?'
  UI_WELCOME_SUBTITLE = 'Cerca informazioni pubbliche e verifica sempre le fonti.'
  UI_DISCLAIMER = 'Le risposte sono generate con AI: verifica le informazioni e non inserire dati sensibili.'
  UI_SUGGESTED_QUESTIONS = ConvertTo-Json -InputObject @($UiQuestions) -Compress
}
$SettingsFile = Join-Path (Get-Location).Path ("ui settings {0}.json" -f [guid]::NewGuid())
try {
  [System.IO.File]::WriteAllText(
    $SettingsFile, (ConvertTo-Json -InputObject $UiSettings -Depth 3),
    [System.Text.UTF8Encoding]::new($false))
  az webapp config appsettings set `
    --subscription $SubscriptionId `
    --resource-group $ResourceGroup `
    --name $AppName `
    --settings ('@' + $SettingsFile) `
    --output none
  if ($LASTEXITCODE -ne 0) { throw "Aggiornamento UI non riuscito; riavvio annullato." }
  az webapp restart `
    --subscription $SubscriptionId `
    --resource-group $ResourceGroup `
    --name $AppName
  if ($LASTEXITCODE -ne 0) { throw "Riavvio non riuscito; verificare App Service." }
}
finally {
  Remove-Item -LiteralPath $SettingsFile -ErrorAction SilentlyContinue
}
```

Compatibile con **Windows PowerShell 5.1 e PowerShell 7**: Azure CLI legge
`--settings ('@' + $SettingsFile)` come file JSON, evitando la perdita delle
virgolette JSON nel passaggio degli argomenti nativi. Il file temporaneo UTF-8
senza BOM viene creato nella directory corrente (anche con spazi) e rimosso in
`finally`; contiene solo i valori **non segreti** `UI_*` mostrati.
Azure CLI unisce questi valori alla configurazione esistente: `UI_LANGUAGE` e
gli altri setting non elencati restano invariati.

`UI_SUGGESTED_QUESTIONS` è una **stringa contenente un array JSON** dentro
l'oggetto JSON esterno. `-InputObject @($UiQuestions)` conserva l'array anche con
un solo elemento o nessuno. Per rimuovere i suggerimenti usare `$UiQuestions = @()`
oppure `UI_SUGGESTED_QUESTIONS = '[]'` nell'hashtable, mai `$null`. Il restart
avviene solo se l'aggiornamento riesce; verificare poi `/api/config` e la pagina.

Per un'anteprima locale dei soli testi:

```powershell
$env:APP_ENV = "development"
$env:UI_LANGUAGE = "it"
$env:UI_PRODUCT_NAME = "Assistente servizi"
$env:UI_ORGANIZATION_NAME = "Università Esempio"
$env:UI_ASSISTANT_NAME = "Assistente"
$env:UI_WELCOME_TITLE = "Come posso aiutarti?"
$env:UI_SUGGESTED_QUESTIONS = '["Domanda di esempio"]'
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

Aprire `http://127.0.0.1:8000`. Senza endpoint Foundry la pagina è
visualizzabile ma la chat restituisce indisponibilità: non è una prova live.

<a id="palette-ui-it"></a>

#### Palette, temi e font

In `app/frontend/styles.css`, `:root` contiene il tema chiaro e
`html[data-theme="dark"]` sovrascrive il tema scuro. I componenti consumano i
token `--cp-*`: modificare i token, non distribuire colori letterali nelle
singole classi. Questo estratto mantiene la palette calda/rosa predefinita ed è
un punto sicuro da cui sostituire i colori del proprio marchio:

```css
:root {
  --cp-bg: #f7f4ef;
  --cp-surface: #ffffff;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-fg: #ffffff;
}

html[data-theme="dark"] {
  --cp-bg: #3d3b3a;
  --cp-surface: #292929;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-fg: #1a1a1a;
}
```

Lasciare presenti anche gli altri token già definiti: `--cp-bg-elevated`,
`--cp-surface-soft`, bordi, stati, link, pannelli, overlay e ombre. Verificare
separatamente testo/sfondo, link, focus, errori e stato disabilitato nei due
temi; per il testo normale puntare almeno a un rapporto di contrasto 4,5:1.
Questo controllo non equivale a una certificazione WCAG.

Il font predefinito è
`"Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif`:
non richiede CDN o font esterni. Lo script iniziale accetta esclusivamente
`?scoutTheme=light` o `?scoutTheme=dark`; senza parametro usa
`prefers-color-scheme`. `UI_LANGUAGE` è configurazione server e accetta `it`,
`en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr`; non esiste un parametro URL
per cambiare lingua. Verificare anche font, testi misti e layout RTL per `he`/`ar`.

<a id="bubble-ui-it"></a>

#### Bubble dei messaggi e launcher flottante

Nel CSS corrente “bubble” indica due cose diverse:

- `.msg-bot .bubble` e `.msg-user .bubble` sono i palloncini dei messaggi;
- `.bubble-launcher` è il pulsante fisso che apre il dialogo.

Per facilitare gli aggiornamenti, aggiungere gli override subito **prima** di
`@media (prefers-reduced-motion: reduce)`, dopo le media query mobili esistenti.
Usare selettori mirati, non regole per tutti i `button` o gli `article`, non
moltiplicare `!important` e lasciare dopo gli override le regole
`prefers-reduced-motion`, `forced-colors` e di stampa.

Ricetta copiabile per messaggi più arrotondati, leggermente più stretti e avatar
da 40 px:

```css
.bubble {
  max-width: min(78%, 38rem);
  padding: 0.9rem 1.05rem;
  border-radius: 1rem;
  font-size: 1rem;
  line-height: 1.6;
}

.msg-bot .bubble {
  border-color: var(--cp-border);
  border-top-left-radius: 0;
  background: var(--cp-surface);
  color: var(--cp-text);
}

.msg-user .bubble {
  border-color: var(--cp-accent);
  border-top-right-radius: 0;
  background: var(--cp-accent);
  color: var(--cp-accent-fg);
}

.msg-avatar {
  width: 40px;
  height: 40px;
}

@media (max-width: 600px) {
  .bubble {
    max-width: calc(100% - 52px);
    padding: 0.8rem 0.9rem;
  }
}
```

Per un aspetto più squadrato sostituire solo `border-radius: 1rem` con
`0.375rem`; mantenere gli angoli direzionali e il limite mobile. Per spostare il
launcher a sinistra, azzerare esplicitamente l'inset opposto e rispettare la
safe area:

```css
.bubble-launcher {
  right: auto;
  left: max(1rem, env(safe-area-inset-left, 0px));
  bottom: max(1rem, env(safe-area-inset-bottom, 0px));
}
```

Il launcher è già una pillola. Per renderlo circolare mantenendo un target
maggiore di 44 px e l'etichetta accessibile aggiornata da `app.js`:

```css
.bubble-launcher {
  width: 56px;
  height: 56px;
  min-height: 56px;
  justify-content: center;
  padding: 0;
  border-radius: 50%;
}

.bubble-launcher svg {
  width: 24px;
  height: 24px;
}

#launcher-label {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

Per mantenere o ripristinare la pillola, usare invece i valori correnti
seguenti e rimuovere il blocco circolare:

```css
.bubble-launcher {
  width: auto;
  height: auto;
  min-height: 48px;
  padding: 0.65rem 0.9rem;
  border-radius: 999px;
}

#launcher-label {
  position: static;
  width: auto;
  height: auto;
  margin: 0;
  overflow: visible;
  clip: auto;
  white-space: normal;
}
```

Non rimuovere `aria-label`, `aria-haspopup`, `type="button"` o il testo
`#launcher-label` dall'HTML.

<a id="pannello-ui-it"></a>

#### Dimensioni del pannello e leggibilità

Il box visibile è `.chat-container`; `.chat-dialog` è il backdrop a tutto
viewport e non va usato per impostare la larghezza del pannello. Il CSS corrente
usa `760px` × `780px` come massimi desktop e, sotto `600px`, porta
`.chat-container` a `100vw` × `100dvh`, senza bordo né raggio. Un override
desktop che non restringe o sposta il layout mobile:

```css
@media (min-width: 601px) {
  .chat-container {
    width: min(900px, calc(100vw - 3rem));
    height: min(720px, calc(100dvh - 3rem));
  }
}

.composer-input {
  font-size: 1rem;
  line-height: 1.6;
}

.citation-link,
.citation-text {
  font-size: 0.875rem;
  line-height: 1.45;
}
```

Non ridurre i target interattivi sotto 44 × 44 px. Provare a 320 px e con
viewport basso: titlebar, `#close-btn`, log, annullamento e composer devono
restare visibili e il focus non deve essere coperto. Non imporre altezza fissa
al log o al textarea: il flex layout e `max-height` correnti gestiscono lo
scorrimento.

<a id="icone-ui-it"></a>

#### Icone, marchio e avatar

Non esistono `UI_LOGO_URL`, upload logo o directory statica generica. Il backend
serve esplicitamente `/`, `/app.js` e `/styles.css`; quindi aggiungere
`app/frontend/logo.svg` da solo non rende il file raggiungibile. L'opzione più
semplice è usare un SVG inline di propria titolarità. Per esempio, il
`.brand-mark` in `index.html` può restare decorativo perché il nome prodotto
adiacente fornisce il testo:

```html
<span class="brand-mark" aria-hidden="true">
  <svg viewBox="0 0 24 24" fill="none" focusable="false">
    <path d="M12 3 21 12 12 21 3 12Z" fill="currentColor"></path>
  </svg>
</span>
```

```css
.brand-mark svg,
.chat-avatar svg {
  width: 24px;
  height: 24px;
}
```

Applicare lo stesso schema a `.chat-avatar` se desiderato e lasciare
`aria-hidden="true"` agli SVG puramente decorativi. Usare soltanto asset propri
o correttamente licenziati; un marchio di esempio non implica approvazione di
Microsoft o di altre organizzazioni.

Gli avatar dei messaggi non provengono da `index.html`: `addMessage()` assegna
`avatar.textContent = role === "assistant" ? "AI" : strings.userAvatar` e
`showLoading()` assegna `"AI"`. Per cambiare quelle iniziali, aggiornare
entrambi i punti. Per un SVG dinamico creare nodi con `createElementNS`, impostare
un `viewBox` e aggiungerli con `append`; non inserire markup con `innerHTML`.
Una route statica esplicita per un file separato è una modifica backend
facoltativa, non inclusa in questa guida.

<a id="incorporare-chat-it"></a>

#### Inserire la chat nel proprio sito

La chat distribuita è un'applicazione completa, non uno script widget. Sono
disponibili subito due livelli.

**A. Collegamento HTTPS.** È la soluzione più robusta:

```html
<a href="https://chat.example.org/" target="_blank" rel="noopener noreferrer">
  Apri l'assistente
</a>
```

Se non serve una nuova scheda, rimuovere `target` e `rel`. Usare sempre il
proprio URL HTTPS, mai endpoint Foundry o token nel browser.

**B. Pagina completa in iframe.** Inserire nel sito ospitante:

```html
<section class="chat-embed" aria-labelledby="chat-embed-title">
  <h2 id="chat-embed-title">Assistente online</h2>
  <iframe
    class="chat-embed-frame"
    src="https://chat.example.org/"
    title="Assistente online dell'organizzazione"
    loading="eager"
  ></iframe>
</section>
```

```css
:root {
  --cp-border: #dedede;
}

.chat-embed {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(100%, 60rem);
  height: min(80dvh, 50rem);
  min-height: 40rem;
  gap: 0.5rem;
  font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
}

.chat-embed-frame {
  display: block;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  border: 1px solid var(--cp-border);
  border-radius: 0.625rem;
}

@media (max-width: 600px) {
  .chat-embed {
    height: 100dvh;
    min-height: 35rem;
  }
}
```

`loading="eager"` è appropriato quando la chat è la funzione principale;
valutare `lazy` solo se è molto sotto la piega. L'iframe mostra **l'intera app
esistente**, pagina iniziale e launcher inclusi: non esistono `?embed=1`,
`?autostart=1`, `widget.js` o apertura automatica. Il dialogo aperto resta nel
viewport dell'iframe, non può sovrapporsi alla pagina padre, e il pulsante di
chiusura chiude il dialogo interno, non il contenitore host. Il CSS del sito
padre non può stilizzare l'app cross-origin: personalizzare e distribuire
`styles.css` nell'app.

Un launcher creato dal sito host che apre/chiude un drawer con questo iframe è
un'integrazione avanzata: deve gestire focus, Esc, etichetta, riapertura e
dimensioni, ma l'app incorporata richiede ancora il proprio pulsante “inizia”.
Un vero widget con avvio diretto richiederebbe una modifica sorgente progettata
e testata; non è una funzionalità pronta del repository.

In WordPress usare un blocco HTML personalizzato autorizzato; in Drupal o altri
CMS inserire il frammento in un template/componente consentito. Alcuni ruoli o
policy rimuovono iframe, script o stili: chiedere all'amministratore del sito,
senza aggirare la sanitizzazione. Il collegamento rimane l'alternativa più
semplice e non richiede plugin.

<a id="embed-trust-it"></a>

#### Header, confini di sicurezza e problemi comuni

Per un iframe cross-origin devono essere compatibili entrambe le policy:

- la risposta della pagina **padre** deve permettere la chat, per esempio con
  l'header HTTP `Content-Security-Policy: frame-src https://chat.example.org`;
- la risposta della **chat** deve permettere il sito padre, per esempio con
  l'header HTTP
  `Content-Security-Policy: frame-ancestors 'self' https://www.example.org`.

`frame-ancestors` deve essere un header HTTP, non un tag `<meta>`. Un
`X-Frame-Options: DENY` o `SAMEORIGIN` sulla chat può comunque bloccare
l'incorporamento cross-origin. Queste impostazioni appartengono
all'infrastruttura controllata dal cliente: non rimuovere protezioni alla cieca
e non presumere che il progetto le configuri. Limitare chi può incorporare la
pagina non autorizza `/api/chat`; proteggere l'intero ingresso web e l'API
diretta secondo [Sicurezza](security.md#italiano).

CSP dell'iframe e CORS sono problemi diversi. Non serve CORS soltanto per
visualizzare una pagina cross-origin in un iframe: JavaScript, CSS e chiamate
`/api/*` dell'app restano nella propria origine. HTTPS nella pagina padre con
iframe HTTP viene bloccato come contenuto misto.

Il frontend usa percorsi assoluti `/app.js`, `/styles.css`, `/api/config` e
`/api/chat`. Pubblicarlo sotto un prefisso come `/assistente/` richiede un
reverse proxy coerente per pagina, asset e API; copiare solo i file frontend o
riscrivere un solo percorso non basta. Un sottodominio dedicato, per esempio
`chat.example.org`, è il percorso più semplice. Dominio personalizzato e proxy
sono attività future del cliente, non eseguite da questi esempi.

<a id="verifica-ui-it"></a>

#### Anteprima locale, deploy e rollback

Seguire prima l'[installazione locale](../README.md#installazione-rapida-it).
Poi, dalla root del repository in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:APP_ENV = "development"
$env:UI_LANGUAGE = "it"
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

Aprire `http://127.0.0.1:8000`, quindi provare anche
`http://127.0.0.1:8000/?scoutTheme=light` e
`http://127.0.0.1:8000/?scoutTheme=dark`. Senza
`FOUNDRY_PROJECT_ENDPOINT` e `CHATBOT_NAME`, la configurazione e la UI locale
si caricano ma l'invio mostra il backend non disponibile: l'anteprima offline
non produce risposte live. Per testare l'iframe usare il server di sviluppo del
proprio sito su un'altra porta HTTP, non il protocollo `file:`.

Le modifiche a `UI_*` richiedono aggiornamento dei setting e riavvio
dell'applicazione. Le modifiche a HTML/CSS/JavaScript fanno invece parte del
pacchetto: il solo riavvio non le pubblica. Dopo avere verificato ambiente e
diff, un deploy del solo pacchetto supportato da `azure.yaml` è:

```powershell
$AzdEnvironment = "REPLACE_WITH_AZD_ENVIRONMENT"
azd deploy web --environment $AzdEnvironment --no-prompt
```

`python -m azure_bing_assistant deploy --environment $AzdEnvironment`
ricalcola la configurazione Foundry, sincronizza i setting previsti e poi crea
il pacchetto: non usarlo come scorciatoia per un cambio solo CSS se non si vuole
anche quel percorso.

Checklist di rilascio:

1. rivedere `git diff -- README.md docs/configuration.md app/frontend`;
2. registrare le proprie personalizzazioni in un commit identificabile;
3. provare desktop e mobile, chiaro e scuro, tastiera/focus, Esc, annullamento,
   citazioni e testi in tutte le nove lingue, inclusi layout RTL `he`/`ar`,
   URL/codice LTR e risposte sì/no native dell'installer;
4. distribuire prima in un'istanza di test e fare un hard reload per escludere
   la cache del browser;
5. per rollback, applicare `git revert <COMMIT_PROPRIO>` e ridistribuire il
   pacchetto; non usare `git reset --hard` su lavoro condiviso.

Conservare avviso AI, fonti/citazioni, target accessibili e default di
localizzazione. Gli screenshot esistenti sono rendering locali sintetici:
[desktop](assets/chat-bing-desktop.png) · [mobile](assets/chat-mobile.png) ·
[tema scuro](assets/chat-dark.png); non dimostrano un deploy live.

---

<a id="english"></a>

## English

<a id="roles-en"></a>

### Users and administrators

- **End user:** opens the page and chats. They do not install software, provide
  a client ID, register an application, or complete application-managed Entra
  visitor login.
- **Installing administrator:** signs in to Azure, chooses resources and a
  model, accepts Bing terms and costs, deploys the app, and manages documents,
  visuals, and ingress policy when required.

Operator authentication (`az login`, `azd auth login`,
`DefaultAzureCredential`) and backend Managed Identity are separate from
visitor access and remain required.

<a id="operator-installation"></a>

### Operator prerequisites

- Windows PowerShell and Git.
- Python 3.11 or 3.12.
- Azure CLI and Azure Developer CLI (`azd`).
- Access to the public repository
  `https://github.com/natasso/azure-bing-assistant`.
- A paid Azure subscription, applicable registered providers, model quota, and
  permission to create resources, connections, and role assignments.
- Visibility of Foundry User (or its documented rollout name), Storage Blob
  Data Reader, and Search Index Data Reader roles when applicable.
- `az` and `azd` sessions using an authorized account in the same tenant.

The installing identity also needs **Foundry User** (or equivalent data-plane
permissions, including agent write) on the Foundry project. **Owner** or
**Contributor** alone do not grant these permissions. The role assigned to the
application's managed identity does not authorize the installer.
For a new project, an administrator can grant access at an appropriate parent
scope before installation, or at project scope after resource provisioning.
Allow RBAC assignments to propagate, which can take several minutes, then resume
with `python -m azure_bing_assistant deploy --environment <installation-name> --ui-language en`.
This command reuses saved outputs without reprovisioning infrastructure.

Model names, versions, SKUs, capacities, subscriptions, and role definition IDs
in examples are not validated values. Replace them with real target-tenant
values. Azure remains authoritative for regional availability, quota, and
compatibility.

### PowerShell setup

Run from the directory where the project should be cloned:

```powershell
git clone https://github.com/natasso/azure-bing-assistant.git
Set-Location .\azure-bing-assistant
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
az login
azd auth login
python -m azure_bing_assistant doctor
```

If only Python 3.11 is installed, replace the environment-creation command with
`py -3.11 -m venv .venv`; activation and all following commands stay the same.

The public repository can be cloned without GitHub authentication. If
PowerShell blocks the activation script, follow the approved organizational
process or invoke `.\.venv\Scripts\python.exe -m ...` directly.

For development and tests, separately:

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

The installed `azure-bing-assistant` entry point and
`python -m azure_bing_assistant` are equivalent.

### Recommended interactive installation

```powershell
python -m azure_bing_assistant install
```

The wizard:

1. reads enabled subscriptions, resource groups, regions,
   model/version/format/SKU combinations, and roles from Azure;
2. asks for names, capacity, and required authorized public domains;
3. defaults to **Authorized websites** and asks whether to add Blob Storage and Azure
   AI Search;
4. requires acknowledgement of Bing costs, terms, and data flow;
5. shows a plan and asks before making changes.

On the first run, the nine-language picker uses native labels and defaults to **Italiano** on Enter. The selected
language controls both the chatbot and all installer questions, guidance,
summaries and confirmations. `--ui-language` accepts one of `it`, `en`, `fr`,
`es`, `pt`, `el`, `he`, `ar`, `tr`, skips the picker and preselects the language
in interactive mode. Existing `it`/`en` menu entries remain compatible; see
[languages, native inputs, and RTL](#languages). Azure names, SKUs, region identifiers, JSON
keys and technical provider diagnostics remain unchanged; provider failures
include localized stage context.
Other `--ui-*` custom-copy arguments are processed only with
`--non-interactive`.

Each question first shows its format, limits, and default (if any). Invalid input
repeats **only that field**, keeping earlier answers in memory without repeating
completed Azure discovery. Chatbot and installation technical names require
**3–24 lowercase letters, digits or hyphens, starting with a letter**; they are
not automatically corrected. Public labels can contain spaces and are configured
separately through `UI_*` fields. Resource groups accept 1–90 ASCII letters,
digits, periods, underscores, parentheses or hyphens. The deployment name
identifies the model route on the endpoint, not its catalog name: 1–128 ASCII
letters, digits, periods, underscores or hyphens, starting with a letter or digit
(e.g. `chat-model`). These are local checks: Azure existence, permissions, quota,
and compatibility still require service validation.

Immediate correction example (excerpt):

```text
Chatbot technical name: Example University
Chatbot technical name must be 3-24 lowercase letters, digits, or hyphens and start with a letter
Chatbot technical name: assistant-demo
```

Invalid menu numbers repeat the same choice; Enter selects the proposed language
in the first menu. Other menus have a default only when a saved choice is still
available. Invalid capacity repeats only that question, without silently
substituting the default. Enter accepts the displayed yes/no default;
terms and final approval **always default to No**. Declining either stops installation.
Ctrl+C/EOF cancels even during a correction. Invalid non-interactive arguments
still fail once, without prompting. Manually restart an already running wizard;
an editable installation does not require reinstalling the package.

#### Resuming installer answers

Only interactive `install` saves each valid answer in the versioned JSON draft
`.azure/installer-draft.json`, relative to the current project directory.
This is a **private local plaintext file, excluded from Git**. It contains language,
selected tenant/subscription IDs, resource-group name/create choice, region,
model/version/format/SKU identity, capacity, technical chatbot/installation/deployment
names, optional Search choice and ordered domain/subdomain rules with collection
progress. It contains no credentials, tokens, keys, service outputs, conversation
IDs or consents, and does not read `.env`. It does not add runtime chat sessions
or conversation storage.

After failure or cancellation, rerun the same command from the same directory.
Fields show previous values in brackets; **Enter** reuses them after validation.
Without `--ui-language`, the saved language becomes the picker's default; an
explicit argument overrides only language. Menus match stable IDs against current
Azure discovery, not numeric positions. Removed choices are explained and require
a fresh selection. Changing tenant/subscription clears dependent resource defaults;
changing region/model revalidates model/capacity. An out-of-range saved capacity
is explained, never silently clamped.

Domains repeat individually: “add another” defaults to Yes while saved entries
remain, then No. An interrupted review retains unvisited entries; an explicit No
truncates the remaining list. An edited domain does not inherit another domain's
Yes to subdomains. Saved No policies remain No and still block installation,
without broadening authorization. **Bing terms and final approval always require
a fresh explicit Yes.**

The draft survives final configuration, provider, provisioning or package
deployment failures, refusals and Ctrl+C/EOF. It is cleared only after successful
full application deployment. Cleanup-only failure produces a local warning, not
a false Azure deployment failure; read/save failures stop the installer.
To start again, including after corrupt JSON or an unsupported version:

```powershell
python -m azure_bing_assistant install --reset-wizard
```

This removes **only** the draft, not azd environments/configuration or sign-ins.
It cannot be combined with `--non-interactive`/`--dry-run`. Those paths, `doctor`,
`plan`, `provision`, `deploy` and `--help` do not read or write the draft.
Only answers saved after this change can persist: an older failed invocation
without a draft cannot be recovered retrospectively. Manually restart an already
open wizard to load the updated code.

#### Domains, one at a time

After the Search option, enter **one domain or root HTTPS URL**. The wizard
validates it immediately, explicitly asks whether to include subdomains, then
whether to add another domain. It repeats until the final No (at most 100 distinct
domains; the limit completes the summary). Empty or invalid entries are requested
again. A canonical duplicate never overwrites the previous choice: its requested
policy is displayed and you must enter a different domain, or cancel and restart
to change that policy.

**Service limitation:** `web_search.filters.allowed_domains` always includes
all descendants. **Yes is the only policy supported by the current engine.**
No means “only this host”: the wizard retains that intent in the summary and
**blocks installation before terms or any Azure writes**. It never converts No
to Yes, claims a response filter prevents remote fetches, or enables alternative
services. This implements explicit choice collection, **not operational
subdomain exclusion**.

English answers accept `y`, `yes`, `n`, `no`; the other eight languages accept
their [native yes/no inputs](#languages) too. Enter accepts the displayed default,
**always No for terms and final approval**; an invalid yes/no answer repeats the same question. EOF or
interruption cancels without continuing. **Manually restart** an already open
wizard to load these changes.

Example domain segment with two supported policies:

```text
Native search always includes subdomains. Only Yes is supported; choosing No blocks installation without broadening your policy. No is the default.
Authorized public domain or root HTTPS URL: https://Example.ORG/
Include subdomains of example.org? [y/N]: yes
Add another domain? [y/N]: y
Authorized public domain or root HTTPS URL: docs.example.net
Include subdomains of docs.example.net? [y/N]: yes
Add another domain? [y/N]: no
Requested domain policies:
  example.org: with subdomains
  docs.example.net: with subdomains
Native Bing-backed web_search is restricted to these domains, including all their subdomains; a subdomain does not authorize its parent. Model/region acceptance and source metadata require manual live verification.
Accept Bing grounding cost, terms, and data flow outside Azure compliance/Geo boundaries [y/N]: yes
```

The full plan follows, then
`Proceed with provisioning and deployment [y/N]:`.
Only an explicit Yes authorizes writes. An alternative blocked example:

```text
Authorized public domain or root HTTPS URL: example.org
Include subdomains of example.org? [y/N]: no
Host-only policy for example.org is unsupported; this choice will block installation.
Add another domain? [y/N]: no
Requested domain policies:
  example.org: only this host
Installation failed (Input and discovery): Unsupported host-only policies: example.org. Native web_search.filters.allowed_domains always includes descendants and cannot honor these choices. Installation stopped before terms or provisioning; no resources were created by this installer.
```

<a id="capacity-and-progress-en"></a>

**Model capacity** shows a value in square brackets: press **Enter** to keep it
or enter another positive integer. The wizard uses Azure's returned default;
if absent, it proposes **10**, adjusted to any SKU minimum and maximum bounds.
Invalid or contradictory metadata stops the wizard. For Standard SKUs this is the initial request
throughput quota, not the number of users, guaranteed performance, or a cost
budget. Azure validates quota at deployment: the proposed value does not
guarantee available quota. Other required fields and the final confirmation are
unchanged; `--non-interactive` still requires an explicit `--model-capacity`.

A valid saved capacity takes precedence over Azure's default: **1000 stays 1000**,
not described as a small test allocation or assumed to cause a failure.
Azure's default is not a recommendation for the customer's workload.
Before prompting, `Standard`, `GlobalStandard`, `DataZoneStandard` show:

- “Test/POC example: 10 units for a few manual queries with low concurrency.”
- “Production example: 100 units only as an illustrative starting point, not guaranteed capacity.”

If SKU bounds exclude 10 or 100, that example is explicitly **not applicable**;
no out-of-range fallback is suggested. Capacity is not maximum users, a monthly
budget or a fixed PAYG bill. Production needs peak requests/minute, context size
and limited simultaneous work. **Only if** 1 unit = 1,000 TPM and 1 RPM:
10 requests/minute × 6,000 estimated rate-limit tokens/request requires
`max(60, 10) = 60` units; 25% margin = 75; 100 provides more headroom.
This is **not** a conversion attributed to the selected model: rate-limit
estimates differ from billed tokens. Verify model ratios, increments and
available quota; apply only within SKU bounds. Reserved/provisioned/PTU has
different capacity-based charges; Batch has different quotas. Follow provider
and organizational sizing, not the PAYG examples.

**Progress after approval:** `install` shows five phases: save azd environment;
compile Bicep, provision ARM and wait; save/read confirmed outputs; configure
Foundry and runtime; package and deploy the app. Example:
`Phase 2/5 · Provisioning Azure resources · in progress · 01:15`.
TTY animation and elapsed time indicate activity, not percentages, an Azure
state check on every frame, or remaining time. Redirected output has start/end
lines and 30-second heartbeats, without ANSI. All progress uses stderr; stdout
JSON stays unchanged. Dry-run or declined approval never starts the display.
Phases end only when their operations return; failures/Ctrl+C stop the display
and retain the draft. **Ctrl+C does not cancel/delete Azure operations/resources**:
they may continue; check before retrying.

On terminal ARM Failed/Canceled, only bounded accepted codes, a few recognized
quota numbers and deployment identifiers are retained. Arbitrary provider prose,
parameters, headers, tokens, keys or URLs with queries are not printed.
An outer `ResourceDeploymentFailure` **does not establish the cause**: read
the indicated deployment operation details. Generic examples:

```powershell
az deployment operation sub list --subscription 'example-sub' --name 'chatbot-demo' --output json
az deployment operation group list --subscription 'example-sub' --resource-group 'rg-demo' --name 'foundry' --output json
```

Actual commands target the current deployment and any nested deployment
identified in the response already received; **they are never run automatically**.
Review/redact manual diagnostic output before sharing it. Missing state or
timeout is not reinterpreted as a quota/conflict diagnosis.
Manually restart an already running process to load the update; no reinstall
is needed for the editable checkout.

If operations report `FlagMustBeSetForRestore`, the Foundry name belongs to a
soft-deleted, recoverable account. An administrator must inspect the deleted
account and explicitly recover it if it should be reused; do not purge resources
to work around the error. Preflight errors appear in the parent deployment's
operations, while a nested deployment may still show an earlier attempt.
Always compare timestamps.

An `azd` timeout does not prove that the package failed in Azure. Before retrying,
distinguish App Service build/deployment log status from process startup and
the `/health` response. The installer neither treats a timeout as success nor
automatically repeats deployment.

In `azd` versions before 1.31.2, Linux startup tracking can remain pending after
a successful build. The
[official 1.31.2 fix](https://github.com/Azure/azure-dev/blob/azure-dev-cli_1.31.2/cli/azd/CHANGELOG.md)
bounds waits without status progress. For the next necessary deployment, the
documented process-local setting is also available:

```powershell
$previous = $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK
try {
    $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK = 'true'
    python -m azure_bing_assistant deploy --environment <installation-name> --ui-language en
} finally {
    $env:AZD_DEPLOY_WEB_SKIP_STATUS_CHECK = $previous
}
```

`WEB` identifies the `web` service in `azure.yaml`. This opt-in uses Kudu ZIP
deployment without Linux startup tracking; it does not disable upload/build or
domain filters. Independently check `/health` and a chat response: command
completion alone does not establish runtime health. The same variable in the
azd environment takes precedence over the process value.

### Modes

| Value | Meaning | Main costs |
|---|---|---|
| `off` | Document search off; Bing and chat enabled | Foundry/model, Bing, App Service |
| `searchBlob` | Bing plus indexed administrator documents | Previous costs plus Storage and Search |

In `off`, conditional Bicep creates no Storage or Search. In `searchBlob`,
configuration is not proof that readable documents exist: an administrator
must upload them outside chat and verify the indexer. There is no chat upload,
attachment, OCR, crawler, source picker, or user mode toggle.

Search also emits `url_citation`. Deployment passes the existing
`STORAGE_ACCOUNT_NAME` and `STORAGE_CONTAINER_NAME` to the backend. Only HTTPS
URLs in that exact private Blob container with completed Search evidence and
the verified agent's index/connection become opaque `documents/...` references.
Inline results require an exact `results[].url` match; separate outputs require
the completed call's `call_id`, including `remote_function_call` envelopes with
the exact native Search name. Free-text output is not parsed for provenance.
Other document URLs or insufficient metadata receive no web-policy exemption.
Private container URLs appearing in web actions fail closed rather than exposing
them in `consultedSources`, even if their host was also web-allowed. This is not
live service verification.

`WEB_GROUNDING_SITES` and `--websites` configure **required authorized domains**:
comma-separated public domains or root HTTPS URLs, up to 100 distinct entries.
Case, trailing dots and IDNs normalize to ASCII hostnames with stable deduplication.
Azure includes subdomains; `www.example.org` does not implicitly authorize `example.org`.
Non-root paths, wildcards, IPs, localhost/local names, credentials, ports, query and
fragment are rejected, never silently broadened. DNS validation is syntactic, not
a backend resolver/fetcher. Comma-separated syntax remains for non-interactive CLI
and environment variables; it always means domain **with subdomains**, not
host-only. `--strict-websites` is a compatibility alias; no broad mode exists.

### Migration and manual filter verification

Restart any running wizard: it loaded the old code. For existing deployments,
update domains and run the installer's `deploy` command (or finish a fresh install),
**not just a CSS reload or `azd deploy web`**. Post-deploy recreates the filtered
agent and synchronizes settings. Runtime rejects an old unfiltered Bing agent.
Start **New chat** after every source-policy change: old `previousResponseId`
history is not retroactively cleaned.

The tool is `{"type":"web_search","filters":{"allowed_domains":["example.org"]}}`,
alongside Search only when configured. No standalone Bing resource, connection,
key or `BING_CONNECTION_NAME` output is required. **Incremental reprovisioning
does not delete existing customer Bing resources/connections**; review them separately.

Before exposing the service, the operator must:
1. Confirm support for the selected model/version/SKU/region; catalog availability
   is insufficient. Live acceptance and enforcement, including `open_page`, remain pending.
2. Inspect the returned agent version: exactly filtered `web_search` with matching
   `filters.allowed_domains`, plus optional `azure_ai_search`.
3. Start a new chat and test an authorized source, its subdomain, no results,
   explicit external-domain requests, deceptive suffixes (`example.org.evil.org`)
   and an externally redirected URL.
4. Inspect `/api/chat` fields `consultedSources` and `webSearchUsed`. Runtime requests
   `include=["web_search_call.action.sources"]` and checks `action.sources`,
   `open_page`/`find_in_page` URLs, citations and returned tools. Missing, unknown
   or outside-domain evidence yields `503 source_policy_unverified`, not a partially
   filtered answer. If the service supplies insufficient metadata, stop and verify
   support; do not remove filters or checks.
5. Test a greeting without retrieval (`webSearchUsed=false`), without calling it
   grounded. Verify optional document retrieval independently.

Evidence checks are defense in depth: they cannot retroactively prevent a service
fetch or prove every model statement. Offline tests make no Azure or live inference calls.

<a id="cost-estimate-en"></a>

### Public cost estimate

This indication uses public Azure **USD Consumption prices**, retrieved on
**September 7, 2026**, before tax. Agreements, discounts, and credits can produce
different prices. Its comparable basis is:

Native filtered search remains Bing-backed and subject to Bing terms, privacy
and charges. Estimates and the historical benchmark below are not new measurements
of native filtering: reconfirm applicable meters/pricing without inferring a G1 SKU
or standalone resource from the historical table.

- GPT-5.4 version `2026-03-05`, `DataZoneStandard` pay-as-you-go, requests below
  272,000 tokens, in Sweden Central or West Europe: **$2.75/1M input tokens**
  and **$16.50/1M output tokens**;
- Grounding with Bing Search, `Search Transactions` meter: **$14/1,000 billable
  transactions**;
- App Service Basic B1 Linux: **$0.018/hour**, or **$13.14** for 730 hours.

This is the primary scenario aligned with the practical EU test. No
PTU/Provisioned, Batch, cache, Priority, long-context, or Pro rates are mixed
in. If the live plan selects another region or SKU, recalculate from its rate
instead of treating this estimate as an exact universal price.

The following table is a **planning assumption**, not a verified typical cost.
A conversation contains five question-answer turns. Each turn assumes 1,500
billed input tokens, including system instructions, history, retrieval, and
tool context; 500 **total billed** output tokens, including any reasoning; and
one billable Bing transaction. An Italian question of 40-100 words and a
visible 250-350-word answer are illustrative examples only, not guaranteed
token budgets.

```text
model/turn = 1,500 / 1,000,000 × $2.75
             + 500 / 1,000,000 × $16.50 = $0.012375
Bing/turn(q) = q × $14 / 1,000 = $0.014 × q
total(N,q) = $13.14 + N × 5 × ($0.012375 + $0.014 × q)
```

At `q=1`, variable cost is **$0.026375 per single Q/A turn** and **$0.131875
per conversation**. If “chat” means one Q/A, divide only the variable portion
by five; the monthly fixed cost does not divide.

| Conversations/month | Fixed | Model | Bing | Total | Per conversation |
|---:|---:|---:|---:|---:|---:|
| 10 | $13.14 | $0.62 | $0.70 | **$14.46** | $1.4459 |
| 100 | $13.14 | $6.19 | $7.00 | **$26.33** | $0.2633 |
| 1,000 | $13.14 | $61.88 | $70.00 | **$145.02** | $0.1450 |
| 10,000 | $13.14 | $618.75 | $700.00 | **$1,331.89** | $0.1332 |
| 100,000 | $13.14 | $6,187.50 | $7,000.00 | **$13,200.64** | $0.1320 |

#### Illustrative live smoke test

One authorized test on **September 8, 2026** sent five generic synthetic
questions from the app, through Managed Identity, to
`GPT-5.4 DataZoneStandard` and Bing. Aggregate SDK response usage was **30,410
input tokens** (6,082/turn average), **2,463 total output tokens** (492.6/turn
average), zero reasoning tokens, and five completed Bing calls. The **2,176
cached input tokens are already included in 30,410** and are not added again.
These are anonymous synthetic benchmark metrics, not public production
analytics or university data. For estimation only, **one billable transaction
per completed call is a proxy**: invoice billable usage was not measured or
verified.

This is only **one five-turn conversation sample**, not statistically
representative of student traffic: tokens vary with history and retrieval. In
particular, this sample used much more input than the 1,500-token/turn planning
assumption. For a conservative comparison, all 30,410 input tokens are charged
at $2.75/1M with no cached-input discount:

```text
model/sample = 30,410 / 1,000,000 × $2.75
               + 2,463 / 1,000,000 × $16.50 = $0.124267
Bing/sample (proxy: 1 billable transaction/completed call)
            = 5 × $0.014 = $0.070000
variable/sample = $0.194267
total(N) = $13.14 + N × $0.194267
```

This is an **extrapolation of a single synthetic test, not a forecast or
capacity guarantee**:

| Sample repetitions/month | Fixed | Model | Bing | Total |
|---:|---:|---:|---:|---:|
| 10 | $13.14 | $1.24 | $0.70 | **$15.08** |
| 100 | $13.14 | $12.43 | $7.00 | **$32.57** |
| 1,000 | $13.14 | $124.27 | $70.00 | **$207.41** |
| 10,000 | $13.14 | $1,242.67 | $700.00 | **$1,955.81** |
| 100,000 | $13.14 | $12,426.70 | $7,000.00 | **$19,439.84** |

The $0.194267 variable cost is not an Azure bill; taxes, credits, contracts,
and discounts are excluded. The actual bill may be lower because of caching,
but no unsourced cached-input rate is invented here.

<a id="optimized-scenario-en"></a>
<a id="indicative-monthly-estimate-en"></a>

#### Indicative monthly estimate

This estimate uses a **hypothetical variable budget of $0.1359869 per
conversation of five question-answer turns**, plus the B1 fixed cost.
It is a planning assumption, not a measured unit cost, a tariff, or an Azure
bill. It is separate from the observed sample described above
($0.194267 variable per conversation); list prices and measurements are unchanged.

```text
variable budget/conversation = $0.1359869
estimated total(N) = $13.14 + N × $0.1359869
```

| Five-turn conversations/month | Fixed B1 | Estimated variable | Estimated total |
|---:|---:|---:|---:|
| 10 | $13.14 | $1.36 | **$14.50** |
| 100 | $13.14 | $13.60 | **$26.74** |
| 1,000 | $13.14 | $135.99 | **$149.13** |
| 10,000 | $13.14 | $1,359.87 | **$1,373.01** |
| 100,000 | $13.14 | $13,598.69 | **$13,611.83** |

Fixed cost is **$13.14/month**, even with zero conversations. The optional
**$73.73/month** Search fixed cost is not included in the table, nor are taxes
and other excluded items described below.

Actual cost depends on the selected model, tokens, Bing transactions, caching,
and contract. Verify real consumption before setting a budget.
The sample's measurements and billing proxy remain documented separately in
the observed-test section.

#### Sensitivity, optional costs, and reproduction

The meter does not generically bill a “Foundry request”; it bills a Bing
transaction. Tool availability does not mean one transaction every turn; an
agent turn can invoke Bing zero or multiple times. Under the original planning
assumption, sensitivity at 0/1/2 transactions per turn is
respectively **$0/$0.07/$0.14 Bing per conversation**,
or **$0.061875/$0.131875/$0.201875** total variable cost. Measure actual tool
calls. `DataZoneStandard` constrains model processing to the applicable data
zone, but it does **not** make Bing processing EU-only; Bing remains subject to
its own terms and data boundary.

Under that same assumption, if total billed output rises from 500 to 1,500 tokens
per turn, the extra 1,000 tokens add **$0.0825 per five-turn conversation** and **$8,250/month at 100,000
conversations**. Reasoning, retrieval, and long histories can exceed either
assumption.

As a separate comparison, `GlobalStandard` uses **$2.50/1M input** and
**$15/1M output**: under the original planning assumption it costs **$0.12625
variable per conversation** and **$12,638.14 total at 100,000 conversations**. These values
are not mixed into the primary table columns.

`searchBlob` is separate and is not required for Bing. Basic Azure AI Search
with 1 replica × 1 partition, or one search unit, adds at least **$0.101/hour =
$73.73/730 hours** in each of the three compared regions, plus Blob Storage and
operations that depend on quantity and actual region. Retrieval can also
increase input tokens. One replica is not an SLA configuration; extra units,
replicas, and partitions change cost.

None of the three profiles applies tax, list-price discounts, contracts, or
free credits; the indicative monthly estimate uses a hypothetical variable budget.
All exclude egress, monitoring, additional units, Storage, and other usage-based tools. The estimate
invents no fixed fee for Foundry hosting, visitor login, keys, session stores,
or locks, which the architecture does not contain. It does not guarantee that a
continuously running B1 or the quoted model quota can serve 100,000
conversations: throttling, concurrency, scaling, SLA, and load testing are
separate checks. The calculation uses `Decimal`, rounds final currency only
with `ROUND_HALF_UP`, and runs offline:

```powershell
python .\scripts\estimate_monthly_cost.py
```

The command displays the original planning assumption, observed sample, and
indicative monthly estimate separately.

Official sources: [Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/),
[model and region availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability),
[reasoning-token billing](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning),
[Grounding with Bing pricing](https://www.microsoft.com/en-us/bing/apis),
[Bing transaction counting](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools),
[App Service Linux](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/),
[Azure AI Search](https://azure.microsoft.com/en-us/pricing/details/search/), and
[Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
Reproducible Consumption queries: [GPT-5.4 West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=armRegionName%20eq%20%27westeurope%27%20and%20serviceName%20eq%20%27Foundry%20Models%27%20and%20productName%20eq%20%27Azure%20OpenAI%20GPT5%27%20and%20priceType%20eq%20%27Consumption%27%20and%20%28skuName%20eq%20%275.4%20inp%20Dz%27%20or%20skuName%20eq%20%275.4%20opt%20Dz%27%20or%20skuName%20eq%20%275.4%20inp%20Gl%27%20or%20skuName%20eq%20%275.4%20opt%20Gl%27%29),
[Grounding with Bing](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=productName+eq+%27Grounding+with+Bing%27+and+skuName+eq+%27Search%27+and+priceType+eq+%27Consumption%27),
[B1 Linux West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=serviceName+eq+%27Azure+App+Service%27+and+armRegionName+eq+%27westeurope%27+and+productName+eq+%27Azure+App+Service+Basic+Plan+-+Linux%27+and+skuName+eq+%27B1%27+and+priceType+eq+%27Consumption%27), and
[Search Basic West Europe](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=serviceName+eq+%27Azure+Cognitive+Search%27+and+armRegionName+eq+%27westeurope%27+and+skuName+eq+%27Basic%27+and+priceType+eq+%27Consumption%27).

### Dry-run and non-interactive installation

Offline plans acquire no credentials and contact no Azure service:

```powershell
python -m azure_bing_assistant plan --mode off --websites "example.org" --dry-run
python -m azure_bing_assistant plan --mode searchBlob --websites "example.org" --dry-run
```

`install --dry-run` is also offline, so it requires `--non-interactive` and all
values. Complete this example **before running it**:

```powershell
$SubscriptionId = "REPLACE_WITH_SUBSCRIPTION_ID"
$ResourceGroup = "REPLACE_WITH_RESOURCE_GROUP"
$Location = "REPLACE_WITH_AZURE_REGION"
$ModelName = "REPLACE_WITH_MODEL_NAME"
$ModelVersion = "REPLACE_WITH_MODEL_VERSION"
$ModelFormat = "REPLACE_WITH_MODEL_FORMAT"
$ModelSku = "REPLACE_WITH_MODEL_SKU"
$FoundryRoleId = "REPLACE_WITH_FULL_FOUNDRY_ROLE_DEFINITION_RESOURCE_ID"

python -m azure_bing_assistant install `
  --non-interactive `
  --dry-run `
  --mode off `
  --ui-language en `
  --environment chatbot-dev `
  --subscription $SubscriptionId `
  --resource-group $ResourceGroup `
  --create-resource-group `
  --location $Location `
  --model-name $ModelName `
  --model-version $ModelVersion `
  --model-format $ModelFormat `
  --model-sku $ModelSku `
  --model-capacity 10 `
  --deployment-name chat-model `
  --chatbot-name helper `
  --websites "https://docs.example.org" `
  --accept-bing-terms `
  --foundry-user-role-id $FoundryRoleId
```

Only after reviewing the plan JSON and values should `--dry-run` be removed to
authorize provisioning and deployment. Use `--no-create-resource-group` for an
existing group. For `searchBlob`, add `--mode searchBlob`,
`--storage-blob-data-reader-role-id <FULL_ID>`, and
`--search-index-data-reader-role-id <FULL_ID>`.

### Installer configuration

`AZURE_ENV_NAME` (`--environment`) is the **short installation name**
(e.g. `assistant-demo`): an internal name used to save the installer
configuration and derive Azure resource names. It can differ from the
resource-group name already chosen and is not the chat title visitors see.
Use 3–24 lowercase letters, digits or hyphens, starting with a letter.
The wizard requires manual entry, with no default. Reuse this name for updates:
changing it can generate a separate set of resources.

| Variable | Purpose | Default |
|---|---|---|
| `AZURE_ENV_NAME` | Lowercase environment identifier | `chatbot-dev` |
| `AZURE_LOCATION` | Azure region | `westeurope` |
| `AZURE_SUBSCRIPTION_ID` | Selected subscription | none |
| `AZURE_RESOURCE_GROUP` | New/existing resource group | none |
| `CREATE_RESOURCE_GROUP` | Create the group | `true` |
| `KNOWLEDGE_MODE` | `off` or `searchBlob` | none in plan; `off` in wizard |
| `MODEL_NAME`, `MODEL_VERSION`, `MODEL_FORMAT` | Model identity | none |
| `MODEL_SKU`, `MODEL_CAPACITY` | SKU and capacity | none / `10` |
| `MODEL_DEPLOYMENT_NAME` | Inference deployment name | none |
| `CHATBOT_NAME` | Lowercase chatbot identifier | none |
| `UI_LANGUAGE` | Complete UI/installer language: `it`, `en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr` | `it` |
| `WEB_GROUNDING_SITES` | Required comma-separated authorized domains (includes subdomains) | none |
| `BING_TERMS_ACCEPTED` | Explicit acknowledgement | `false` |
| `FOUNDRY_USER_ROLE_DEFINITION_ID` | Installer input: full Foundry runtime role ID | none |
| `STORAGE_BLOB_DATA_READER_ROLE_DEFINITION_ID` | Optional Blob role ID | none |
| `SEARCH_INDEX_DATA_READER_ROLE_DEFINITION_ID` | Optional Search role ID | none |

The installer reads `FOUNDRY_USER_ROLE_DEFINITION_ID`. After validation it
stores the value in the azd environment as
`COGNITIVE_USER_ROLE_DEFINITION_ID`, the internal name consumed by the Bicep
parameter; that internal name is not the installer input.

There are no visitor-authentication flags or settings. Old external
`AUTH_CLIENT_ID`, `AUTH_TENANT_ID`, and `AUTH_BYPASS` values are ignored and are
not automatically deleted.

### Precedence and later deployments

- Initial `--non-interactive` installation validates flags and passes UI text
  through Bicep to App Service.
- Standalone `deploy` resolves `CHATBOT_NAME`, `WEB_GROUNDING_SITES`,
  `KNOWLEDGE_MODE`, and `UI_LANGUAGE` in this order: explicit process/CLI
  configuration, persisted azd environment values, then safe defaults
  (`assistant`, no default for required domains, `off`, `it`). Omitting `--mode` preserves persisted mode;
  `--mode off` disables only Search.
- `python -m azure_bing_assistant deploy` validates outputs, reconfigures
  Foundry tools, synchronizes only those four App Service settings, and then
  deploys the package. It is not a general updater for every custom-copy
  `UI_*` override.
- For an HTML/CSS/JavaScript-only change already saved in the repository, use
  azd packaging without Foundry reconfiguration:

```powershell
$AzdEnvironment = "REPLACE_WITH_AZD_ENVIRONMENT"
azd deploy web --environment $AzdEnvironment --no-prompt
```

Always verify the selected azd environment before running an Azure-changing
command.

<a id="documents-en"></a>

### Optional documents

In `searchBlob`, Search uses its Managed Identity to read the private Blob
container; the Foundry project receives index-reader access. Shared Key,
anonymous Blob access, and Search local authentication remain disabled.

After a successful installation, the CLI prints the container path and a
command equivalent to:

```powershell
az storage blob upload-batch `
  --account-name "REPLACE_WITH_STORAGE_ACCOUNT" `
  --destination documents `
  --source ".\REPLACE_WITH_LOCAL_FOLDER" `
  --auth-mode login
```

The uploading operator needs **Storage Blob Data Contributor**. In Azure Portal,
check indexer state and errors, document count, and an authorized test query.
A file in the container is not proof that it was indexed. Do not promise public
document availability until retrieval confirms it.

<a id="customization-en"></a>

### Text and visual customization

**In this guide:** [change map](#ui-map-en) ·
[text and language](#ui-text-en) · [palette and themes](#ui-palette-en) ·
[bubbles and launcher](#ui-bubbles-en) · [panel and readability](#ui-panel-en) ·
[icons and logo](#ui-icons-en) · [embed the chat](#embed-chat-en) ·
[headers and troubleshooting](#embed-trust-en) ·
[preview, deploy, and rollback](#ui-validation-en).

All application-controlled copy is available in nine languages: Italian (`it`),
English (`en`), French (`fr`), Spanish (`es`), European Portuguese (`pt`),
Greek (`el`), Hebrew/Israel (`he`), Arabic (`ar`), and Turkish (`tr`).
This covers the full installer and frontend: landing
page, modes, loading/errors, dialog, controls, accessibility text, conversation,
retry, and generated source/citation labels. Hebrew and Arabic use RTL layout
with readable LTR URLs and technical identifiers. The shared catalogs also
generate frontend translations; see [languages and native inputs](#languages).
The default remains `it`; there is no browser
detection or per-visitor selector. UI language does not translate AI answers,
URLs, provider labels, or customer overrides.
The agent instructions ask the model to answer in the user's language unless
asked otherwise; generated content still requires verification.

<a id="ui-map-en"></a>

#### Quick map: what to change

| Goal | Change point |
|---|---|
| Language, names, welcome copy, notice, and suggestions | runtime `UI_LANGUAGE` and `UI_*` settings; no frontend edit |
| Colors, message bubbles, spacing, font, panel, and floating launcher | `app/frontend/styles.css` |
| Static structure, mark, and launcher SVG | `app/frontend/index.html` |
| Avatars or markup created for each message | `addMessage()` and `showLoading()` in `app/frontend/app.js`, only when CSS is insufficient |

Do not rename or remove IDs consumed by `app.js`, notably `#launcher`,
`#chat-dialog`, `#close-btn`, `#conversation`, `#chat-form`, `#message`, and
`#send-btn`. Preserve localization bindings, ARIA labels, initial/restored
focus, Escape close, Tab wrapping, Enter / Shift+Enter, and safe request
cancellation. For dynamic content, keep using `textContent` and DOM APIs as
the current code does; do not introduce `innerHTML`.

<a id="ui-text-en"></a>

#### Configurable text without frontend edits

| App Service setting | Non-interactive install flag | Effect | Limit |
|---|---|---|---:|
| `UI_LANGUAGE` | `--ui-language <code>` | All built-in UI copy; installer in the same language | `it`, `en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr` |
| `UI_PRODUCT_NAME` | `--ui-product-name` | Browser title and product name | 80 |
| `UI_ORGANIZATION_NAME` | `--ui-organization-name` | Organization below product | 80 |
| `UI_ASSISTANT_NAME` | `--ui-assistant-name` | Launcher and chat name | 80 |
| `UI_WELCOME_TITLE` | `--ui-welcome-title` | Welcome heading | 120 |
| `UI_WELCOME_SUBTITLE` | `--ui-welcome-subtitle` | Welcome subtitle | 240 |
| `UI_DISCLAIMER` | `--ui-disclaimer` | AI notice | 320 |
| `UI_SUGGESTED_QUESTIONS` | repeatable `--ui-suggestion` | Up to 5 suggestions, 160 characters each | 5 |

`--no-ui-suggestions` creates an explicit empty list and cannot be combined
with `--ui-suggestion`. Every text value must be nonempty and contain no control
characters; only the suggestion list may be `[]`.

For a new installation with no overrides, changing only `UI_LANGUAGE` changes
all built-in defaults and controls. `UI_PRODUCT_NAME`, `UI_ORGANIZATION_NAME`,
`UI_ASSISTANT_NAME`, `UI_WELCOME_TITLE`, `UI_WELCOME_SUBTITLE`,
`UI_DISCLAIMER`, and `UI_SUGGESTED_QUESTIONS` are literal overrides: changing
language does not translate or clear them.

Directly switch an existing App Service without reconfiguring the agent:

```powershell
az webapp config appsettings set `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME" `
  --settings UI_LANGUAGE=en `
  --output none
if ($LASTEXITCODE -ne 0) { throw "Language update failed; restart cancelled." }
az webapp restart `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME"
```

Replace `en` with any supported code: `it`, `en`, `fr`, `es`, `pt`, `el`, `he`,
`ar`, `tr` (for example, `UI_LANGUAGE=pt` for European Portuguese).
This assumes an updated deployed package containing all nine catalogs.
Use `UI_LANGUAGE=it` to return to Italian. Alternatively,
`python -m azure_bing_assistant deploy --environment <ENVIRONMENT> --ui-language en`
uses and persists the same setting, but also performs the normal Foundry
reconfiguration and packaging path. Omitting `--ui-language` on standalone
deploy preserves the persisted language.

**Migration from earlier releases.** Older deployments may store built-in
English defaults as overrides. If and only if those values were not customized,
deliberately remove them to inherit language defaults:

```powershell
az webapp config appsettings delete `
  --subscription "REPLACE_WITH_SUBSCRIPTION_ID" `
  --resource-group "REPLACE_WITH_RESOURCE_GROUP" `
  --name "REPLACE_WITH_APP_SERVICE_NAME" `
  --setting-names UI_PRODUCT_NAME UI_ORGANIZATION_NAME UI_ASSISTANT_NAME UI_WELCOME_TITLE UI_WELCOME_SUBTITLE UI_DISCLAIMER UI_SUGGESTED_QUESTIONS
```

Then set `UI_LANGUAGE` and restart. Do not delete customer-authored values:
ordinary deployment preserves them, and the project does not try to recognize
or translate old text automatically.

Optional **Example University** branding for an existing App Service is shown
below. This changes Azure, so review every target before running it:

```powershell
$SubscriptionId = "REPLACE_WITH_SUBSCRIPTION_ID"
$ResourceGroup = "REPLACE_WITH_RESOURCE_GROUP"
$AppName = "REPLACE_WITH_APP_SERVICE_NAME"
$UiQuestions = @(
  'Which services are described on the site?'
  'Where can I find official contacts?'
)
$UiSettings = @{
  UI_PRODUCT_NAME = 'Digital services assistant'
  UI_ORGANIZATION_NAME = 'Example University'
  UI_ASSISTANT_NAME = 'Assistant'
  UI_WELCOME_TITLE = 'How can I help?'
  UI_WELCOME_SUBTITLE = 'Find public information and always verify the sources.'
  UI_DISCLAIMER = 'Answers use AI: verify information and do not enter sensitive data.'
  UI_SUGGESTED_QUESTIONS = ConvertTo-Json -InputObject @($UiQuestions) -Compress
}
$SettingsFile = Join-Path (Get-Location).Path ("ui settings {0}.json" -f [guid]::NewGuid())
try {
  [System.IO.File]::WriteAllText(
    $SettingsFile, (ConvertTo-Json -InputObject $UiSettings -Depth 3),
    [System.Text.UTF8Encoding]::new($false))
  az webapp config appsettings set `
    --subscription $SubscriptionId `
    --resource-group $ResourceGroup `
    --name $AppName `
    --settings ('@' + $SettingsFile) `
    --output none
  if ($LASTEXITCODE -ne 0) { throw "UI update failed; restart cancelled." }
  az webapp restart `
    --subscription $SubscriptionId `
    --resource-group $ResourceGroup `
    --name $AppName
  if ($LASTEXITCODE -ne 0) { throw "Restart failed; check App Service." }
}
finally {
  Remove-Item -LiteralPath $SettingsFile -ErrorAction SilentlyContinue
}
```

Compatible with **Windows PowerShell 5.1 and PowerShell 7**: Azure CLI reads
`--settings ('@' + $SettingsFile)` as a JSON file, avoiding JSON quote loss in
native argument passing. The temporary UTF-8 file without a BOM is created in
the current directory (including paths with spaces) and removed in `finally`;
it contains only the **non-secret** `UI_*` values shown.
Azure CLI merges these values into existing configuration: `UI_LANGUAGE` and
other settings not listed remain unchanged.

`UI_SUGGESTED_QUESTIONS` is a **string containing a JSON array** within the outer
JSON object. `-InputObject @($UiQuestions)` preserves an array with one element
or none. To remove suggestions use `$UiQuestions = @()` or
`UI_SUGGESTED_QUESTIONS = '[]'` in the hashtable, never `$null`. Restart runs only
after a successful update; then verify `/api/config` and the page.

For a local text-only preview:

```powershell
$env:APP_ENV = "development"
$env:UI_LANGUAGE = "en"
$env:UI_PRODUCT_NAME = "Digital services assistant"
$env:UI_ORGANIZATION_NAME = "Example University"
$env:UI_ASSISTANT_NAME = "Assistant"
$env:UI_WELCOME_TITLE = "How can I help?"
$env:UI_SUGGESTED_QUESTIONS = '["Example question"]'
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Without a Foundry endpoint, the page is
previewable but chat reports unavailable; this is not a live-service test.

<a id="ui-palette-en"></a>

#### Palette, themes, and fonts

In `app/frontend/styles.css`, `:root` defines the light theme and
`html[data-theme="dark"]` overrides the dark theme. Components consume the
`--cp-*` tokens: change tokens rather than spreading literal colors through
individual classes. This excerpt preserves the default warm/rose palette and
is a safe starting point for substituting your own brand colors:

```css
:root {
  --cp-bg: #f7f4ef;
  --cp-surface: #ffffff;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-fg: #ffffff;
}

html[data-theme="dark"] {
  --cp-bg: #3d3b3a;
  --cp-surface: #292929;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-fg: #1a1a1a;
}
```

Keep the other existing tokens too: `--cp-bg-elevated`,
`--cp-surface-soft`, borders, states, links, panels, overlays, and shadows.
Check text/background, links, focus, errors, and disabled states independently
in both themes; target at least a 4.5:1 contrast ratio for normal text. This
check is not a claim of WCAG certification.

The default font stack is
`"Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif`;
it needs no CDN or external font. The startup script accepts only
`?scoutTheme=light` or `?scoutTheme=dark`; with no parameter it follows
`prefers-color-scheme`. `UI_LANGUAGE` is server configuration and accepts `it`,
`en`, `fr`, `es`, `pt`, `el`, `he`, `ar`, `tr`; there is no URL language
parameter. Also check fonts, mixed-direction text, and RTL layout for `he`/`ar`.

<a id="ui-bubbles-en"></a>

#### Message bubbles and floating launcher

In the current CSS, “bubble” means two different things:

- `.msg-bot .bubble` and `.msg-user .bubble` are message balloons;
- `.bubble-launcher` is the fixed button that opens the dialog.

For easier upgrades, append overrides immediately **before**
`@media (prefers-reduced-motion: reduce)`, after the existing mobile media
queries. Use targeted selectors—not rules for every `button` or `article`—do
not accumulate `!important`, and leave the `prefers-reduced-motion`,
`forced-colors`, and print rules after your overrides.

Copyable recipe for rounder, slightly narrower messages and 40 px avatars:

```css
.bubble {
  max-width: min(78%, 38rem);
  padding: 0.9rem 1.05rem;
  border-radius: 1rem;
  font-size: 1rem;
  line-height: 1.6;
}

.msg-bot .bubble {
  border-color: var(--cp-border);
  border-top-left-radius: 0;
  background: var(--cp-surface);
  color: var(--cp-text);
}

.msg-user .bubble {
  border-color: var(--cp-accent);
  border-top-right-radius: 0;
  background: var(--cp-accent);
  color: var(--cp-accent-fg);
}

.msg-avatar {
  width: 40px;
  height: 40px;
}

@media (max-width: 600px) {
  .bubble {
    max-width: calc(100% - 52px);
    padding: 0.8rem 0.9rem;
  }
}
```

For a squarer appearance, replace only `border-radius: 1rem` with `0.375rem`;
keep the directional corners and mobile limit. To move the launcher to the
left, explicitly reset the opposite inset and respect the safe area:

```css
.bubble-launcher {
  right: auto;
  left: max(1rem, env(safe-area-inset-left, 0px));
  bottom: max(1rem, env(safe-area-inset-bottom, 0px));
}
```

The launcher is already pill-shaped. To make it circular while retaining a
target larger than 44 px and the accessible label updated by `app.js`:

```css
.bubble-launcher {
  width: 56px;
  height: 56px;
  min-height: 56px;
  justify-content: center;
  padding: 0;
  border-radius: 50%;
}

.bubble-launcher svg {
  width: 24px;
  height: 24px;
}

#launcher-label {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

To keep or restore the pill, use the following current values instead and
remove the circular block:

```css
.bubble-launcher {
  width: auto;
  height: auto;
  min-height: 48px;
  padding: 0.65rem 0.9rem;
  border-radius: 999px;
}

#launcher-label {
  position: static;
  width: auto;
  height: auto;
  margin: 0;
  overflow: visible;
  clip: auto;
  white-space: normal;
}
```

Do not remove `aria-label`, `aria-haspopup`, `type="button"`, or the
`#launcher-label` text from the HTML.

<a id="ui-panel-en"></a>

#### Panel size and readability

The visible box is `.chat-container`; `.chat-dialog` is the full-viewport
backdrop and must not be used to set panel width. The current CSS caps the
desktop panel at `760px` × `780px` and, below `600px`, makes
`.chat-container` `100vw` × `100dvh` without border or radius. This desktop
override does not shrink or offset the mobile layout:

```css
@media (min-width: 601px) {
  .chat-container {
    width: min(900px, calc(100vw - 3rem));
    height: min(720px, calc(100dvh - 3rem));
  }
}

.composer-input {
  font-size: 1rem;
  line-height: 1.6;
}

.citation-link,
.citation-text {
  font-size: 0.875rem;
  line-height: 1.45;
}
```

Do not reduce interactive targets below 44 × 44 px. Test at 320 px and with a
short viewport: the titlebar, `#close-btn`, log, cancel action, and composer
must remain visible, and focus must not be obscured. Do not assign a fixed
height to the log or textarea; the current flex layout and `max-height` manage
scrolling.

<a id="ui-icons-en"></a>

#### Icons, mark, and avatars

There is no `UI_LOGO_URL`, logo upload, or generic static directory. The
backend explicitly serves `/`, `/app.js`, and `/styles.css`; merely adding
`app/frontend/logo.svg` does not expose the file. The simplest option is an
inline SVG you own. For example, `.brand-mark` in `index.html` can remain
decorative because the adjacent product name supplies the text:

```html
<span class="brand-mark" aria-hidden="true">
  <svg viewBox="0 0 24 24" fill="none" focusable="false">
    <path d="M12 3 21 12 12 21 3 12Z" fill="currentColor"></path>
  </svg>
</span>
```

```css
.brand-mark svg,
.chat-avatar svg {
  width: 24px;
  height: 24px;
}
```

Apply the same pattern to `.chat-avatar` if desired, and retain
`aria-hidden="true"` on purely decorative SVGs. Use only owned or properly
licensed assets; a sample mark implies no Microsoft or third-party
endorsement.

Message avatars do not come from `index.html`: `addMessage()` assigns
`avatar.textContent = role === "assistant" ? "AI" : strings.userAvatar`, and
`showLoading()` assigns `"AI"`. Update both places to change those initials.
For dynamic SVG, create nodes with `createElementNS`, set a `viewBox`, and add
them with `append`; do not inject markup through `innerHTML`. An explicit
static route for a separate file is an optional backend change and is not part
of this guide.

<a id="embed-chat-en"></a>

#### Insert the chat in your website

The deployed chat is a complete application, not a widget script. Two levels
work immediately.

**A. HTTPS link.** This is the most robust option:

```html
<a href="https://chat.example.org/" target="_blank" rel="noopener noreferrer">
  Open the assistant
</a>
```

Remove `target` and `rel` when a new tab is not wanted. Always use your own
HTTPS application URL; never put Foundry endpoints or tokens in browser code.

**B. Full page in an iframe.** Add this to the host website:

```html
<section class="chat-embed" aria-labelledby="chat-embed-title">
  <h2 id="chat-embed-title">Online assistant</h2>
  <iframe
    class="chat-embed-frame"
    src="https://chat.example.org/"
    title="Organization online assistant"
    loading="eager"
  ></iframe>
</section>
```

```css
:root {
  --cp-border: #dedede;
}

.chat-embed {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(100%, 60rem);
  height: min(80dvh, 50rem);
  min-height: 40rem;
  gap: 0.5rem;
  font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
}

.chat-embed-frame {
  display: block;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  border: 1px solid var(--cp-border);
  border-radius: 0.625rem;
}

@media (max-width: 600px) {
  .chat-embed {
    height: 100dvh;
    min-height: 35rem;
  }
}
```

`loading="eager"` is suitable when chat is the page's primary function;
consider `lazy` only when it is well below the fold. The iframe shows **the
entire existing app**, landing page and launcher included: there is no
`?embed=1`, `?autostart=1`, `widget.js`, or automatic open. The open dialog
stays inside the iframe viewport, cannot overlay the parent page, and its close
button closes the inner dialog—not the host container. Cross-origin parent CSS
cannot style the app: customize and deploy `styles.css` in the app itself.

A host-created launcher that opens/closes a drawer containing this iframe is
an advanced integration: it must manage focus, Escape, labeling, reopen, and
dimensions, while the embedded app still requires its own “start” action. A
true direct-start widget needs a designed and tested source change; it is not a
ready-made repository feature.

In WordPress, use an authorized Custom HTML block; in Drupal or another CMS,
place the fragment in an allowed template/component. Some roles or policies
strip iframes, scripts, or styles: ask the site administrator rather than
bypassing sanitization. The link remains the simplest option and requires no
plugin.

<a id="embed-trust-en"></a>

#### Headers, security boundaries, and troubleshooting

For a cross-origin iframe, both policies must agree:

- the **parent** page response must allow the chat, for example with the HTTP
  header `Content-Security-Policy: frame-src https://chat.example.org`;
- the **chat** response must allow the parent, for example with the HTTP header
  `Content-Security-Policy: frame-ancestors 'self' https://www.example.org`.

`frame-ancestors` must be an HTTP header, not a `<meta>` tag. A chat response
with `X-Frame-Options: DENY` or `SAMEORIGIN` may still block cross-origin
embedding. These are customer-controlled infrastructure settings: do not
blindly remove protection or assume that this project sets them. Restricting
who may embed the page does not authorize `/api/chat`; protect the full web
ingress and direct API according to [Security](security.md#english).

Iframe CSP and CORS are separate concerns. CORS is not required merely to view
a cross-origin page in an iframe: the app's JavaScript, CSS, and `/api/*`
requests remain on its own origin. An HTTP iframe on an HTTPS parent is blocked
as mixed content.

The frontend uses absolute `/app.js`, `/styles.css`, `/api/config`, and
`/api/chat` paths. Hosting it under a prefix such as `/assistant/` requires
coherent reverse-proxy routing for the page, assets, and APIs; copying only
frontend files or rewriting one path is insufficient. A dedicated subdomain
such as `chat.example.org` is the simplest route. A custom domain or proxy is
future customer work, not executed by these examples.

<a id="ui-validation-en"></a>

#### Local preview, deploy, and rollback

Complete the [local installation](../README.md#quick-install-en) first. Then,
from the repository root in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:APP_ENV = "development"
$env:UI_LANGUAGE = "en"
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, then also test
`http://127.0.0.1:8000/?scoutTheme=light` and
`http://127.0.0.1:8000/?scoutTheme=dark`. Without
`FOUNDRY_PROJECT_ENDPOINT` and `CHATBOT_NAME`, local configuration and UI load,
but sending reports that the backend is unavailable: the offline preview does
not produce live answers. To test the iframe, use your host website's
development server on another HTTP port, not the `file:` protocol.

Changes to `UI_*` require updating settings and restarting the application.
HTML/CSS/JavaScript changes are part of the package; restarting alone does not
publish them. After verifying the environment and diff, a package-only deploy
supported by `azure.yaml` is:

```powershell
$AzdEnvironment = "REPLACE_WITH_AZD_ENVIRONMENT"
azd deploy web --environment $AzdEnvironment --no-prompt
```

`python -m azure_bing_assistant deploy --environment $AzdEnvironment`
recalculates Foundry configuration, synchronizes its expected settings, and
then packages the app. Do not use it as a shortcut for a CSS-only change unless
that additional path is intended.

Release checklist:

1. review `git diff -- README.md docs/configuration.md app/frontend`;
2. record your customizations in an identifiable commit;
3. test desktop and mobile, light and dark, keyboard/focus, Escape, cancel,
   citations, and copy in all nine languages, including `he`/`ar` RTL layout,
   LTR URLs/code, and native installer yes/no inputs;
4. deploy to a test instance first and hard-reload to rule out browser cache;
5. to roll back, run `git revert <YOUR_COMMIT>` and redeploy the package; do not
   use `git reset --hard` on shared work.

Retain the AI notice, sources/citations, accessible targets, and localization
defaults. Existing screenshots are synthetic local renders:
[desktop](assets/chat-bing-desktop.png) · [mobile](assets/chat-mobile.png) ·
[dark theme](assets/chat-dark.png); they do not prove a live deployment.
