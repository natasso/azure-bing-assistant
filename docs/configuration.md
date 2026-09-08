# Configurazione / Configuration

[Italiano](#italiano) · [English](#english) · [README](../README.md)

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
2. chiede nomi, capacità e siti HTTPS preferiti;
3. propone **Bing web chat** per impostazione predefinita e chiede se aggiungere
   Blob Storage e Azure AI Search;
4. richiede l'accettazione di costi, termini e flusso dati Bing;
5. mostra un piano e chiede conferma prima delle modifiche.

Il wizard chiede la lingua dell'interfaccia e propone **Italiano** premendo
Invio. `--ui-language it|en` può preselezionarla anche nel comando interattivo.
Gli altri argomenti `--ui-*` per testi personalizzati vengono elaborati solo con
`--non-interactive`.

### Modalità

| Valore | Significato | Costi principali |
|---|---|---|
| `off` | Ricerca documentale disattivata; Bing e chat attivi | Foundry/modello, Bing, App Service |
| `searchBlob` | Bing più documenti amministrativi indicizzati | Costi precedenti più Storage e Search |

In `off` il Bicep condizionale non crea Storage o Search. In `searchBlob` la
configurazione non prova che esistano documenti leggibili: un amministratore
deve caricarli fuori dalla chat e verificare l'indicizzatore. Non esistono upload
in chat, allegati, OCR, crawler, selettori di fonti o toggle utente.

`WEB_GROUNDING_SITES` e `--websites` forniscono preferenze consultive al prompt.
Grounding with Bing Search può restituire altri domini. `--strict-websites`
fallisce intenzionalmente perché questo installer non crea né verifica un
percorso di filtro dominio rigoroso.

<a id="stima-costi-it"></a>

### Stima pubblica dei costi

Questa indicazione usa prezzi pubblici Azure **Consumption in USD**, rilevati il
**7 settembre 2026**, al netto di imposte. Contratti, sconti e crediti possono
produrre prezzi diversi. La base confrontabile è:

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
python -m azure_bing_assistant plan --mode off --dry-run
python -m azure_bing_assistant plan --mode searchBlob --dry-run
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
| `UI_LANGUAGE` | Lingua completa dell'interfaccia: `it` o `en` | `it` |
| `WEB_GROUNDING_SITES` | Siti HTTPS consultivi separati da virgola | nessuno |
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
  (`assistant`, vuoto, `off`, `it`). Omettere `--mode` conserva il valore
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

Tutti i testi controllati dall'app sono disponibili in italiano e inglese:
pagina iniziale, modalità, caricamento/errori, dialogo, controlli, accessibilità,
conversazione, retry e label di fonte generate. Il default è `it`; non esistono
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
| `UI_LANGUAGE` | `--ui-language it|en` | Tutti i testi UI incorporati | `it`, `en` |
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
`prefers-color-scheme`. `UI_LANGUAGE=it|en` è configurazione server e non
esiste un parametro URL per cambiare lingua.

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
   citazioni e testi italiano/inglese;
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
2. asks for names, capacity, and preferred HTTPS sites;
3. defaults to **Bing web chat** and asks whether to add Blob Storage and Azure
   AI Search;
4. requires acknowledgement of Bing costs, terms, and data flow;
5. shows a plan and asks before making changes.

The wizard asks for the interface language and defaults to **Italiano** when
Enter is pressed. `--ui-language it|en` can preselect it on the interactive
command. Other `--ui-*` custom-copy arguments are processed only with
`--non-interactive`.

### Modes

| Value | Meaning | Main costs |
|---|---|---|
| `off` | Document search off; Bing and chat enabled | Foundry/model, Bing, App Service |
| `searchBlob` | Bing plus indexed administrator documents | Previous costs plus Storage and Search |

In `off`, conditional Bicep creates no Storage or Search. In `searchBlob`,
configuration is not proof that readable documents exist: an administrator
must upload them outside chat and verify the indexer. There is no chat upload,
attachment, OCR, crawler, source picker, or user mode toggle.

`WEB_GROUNDING_SITES` and `--websites` provide advisory prompt preferences.
Grounding with Bing Search may return other domains. `--strict-websites`
intentionally fails because this installer does not create or verify a strict
domain-filtering path.

<a id="cost-estimate-en"></a>

### Public cost estimate

This indication uses public Azure **USD Consumption prices**, retrieved on
**September 7, 2026**, before tax. Agreements, discounts, and credits can produce
different prices. Its comparable basis is:

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
python -m azure_bing_assistant plan --mode off --dry-run
python -m azure_bing_assistant plan --mode searchBlob --dry-run
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
| `UI_LANGUAGE` | Complete interface language: `it` or `en` | `it` |
| `WEB_GROUNDING_SITES` | Comma-separated advisory HTTPS sites | none |
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
  (`assistant`, empty, `off`, `it`). Omitting `--mode` preserves persisted mode;
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

All application-controlled copy is available in Italian and English: landing
page, modes, loading/errors, dialog, controls, accessibility text, conversation,
retry, and generated source labels. The default is `it`; there is no browser
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
| `UI_LANGUAGE` | `--ui-language it|en` | All built-in UI copy | `it`, `en` |
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
`prefers-color-scheme`. `UI_LANGUAGE=it|en` is server configuration; there is
no URL language parameter.

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
   citations, and Italian/English copy;
4. deploy to a test instance first and hard-reload to rule out browser cache;
5. to roll back, run `git revert <YOUR_COMMIT>` and redeploy the package; do not
   use `git reset --hard` on shared work.

Retain the AI notice, sources/citations, accessible targets, and localization
defaults. Existing screenshots are synthetic local renders:
[desktop](assets/chat-bing-desktop.png) · [mobile](assets/chat-mobile.png) ·
[dark theme](assets/chat-dark.png); they do not prove a live deployment.
