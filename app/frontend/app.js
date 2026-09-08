"use strict";

const MAX_MESSAGE_LENGTH = 8000;
const DEFAULT_LANGUAGE = "it";
const UI_STRINGS = Object.freeze({
  it: Object.freeze({
    metaDescription: "Assistente web basato su Microsoft Foundry e Grounding with Bing Search.",
    productName: "Azure Bing Assistant",
    organizationName: "Organizzazione",
    assistantName: "Assistente",
    welcomeTitle: "Come posso aiutarti?",
    welcomeSubtitle: "Fai una domanda sulle informazioni aggiornate disponibili sul web.",
    disclaimer: "Questo assistente usa l'AI. Verifica le informazioni importanti e non condividere dati sensibili.",
    suggestions: Object.freeze([
      "Che cosa puoi aiutarmi a trovare?",
      "Riassumi un argomento attuale",
      "Spiega un concetto in modo semplice",
      "Confronta due opzioni",
      "Dove posso trovare maggiori informazioni?",
    ]),
    startConversation: "Inizia una conversazione",
    openAssistant: "Apri {assistant}",
    openAssistantTitle: "Apri assistente",
    askAssistant: "Chiedi a {assistant}",
    closeAssistant: "Chiudi assistente",
    closeTitle: "Chiudi (Esc)",
    newChat: "Nuova chat",
    conversationHistory: "Cronologia della conversazione",
    messageLabel: "Messaggio",
    sendMessage: "Invia messaggio",
    composerHint: "Invio per inviare · Maiusc+Invio per andare a capo",
    availableInChat: "Disponibile in questa chat",
    publicWebAndDocuments: "Web pubblico e ricerca nei documenti configurati",
    publicWebWithSources: "Risposte dal web pubblico con fonti",
    bingConfigured: "Grounding with Bing Search è configurato. Il suo utilizzo dipende dalla domanda.",
    configurationStatus: "Stato della configurazione",
    offLabel: "Chat web Bing (predefinita)",
    offSummary: "Chiedi informazioni aggiornate disponibili sul web pubblico.",
    offDetail: "I documenti privati non sono disponibili in questa chat.",
    offDocuments: "Servono documenti gestiti? Un amministratore può aggiungere facoltativamente Azure AI Search.",
    offPlaceholder: "Fai una domanda sul web…",
    searchLabel: "Bing + documenti (Azure AI Search, facoltativo)",
    searchSummary: "Chiedi informazioni sul web pubblico e sui documenti gestiti disponibili.",
    searchDetail: "Azure AI Search è configurato. La disponibilità dei documenti dipende dall'indicizzazione amministrativa.",
    searchDocuments: "I documenti sono aggiunti e gestiti da un amministratore; questa chat non carica file.",
    searchPlaceholder: "Fai una domanda sul web o sui documenti disponibili…",
    configUnavailableLabel: "Configurazione non disponibile",
    configUnavailableSummary: "Non è stato possibile confermare le funzionalità della chat.",
    configUnavailableTitle: "Disponibilità della chat non verificabile",
    configUnavailableDescription: "Non è stato possibile caricare la configurazione. Non si presume la disponibilità del web o dei documenti.",
    configUnavailableDocuments: "La disponibilità del web e dei documenti non può essere confermata.",
    configUnavailableWelcome: "Non è stato possibile caricare la configurazione dell'assistente.",
    configUnavailableMode: "Le funzionalità della chat non possono essere confermate in questo momento.",
    configUnavailableNotice: "Non è stato possibile caricare la configurazione. La disponibilità del web e dei documenti non può essere confermata.",
    configLoadingLabel: "Caricamento configurazione",
    configLoadingSummary: "Verifica delle funzionalità disponibili della chat.",
    configLoadingTitle: "Verifica della disponibilità della chat",
    configLoadingDescription: "Caricamento della configurazione dell'assistente.",
    configLoadingDocuments: "La disponibilità del web e dei documenti verrà mostrata dopo il caricamento.",
    configLoadingWelcome: "Caricamento della configurazione dell'assistente.",
    configLoadingMode: "La disponibilità del web e dei documenti non è ancora stata confermata.",
    configLoadingNotice: "Caricamento della configurazione dell'assistente.",
    genericPlaceholder: "Scrivi un messaggio…",
    userAvatar: "Tu",
    userMessage: "Il tuo messaggio",
    assistantMessage: "Messaggio dell'assistente",
    sources: "Fonti:",
    reference: "Riferimento",
    assistantTyping: "L'assistente sta scrivendo",
    preparingAnswer: "Preparazione della risposta",
    cancel: "Annulla",
    cancelled: "Richiesta annullata. La conversazione è stata conservata.",
    retry: "Riprova",
    retryNew: "Riprova come nuova conversazione",
    startNew: "Inizia una nuova conversazione",
    previousUnavailable: "Questa conversazione non può più continuare. Ricomincia o riprova questo messaggio come nuova conversazione.",
    requestFailed: "L'assistente non ha completato la richiesta. Riprova.",
    messageTooLong: "I messaggi non possono superare {maximum} caratteri.",
    dialogOpenError: "Impossibile aprire la finestra dell'assistente.",
  }),
  en: Object.freeze({
    metaDescription: "Web assistant powered by Microsoft Foundry and Grounding with Bing Search.",
    productName: "Azure Bing Assistant",
    organizationName: "Organization",
    assistantName: "Assistant",
    welcomeTitle: "How can I help?",
    welcomeSubtitle: "Ask a question about current information from the web.",
    disclaimer: "This assistant uses AI. Verify important information and do not share sensitive data.",
    suggestions: Object.freeze([
      "What can you help me find?",
      "Summarize a current topic",
      "Explain a concept in simple terms",
      "Compare two options",
      "Where can I learn more?",
    ]),
    startConversation: "Start a conversation",
    openAssistant: "Open {assistant}",
    openAssistantTitle: "Open assistant",
    askAssistant: "Ask {assistant}",
    closeAssistant: "Close assistant",
    closeTitle: "Close (Esc)",
    newChat: "New chat",
    conversationHistory: "Conversation history",
    messageLabel: "Message",
    sendMessage: "Send message",
    composerHint: "Enter to send · Shift+Enter for a new line",
    availableInChat: "Available in this chat",
    publicWebAndDocuments: "Public web and configured document search",
    publicWebWithSources: "Public web answers with sources",
    bingConfigured: "Bing web grounding is configured. Whether it is used depends on the question.",
    configurationStatus: "Configuration status",
    offLabel: "Bing web chat (default)",
    offSummary: "Ask about current information from the public web.",
    offDetail: "Private documents are not available in this chat.",
    offDocuments: "Need governed documents? An administrator can optionally add Azure AI Search.",
    offPlaceholder: "Ask a question about the web…",
    searchLabel: "Bing + your documents (Azure AI Search, optional)",
    searchSummary: "Ask about the public web and available administrator-managed documents.",
    searchDetail: "Azure AI Search is configured. Document availability depends on administrator indexing.",
    searchDocuments: "Documents are added and managed by an administrator; this chat does not upload files.",
    searchPlaceholder: "Ask about the web or available documents…",
    configUnavailableLabel: "Configuration unavailable",
    configUnavailableSummary: "Chat capabilities could not be confirmed.",
    configUnavailableTitle: "Chat availability unavailable",
    configUnavailableDescription: "Assistant configuration could not be loaded. No web or document availability is being assumed.",
    configUnavailableDocuments: "Web and document availability cannot be confirmed.",
    configUnavailableWelcome: "Assistant configuration could not be loaded.",
    configUnavailableMode: "Chat capabilities cannot be confirmed right now.",
    configUnavailableNotice: "Assistant configuration could not be loaded. Web and document availability cannot be confirmed.",
    configLoadingLabel: "Configuration loading",
    configLoadingSummary: "Checking available chat capabilities.",
    configLoadingTitle: "Checking chat availability",
    configLoadingDescription: "Loading assistant configuration.",
    configLoadingDocuments: "Web and document availability will appear after configuration loads.",
    configLoadingWelcome: "Loading assistant configuration.",
    configLoadingMode: "Web and document availability has not been confirmed yet.",
    configLoadingNotice: "Loading assistant configuration.",
    genericPlaceholder: "Type a message…",
    userAvatar: "You",
    userMessage: "Your message",
    assistantMessage: "Assistant message",
    sources: "Sources:",
    reference: "Reference",
    assistantTyping: "Assistant is typing",
    preparingAnswer: "Preparing an answer",
    cancel: "Cancel",
    cancelled: "Request cancelled. Your conversation was preserved.",
    retry: "Retry",
    retryNew: "Retry as new conversation",
    startNew: "Start new conversation",
    previousUnavailable: "This conversation can no longer be continued. Start over or retry this message as a new conversation.",
    requestFailed: "The assistant could not complete the request. Please try again.",
    messageTooLong: "Messages cannot exceed {maximum} characters.",
    dialogOpenError: "Unable to open the assistant dialog.",
  }),
});

function normalizeLanguage(value) {
  return value === "en" ? "en" : DEFAULT_LANGUAGE;
}

function stringsFor(language) {
  return UI_STRINGS[normalizeLanguage(language)];
}

function formatString(template, values) {
  return Object.entries(values).reduce(
    (result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

function applyStaticLanguage(elements, documentElement, language) {
  const selected = normalizeLanguage(language);
  const strings = stringsFor(selected);
  documentElement.lang = selected;
  elements.metaDescription.setAttribute("content", strings.metaDescription);
  elements.primaryOpenLabel.textContent = strings.startConversation;
  elements.launcher.title = strings.openAssistantTitle;
  elements.closeBtn.setAttribute("aria-label", strings.closeAssistant);
  elements.closeBtn.title = strings.closeTitle;
  elements.clearBtn.textContent = strings.newChat;
  elements.conversation.setAttribute("aria-label", strings.conversationHistory);
  elements.messageLabel.textContent = strings.messageLabel;
  elements.sendBtn.setAttribute("aria-label", strings.sendMessage);
  elements.composerHint.textContent = strings.composerHint;
  return selected;
}

function localizedDefaultConfig(language = DEFAULT_LANGUAGE) {
  const selected = normalizeLanguage(language);
  const strings = stringsFor(selected);
  return {
    language: selected,
    productName: strings.productName,
    organizationName: strings.organizationName,
    assistantName: strings.assistantName,
    welcomeTitle: strings.welcomeTitle,
    welcomeSubtitle: strings.welcomeSubtitle,
    disclaimer: strings.disclaimer,
    suggestedQuestions: [...strings.suggestions],
    knowledgeMode: "off",
  };
}

function normalizedText(value, fallback) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function normalizeConfig(value) {
  const config = value && typeof value === "object" ? value : {};
  const language = normalizeLanguage(config.language);
  const defaults = localizedDefaultConfig(language);
  const questions = Array.isArray(config.suggestedQuestions)
    ? config.suggestedQuestions
        .filter((question) => typeof question === "string" && question.trim())
        .map((question) => question.trim())
        .slice(0, 5)
    : [...defaults.suggestedQuestions];

  return {
    language,
    productName: normalizedText(config.productName, defaults.productName),
    organizationName: normalizedText(
      config.organizationName,
      defaults.organizationName,
    ),
    assistantName: normalizedText(config.assistantName, defaults.assistantName),
    welcomeTitle: normalizedText(config.welcomeTitle, defaults.welcomeTitle),
    welcomeSubtitle: normalizedText(
      config.welcomeSubtitle,
      defaults.welcomeSubtitle,
    ),
    disclaimer: normalizedText(config.disclaimer, defaults.disclaimer),
    suggestedQuestions: questions,
    knowledgeMode: config.knowledgeMode === "searchBlob" ? "searchBlob" : "off",
  };
}

function isValidConfigPayload(value) {
  const textFields = [
    "productName",
    "organizationName",
    "assistantName",
    "welcomeTitle",
    "welcomeSubtitle",
    "disclaimer",
  ];
  return (
    value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && (value.language === "it" || value.language === "en")
    && textFields.every(
      (field) => typeof value[field] === "string" && value[field].trim(),
    )
    && Array.isArray(value.suggestedQuestions)
    && value.suggestedQuestions.length <= 5
    && value.suggestedQuestions.every(
      (question) => typeof question === "string" && question.trim(),
    )
    && (value.knowledgeMode === "off" || value.knowledgeMode === "searchBlob")
  );
}

async function loadConfig(fetchImpl = globalThis.fetch) {
  try {
    const response = await fetchImpl("/api/config");
    if (!response.ok) throw new Error("configuration_request_failed");
    const data = await response.json();
    if (!isValidConfigPayload(data)) throw new Error("invalid_configuration");
    return { config: normalizeConfig(data), failed: false };
  } catch {
    return { config: null, failed: true };
  }
}

function modePresentation(mode, language = DEFAULT_LANGUAGE) {
  const strings = stringsFor(language);
  if (mode === "searchBlob") {
    return {
      label: strings.searchLabel,
      summary: strings.searchSummary,
      detail: strings.searchDetail,
      documents: strings.searchDocuments,
      placeholder: strings.searchPlaceholder,
    };
  }
  return {
    label: strings.offLabel,
    summary: strings.offSummary,
    detail: strings.offDetail,
    documents: strings.offDocuments,
    placeholder: strings.offPlaceholder,
  };
}

function configurationPresentation(status, language = DEFAULT_LANGUAGE) {
  const strings = stringsFor(language);
  if (status === "failed") {
    return {
      label: strings.configUnavailableLabel,
      summary: strings.configUnavailableSummary,
      title: strings.configUnavailableTitle,
      description: strings.configUnavailableDescription,
      documents: strings.configUnavailableDocuments,
      welcomeSubtitle: strings.configUnavailableWelcome,
      modeDescription: strings.configUnavailableMode,
      placeholder: strings.genericPlaceholder,
      notice: strings.configUnavailableNotice,
    };
  }
  return {
    label: strings.configLoadingLabel,
    summary: strings.configLoadingSummary,
    title: strings.configLoadingTitle,
    description: strings.configLoadingDescription,
    documents: strings.configLoadingDocuments,
    welcomeSubtitle: strings.configLoadingWelcome,
    modeDescription: strings.configLoadingMode,
    placeholder: strings.genericPlaceholder,
    notice: strings.configLoadingNotice,
  };
}

function validateMessage(value) {
  const message = typeof value === "string" ? value.trim() : "";
  if (!message) {
    return { valid: false, message: "", reason: "empty" };
  }
  if (message.length > MAX_MESSAGE_LENGTH) {
    return { valid: false, message, reason: "too-long" };
  }
  return { valid: true, message, reason: null };
}

function shouldSubmitComposerEvent(event) {
  return (
    event.key === "Enter"
    && !event.shiftKey
    && !event.isComposing
    && event.keyCode !== 229
  );
}

function getFocusWrapTarget(focusable, activeElement, shiftKey) {
  if (!focusable.length) return null;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (shiftKey && (activeElement === first || !focusable.includes(activeElement))) {
    return last;
  }
  if (!shiftKey && (activeElement === last || !focusable.includes(activeElement))) {
    return first;
  }
  return null;
}

function isolateBackgroundElements(backgroundElements) {
  const snapshots = new Map();
  for (const element of backgroundElements) {
    snapshots.set(element, {
      hadInert: element.hasAttribute("inert"),
      inertValue: element.getAttribute("inert"),
      hadAriaHidden: element.hasAttribute("aria-hidden"),
      ariaHiddenValue: element.getAttribute("aria-hidden"),
    });
    element.setAttribute("inert", "");
    element.setAttribute("aria-hidden", "true");
  }
  return snapshots;
}

function restoreBackgroundElements(snapshots) {
  for (const [element, snapshot] of snapshots) {
    if (snapshot.hadInert) {
      element.setAttribute("inert", snapshot.inertValue ?? "");
    } else {
      element.removeAttribute("inert");
    }
    if (snapshot.hadAriaHidden) {
      element.setAttribute("aria-hidden", snapshot.ariaHiddenValue ?? "");
    } else {
      element.removeAttribute("aria-hidden");
    }
  }
}

function restoreFocus(opener, fallback) {
  const target = opener && opener.isConnected && !opener.disabled ? opener : fallback;
  if (target && target.isConnected && !target.disabled && typeof target.focus === "function") {
    target.focus();
    return target;
  }
  return null;
}

function isSafeCitationReference(reference) {
  if (typeof reference !== "string" || !/^https?:\/\//i.test(reference)) {
    return false;
  }
  try {
    const url = new URL(reference);
    return (
      (url.protocol === "http:" || url.protocol === "https:")
      && !url.username
      && !url.password
    );
  } catch {
    return false;
  }
}

function isValidPreviousResponseId(value) {
  return (
    typeof value === "string"
    && value.length > 0
    && value.length <= 4096
    && !/[\u0000-\u001f\u007f]/.test(value)
  );
}

function isPreviousResponseFailure(status, data) {
  return status === 409 && data?.code === "invalid_previous_response";
}

const testApi = {
  DEFAULT_LANGUAGE,
  MAX_MESSAGE_LENGTH,
  UI_STRINGS,
  applyStaticLanguage,
  formatString,
  getFocusWrapTarget,
  isSafeCitationReference,
  isolateBackgroundElements,
  isValidConfigPayload,
  isPreviousResponseFailure,
  loadConfig,
  modePresentation,
  localizedDefaultConfig,
  normalizeLanguage,
  normalizeConfig,
  configurationPresentation,
  isValidPreviousResponseId,
  restoreBackgroundElements,
  restoreFocus,
  shouldSubmitComposerEvent,
  validateMessage,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = testApi;
}

if (typeof document !== "undefined") {
  const state = {
    config: localizedDefaultConfig(),
    language: DEFAULT_LANGUAGE,
    messages: [],
    isLoading: false,
    lastFailedMessage: null,
    knowledgeMode: null,
    opener: null,
    requestController: null,
    previousResponseId: null,
    requestSequence: 0,
    backgroundSnapshots: new Map(),
    backgroundObserver: null,
  };

  const elements = {
    launcher: document.querySelector("#launcher"),
    launcherLabel: document.querySelector("#launcher-label"),
    primaryOpenBtn: document.querySelector("#primary-open-btn"),
    primaryOpenLabel: document.querySelector("#primary-open-label"),
    portalProduct: document.querySelector("#portal-product"),
    portalOrganization: document.querySelector("#portal-organization"),
    portalConfigStatus: document.querySelector("#portal-config-status"),
    portalModeLabel: document.querySelector("#portal-mode-label"),
    portalTitle: document.querySelector("#portal-title"),
    portalSummary: document.querySelector("#portal-summary"),
    capabilityTitle: document.querySelector("#capability-title"),
    capabilityKicker: document.querySelector("#capability-kicker"),
    capabilityDescription: document.querySelector("#capability-description"),
    documentCapability: document.querySelector("#document-capability"),
    dialog: document.querySelector("#chat-dialog"),
    closeBtn: document.querySelector("#close-btn"),
    clearBtn: document.querySelector("#clear-btn"),
    messageLabel: document.querySelector("#message-label"),
    dialogTitle: document.querySelector("#dialog-title"),
    knowledgeHint: document.querySelector("#knowledge-mode-hint"),
    welcomeState: document.querySelector("#welcome-state"),
    welcomeTitle: document.querySelector("#welcome-title"),
    welcomeSubtitle: document.querySelector("#welcome-subtitle"),
    welcomeModeLabel: document.querySelector("#welcome-mode-label"),
    welcomeModeDescription: document.querySelector("#welcome-mode-description"),
    disclosureText: document.querySelector("#disclosure-text"),
    dialogConfigStatus: document.querySelector("#dialog-config-status"),
    suggestedQuestions: document.querySelector("#suggested-questions"),
    conversationContainer: document.querySelector("#conversation-container"),
    conversation: document.querySelector("#conversation"),
    form: document.querySelector("#chat-form"),
    messageInput: document.querySelector("#message"),
    charCount: document.querySelector("#char-count"),
    sendBtn: document.querySelector("#send-btn"),
    statusArea: document.querySelector("#status-area"),
    composerHint: document.querySelector("#composer-hint"),
    metaDescription: document.querySelector('meta[name="description"]'),
  };

  function currentStrings() {
    return stringsFor(state.language);
  }

  function applyLanguage(language) {
    state.language = applyStaticLanguage(
      elements,
      document.documentElement,
      language,
    );
  }

  const focusableSelector = [
    "a[href]",
    "area[href]",
    "button:not([disabled])",
    "input:not([disabled]):not([type='hidden'])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "iframe",
    "object",
    "embed",
    "[contenteditable]:not([contenteditable='false'])",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");

  function isVisibleFocusable(element) {
    if (
      element.hidden
      || element.disabled
      || element.tabIndex < 0
      || element.closest("[inert], [aria-hidden='true']")
    ) {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.display !== "none"
      && style.visibility !== "hidden"
      && element.getClientRects().length > 0;
  }

  function getFocusableElements() {
    return [...elements.dialog.querySelectorAll(focusableSelector)]
      .filter(isVisibleFocusable);
  }

  function focusInitialControl() {
    const target = elements.messageInput;
    if (isVisibleFocusable(target)) {
      target.focus();
    } else {
      elements.closeBtn.focus();
    }
  }

  function isolateElement(element) {
    if (element === elements.dialog || state.backgroundSnapshots.has(element)) return;
    const snapshot = isolateBackgroundElements([element]);
    state.backgroundSnapshots.set(element, snapshot.get(element));
  }

  function isolateBackgroundContent() {
    for (const child of document.body.children) {
      isolateElement(child);
    }
    state.backgroundObserver = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE && node.parentElement === document.body) {
            isolateElement(node);
          }
        }
      }
    });
    state.backgroundObserver.observe(document.body, { childList: true });
  }

  function restoreBackgroundContent() {
    state.backgroundObserver?.disconnect();
    state.backgroundObserver = null;
    restoreBackgroundElements(state.backgroundSnapshots);
    state.backgroundSnapshots.clear();
  }

  function cancelActiveRequest(showFeedback = false) {
    const failedMessage = state.lastFailedMessage;
    state.requestSequence += 1;
    state.requestController?.abort();
    state.requestController = null;
    state.isLoading = false;
    removeLoading();
    elements.sendBtn.disabled = false;
    elements.messageInput.disabled = false;
    if (showFeedback && failedMessage) {
      state.lastFailedMessage = failedMessage;
      showError(currentStrings().cancelled, failedMessage);
      if (elements.dialog.open) elements.messageInput.focus();
    }
  }

  function openDialog(event) {
    if (elements.dialog.open) return;
    const candidate = event?.currentTarget || document.activeElement;
    state.opener = candidate && candidate !== document.body ? candidate : elements.launcher;
    try {
      elements.dialog.showModal();
    } catch (error) {
      state.opener = null;
      console.error(currentStrings().dialogOpenError, error);
      return;
    }
    isolateBackgroundContent();
    document.documentElement.setAttribute("data-dialog-open", "true");
    window.setTimeout(focusInitialControl, 0);
  }

  function finalizeDialogClose() {
    if (!state.backgroundSnapshots.size && !state.opener) return;
    cancelActiveRequest();
    restoreBackgroundContent();
    document.documentElement.removeAttribute("data-dialog-open");
    const opener = state.opener;
    state.opener = null;
    window.setTimeout(() => {
      if (!elements.dialog.open) restoreFocus(opener, elements.launcher);
      window.requestAnimationFrame(() => {
        if (!elements.dialog.open) restoreFocus(opener, elements.launcher);
      });
    }, 0);
  }

  function closeDialog() {
    if (!elements.dialog.open) {
      finalizeDialogClose();
      return;
    }
    elements.dialog.close();
    finalizeDialogClose();
  }

  function handleDialogKeydown(event) {
    if (!elements.dialog.open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = getFocusableElements();
    const target = getFocusWrapTarget(focusable, document.activeElement, event.shiftKey);
    if (!focusable.length) {
      event.preventDefault();
      elements.dialog.focus();
    } else if (target) {
      event.preventDefault();
      target.focus();
    }
  }

  async function getJson(response) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  function setupWelcomeState() {
    applyLanguage(state.config.language);
    const strings = currentStrings();
    const mode = modePresentation(state.knowledgeMode, state.language);
    const defaults = localizedDefaultConfig(state.language);
    const hasCustomOrganization = (
      state.config.organizationName !== defaults.organizationName
    );
    document.title = state.config.productName;
    document.documentElement.dataset.configState = "ready";
    document.documentElement.dataset.knowledgeMode = state.knowledgeMode;
    elements.portalProduct.textContent = state.config.productName;
    elements.portalOrganization.textContent = state.config.organizationName;
    elements.portalOrganization.hidden = !hasCustomOrganization;
    elements.portalConfigStatus.hidden = true;
    elements.portalModeLabel.textContent = mode.label;
    elements.portalTitle.textContent = state.config.welcomeTitle;
    elements.portalSummary.textContent = mode.summary;
    elements.capabilityKicker.textContent = strings.availableInChat;
    elements.capabilityTitle.textContent = state.knowledgeMode === "searchBlob"
      ? strings.publicWebAndDocuments
      : strings.publicWebWithSources;
    elements.capabilityDescription.textContent = strings.bingConfigured;
    elements.documentCapability.textContent = mode.documents;
    elements.launcherLabel.textContent = formatString(strings.askAssistant, {
      assistant: state.config.assistantName,
    });
    elements.launcher.setAttribute("aria-label", formatString(strings.openAssistant, {
      assistant: state.config.assistantName,
    }));
    elements.dialogTitle.textContent = state.config.assistantName;
    elements.welcomeTitle.textContent = state.config.welcomeTitle;
    elements.welcomeSubtitle.textContent = state.config.welcomeSubtitle;
    elements.welcomeModeLabel.textContent = mode.label;
    elements.welcomeModeDescription.textContent = mode.detail;
    elements.knowledgeHint.textContent = mode.label;
    elements.messageInput.placeholder = mode.placeholder;
    elements.disclosureText.textContent = state.config.disclaimer;
    elements.dialogConfigStatus.hidden = true;
    elements.suggestedQuestions.replaceChildren();

    for (const question of state.config.suggestedQuestions) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.className = "suggestion-chip";
      button.type = "button";
      button.textContent = question;
      button.addEventListener("click", () => insertSuggestedQuestion(question));
      item.append(button);
      elements.suggestedQuestions.append(item);
    }
  }

  function setupUnavailableState(status) {
    applyLanguage(state.language);
    const strings = currentStrings();
    const presentation = configurationPresentation(status, state.language);
    const failed = status === "failed";
    document.documentElement.dataset.configState = status;
    document.documentElement.removeAttribute("data-knowledge-mode");
    elements.portalConfigStatus.hidden = false;
    elements.portalConfigStatus.dataset.state = failed ? "error" : "loading";
    elements.portalConfigStatus.setAttribute("role", failed ? "alert" : "status");
    elements.portalConfigStatus.textContent = presentation.notice;
    elements.portalModeLabel.textContent = presentation.label;
    elements.portalSummary.textContent = presentation.summary;
    elements.capabilityKicker.textContent = strings.configurationStatus;
    elements.capabilityTitle.textContent = presentation.title;
    elements.capabilityDescription.textContent = presentation.description;
    elements.documentCapability.textContent = presentation.documents;
    elements.knowledgeHint.textContent = presentation.label;
    elements.welcomeModeLabel.textContent = presentation.label;
    elements.welcomeSubtitle.textContent = presentation.welcomeSubtitle;
    elements.welcomeModeDescription.textContent = presentation.modeDescription;
    elements.messageInput.placeholder = presentation.placeholder;
    elements.dialogConfigStatus.hidden = false;
    elements.dialogConfigStatus.dataset.state = failed ? "error" : "loading";
    elements.dialogConfigStatus.setAttribute("role", failed ? "alert" : "status");
    elements.dialogConfigStatus.textContent = presentation.notice;
  }

  function insertSuggestedQuestion(text) {
    elements.messageInput.value = text.slice(0, MAX_MESSAGE_LENGTH);
    updateComposer();
    elements.messageInput.focus();
    elements.form.requestSubmit();
  }

  function updateComposer() {
    const count = elements.messageInput.value.length;
    elements.charCount.textContent = String(count);
    elements.messageInput.style.height = "auto";
    elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 120)}px`;
  }

  function showConversation() {
    elements.welcomeState.hidden = true;
    elements.conversationContainer.classList.add("visible");
    elements.clearBtn.hidden = false;
  }

  function appendPlainTextBlocks(container, text) {
    const value = typeof text === "string" ? text.replace(/\r\n?/g, "\n") : "";
    const blocks = value.split(/\n{2,}/);
    for (const block of blocks) {
      const paragraph = document.createElement("p");
      paragraph.className = "message-text";
      paragraph.textContent = block;
      container.append(paragraph);
    }
  }

  function addMessage(role, text, citations = []) {
    const strings = currentStrings();
    const article = document.createElement("article");
    article.className = `msg msg-${role === "assistant" ? "bot" : "user"}`;
    article.setAttribute(
      "aria-label",
      role === "assistant" ? strings.assistantMessage : strings.userMessage,
    );
    const avatar = document.createElement("span");
    avatar.className = "msg-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = role === "assistant" ? "AI" : strings.userAvatar;
    const content = document.createElement("div");
    content.className = "bubble";
    appendPlainTextBlocks(content, text);

    if (Array.isArray(citations) && citations.length) {
      const list = document.createElement("ul");
      list.className = "citations";
      const listLabel = document.createElement("li");
      listLabel.className = "citations-label";
      listLabel.textContent = strings.sources;
      list.append(listLabel);
      let citationCount = 0;
      for (const citation of citations) {
        if (!citation || typeof citation !== "object") continue;
        const item = document.createElement("li");
        const citationLabel = normalizedText(citation.label, strings.reference);
        const reference = typeof citation.reference === "string"
          ? citation.reference
          : "";
        if (!reference) continue;
        const title = document.createElement("span");
        title.className = "citation-title";
        title.textContent = citationLabel;
        const referenceText = document.createElement("span");
        referenceText.className = "citation-reference";
        referenceText.textContent = reference;
        if (isSafeCitationReference(reference)) {
          const link = document.createElement("a");
          link.className = "citation-link message-citation-link";
          link.href = reference;
          link.rel = "noopener noreferrer";
          link.target = "_blank";
          link.append(title, referenceText);
          item.append(link);
        } else {
          const citationText = document.createElement("span");
          citationText.className = "citation-text message-citation-text";
          citationText.append(title, referenceText);
          item.append(citationText);
        }
        list.append(item);
        citationCount += 1;
      }
      if (citationCount) content.append(list);
    }

    article.append(avatar, content);
    elements.conversation.append(article);
    window.setTimeout(() => {
      article.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 0);
  }

  function showLoading() {
    const strings = currentStrings();
    removeLoading();
    const article = document.createElement("article");
    article.className = "msg msg-bot";
    article.id = "loading-indicator";
    article.setAttribute("role", "status");
    article.setAttribute("aria-label", strings.assistantTyping);
    const avatar = document.createElement("span");
    avatar.className = "msg-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "AI";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const indicator = document.createElement("span");
    indicator.className = "typing";
    const indicatorLabel = document.createElement("span");
    indicatorLabel.className = "typing-label";
    indicatorLabel.textContent = strings.preparingAnswer;
    indicator.append(indicatorLabel);
    for (let index = 0; index < 3; index += 1) {
      const dot = document.createElement("span");
      dot.className = "typing-dot";
      indicator.append(dot);
    }
    const cancel = document.createElement("button");
    cancel.className = "cancel-btn";
    cancel.type = "button";
    cancel.textContent = strings.cancel;
    cancel.addEventListener("click", () => cancelActiveRequest(true));
    bubble.append(indicator, cancel);
    article.append(avatar, bubble);
    elements.conversation.append(article);
    window.setTimeout(() => {
      article.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 0);
  }

  function removeLoading() {
    document.querySelector("#loading-indicator")?.remove();
  }

  function clearStatus() {
    elements.statusArea.replaceChildren();
  }

  function showError(message, failedMessage = null) {
    removeLoading();
    clearStatus();
    const container = document.createElement("div");
    container.className = "status-error";
    container.setAttribute("role", "alert");
    const text = document.createElement("p");
    text.textContent = message;
    container.append(text);

    if (failedMessage) {
      const retry = document.createElement("button");
      retry.className = "retry-btn";
      retry.type = "button";
      retry.textContent = currentStrings().retry;
      retry.addEventListener("click", () => {
        clearStatus();
        void sendMessage(failedMessage);
      });
      container.append(retry);
    }
    elements.statusArea.append(container);
  }

  function showPreviousResponseError(message, failedMessage) {
    removeLoading();
    clearStatus();
    const container = document.createElement("div");
    container.className = "status-error";
    container.setAttribute("role", "alert");
    const text = document.createElement("p");
    text.textContent = message;
    const retry = document.createElement("button");
    retry.className = "retry-btn";
    retry.type = "button";
    retry.textContent = currentStrings().retryNew;
    retry.addEventListener("click", () => {
      clearStatus();
      void sendMessage(failedMessage);
    });
    const startNew = document.createElement("button");
    startNew.className = "retry-btn";
    startNew.type = "button";
    startNew.textContent = currentStrings().startNew;
    startNew.addEventListener("click", clearConversation);
    container.append(text, retry, startNew);
    elements.statusArea.append(container);
  }

  async function sendMessage(message) {
    const sequence = state.requestSequence + 1;
    state.requestSequence = sequence;
    const controller = new AbortController();
    state.requestController = controller;
    state.isLoading = true;
    elements.sendBtn.disabled = true;
    elements.messageInput.disabled = true;
    clearStatus();
    showLoading();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          ...(state.previousResponseId
            ? { previousResponseId: state.previousResponseId }
            : {}),
        }),
        signal: controller.signal,
      });
      const data = await getJson(response);
      if (!response.ok) {
        if (isPreviousResponseFailure(response.status, data)) {
          state.previousResponseId = null;
          state.lastFailedMessage = message;
          showPreviousResponseError(
            currentStrings().previousUnavailable,
            message,
          );
          return;
        }
        throw new Error("request_failed");
      }
      if (!data || typeof data.message !== "string") {
        throw new Error("invalid_response");
      }
      if (!isValidPreviousResponseId(data.previousResponseId)) {
        throw new Error("invalid_conversation");
      }
      if (sequence !== state.requestSequence) {
        return;
      }

      removeLoading();
      state.previousResponseId = data.previousResponseId;
      addMessage("assistant", data.message, data.citations);
      state.messages.push({
        role: "assistant",
        content: data.message,
        citations: Array.isArray(data.citations) ? data.citations : [],
      });
      state.lastFailedMessage = null;
      clearStatus();
    } catch (error) {
      if (sequence !== state.requestSequence || error.name === "AbortError") return;
      state.lastFailedMessage = message;
      showError(currentStrings().requestFailed, message);
    } finally {
      if (sequence === state.requestSequence) {
        state.isLoading = false;
        state.requestController = null;
        elements.sendBtn.disabled = false;
        elements.messageInput.disabled = false;
        if (elements.dialog.open) elements.messageInput.focus();
      }
    }
  }

  async function handleFormSubmit(event) {
    event.preventDefault();
    if (state.isLoading) return;
    const result = validateMessage(elements.messageInput.value);
    if (!result.valid) {
      if (result.reason === "too-long") {
        showError(formatString(currentStrings().messageTooLong, {
          maximum: MAX_MESSAGE_LENGTH,
        }));
      }
      return;
    }

    elements.messageInput.value = "";
    updateComposer();
    if (!state.messages.length) showConversation();
    addMessage("user", result.message);
    state.messages.push({ role: "user", content: result.message });
    state.lastFailedMessage = result.message;
    await sendMessage(result.message);
  }

  function handleComposerKeydown(event) {
    if (shouldSubmitComposerEvent(event)) {
      event.preventDefault();
      elements.form.requestSubmit();
    }
  }

  function clearConversation() {
    cancelActiveRequest();
    state.previousResponseId = null;
    state.messages = [];
    state.lastFailedMessage = null;
    elements.conversation.replaceChildren();
    elements.conversationContainer.classList.remove("visible");
    elements.welcomeState.hidden = false;
    elements.clearBtn.hidden = true;
    clearStatus();
    elements.messageInput.focus();
  }

  function setupEventListeners() {
    elements.launcher.addEventListener("click", openDialog);
    elements.primaryOpenBtn.addEventListener("click", openDialog);
    elements.closeBtn.addEventListener("click", closeDialog);
    elements.clearBtn.addEventListener("click", clearConversation);
    elements.dialog.addEventListener("keydown", handleDialogKeydown);
    elements.dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeDialog();
    });
    elements.dialog.addEventListener("close", finalizeDialogClose);
    elements.dialog.addEventListener("click", (event) => {
      if (event.target === elements.dialog) closeDialog();
    });
    elements.form.addEventListener("submit", handleFormSubmit);
    elements.messageInput.addEventListener("keydown", handleComposerKeydown);
    elements.messageInput.addEventListener("input", updateComposer);
  }

  async function initialize() {
    setupUnavailableState("loading");
    setupEventListeners();
    updateComposer();
    const loaded = await loadConfig();
    if (loaded.failed) {
      setupUnavailableState("failed");
      return;
    }
    state.config = loaded.config;
    state.knowledgeMode = loaded.config.knowledgeMode;
    setupWelcomeState();
  }

  window.ChatAssistant = { close: closeDialog, open: openDialog };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void initialize(), { once: true });
  } else {
    void initialize();
  }
}
