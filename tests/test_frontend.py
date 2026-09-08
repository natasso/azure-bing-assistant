from pathlib import Path
import subprocess
import textwrap


APP_JS = Path(__file__).parents[1] / "app" / "frontend" / "app.js"
INDEX_HTML = APP_JS.with_name("index.html")


def run_node(source: str) -> None:
    program = textwrap.dedent(
        f"""
        const assert = require("node:assert/strict");
        const app = require(process.argv[1]);
        {source}
        """
    )
    subprocess.run(
        ["node", "-e", program, str(APP_JS)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_composer_submit_algorithm_respects_ime_and_shift_enter():
    run_node(
        """
        assert.equal(app.shouldSubmitComposerEvent({
          key: "Enter", shiftKey: false, isComposing: false, keyCode: 13
        }), true);
        assert.equal(app.shouldSubmitComposerEvent({
          key: "Enter", shiftKey: true, isComposing: false, keyCode: 13
        }), false);
        assert.equal(app.shouldSubmitComposerEvent({
          key: "Enter", shiftKey: false, isComposing: true, keyCode: 13
        }), false);
        assert.equal(app.shouldSubmitComposerEvent({
          key: "Enter", shiftKey: false, isComposing: false, keyCode: 229
        }), false);
        """
    )


def test_focus_wrap_algorithm_handles_edges_and_changed_control_sets():
    run_node(
        """
        const first = { id: "first" };
        const middle = { id: "middle" };
        const last = { id: "last" };
        assert.equal(app.getFocusWrapTarget([first, middle, last], last, false), first);
        assert.equal(app.getFocusWrapTarget([first, middle, last], first, true), last);
        assert.equal(app.getFocusWrapTarget([first, middle, last], middle, false), null);
        assert.equal(app.getFocusWrapTarget([first, last], middle, false), first);
        assert.equal(app.getFocusWrapTarget([first, last], middle, true), last);
        assert.equal(app.getFocusWrapTarget([], first, false), null);
        """
    )


def test_background_isolation_restores_every_prior_attribute_exactly():
    run_node(
        """
        class FakeElement {
          constructor(attributes = {}) {
            this.attributes = new Map(Object.entries(attributes));
          }
          hasAttribute(name) { return this.attributes.has(name); }
          getAttribute(name) { return this.attributes.get(name) ?? null; }
          setAttribute(name, value) { this.attributes.set(name, String(value)); }
          removeAttribute(name) { this.attributes.delete(name); }
        }
        const existing = new FakeElement({ inert: "prior", "aria-hidden": "false" });
        const clean = new FakeElement();
        const snapshots = app.isolateBackgroundElements([existing, clean]);
        assert.equal(existing.getAttribute("inert"), "");
        assert.equal(existing.getAttribute("aria-hidden"), "true");
        assert.equal(clean.getAttribute("inert"), "");
        assert.equal(clean.getAttribute("aria-hidden"), "true");
        app.restoreBackgroundElements(snapshots);
        assert.equal(existing.getAttribute("inert"), "prior");
        assert.equal(existing.getAttribute("aria-hidden"), "false");
        assert.equal(clean.hasAttribute("inert"), false);
        assert.equal(clean.hasAttribute("aria-hidden"), false);
        """
    )


def test_focus_restoration_prefers_the_actual_opener_then_fallback():
    run_node(
        """
        const opener = {
          isConnected: true, disabled: false, calls: 0,
          focus() { this.calls += 1; }
        };
        const fallback = {
          isConnected: true, disabled: false, calls: 0,
          focus() { this.calls += 1; }
        };
        assert.equal(app.restoreFocus(opener, fallback), opener);
        assert.equal(opener.calls, 1);
        assert.equal(fallback.calls, 0);
        opener.isConnected = false;
        assert.equal(app.restoreFocus(opener, fallback), fallback);
        assert.equal(fallback.calls, 1);
        """
    )


def test_citations_only_link_valid_http_or_https_urls():
    run_node(
        """
        assert.equal(app.isSafeCitationReference("https://example.test/doc"), true);
        assert.equal(app.isSafeCitationReference("HTTP://example.test/doc"), true);
        assert.equal(app.isSafeCitationReference("javascript:alert(1)"), false);
        assert.equal(app.isSafeCitationReference("data:text/html,test"), false);
        assert.equal(app.isSafeCitationReference("//example.test/doc"), false);
        assert.equal(app.isSafeCitationReference("https://user:secret@example.test"), false);
        assert.equal(app.isSafeCitationReference("not a url"), false);
        """
    )


def test_frontend_message_validation_enforces_the_8000_character_limit():
    run_node(
        """
        assert.equal(app.validateMessage("x".repeat(8000)).valid, true);
        assert.deepEqual(app.validateMessage("x".repeat(8001)), {
          valid: false, message: "x".repeat(8001), reason: "too-long"
        });
        assert.equal(app.validateMessage("   ").reason, "empty");
        """
    )


def test_config_normalization_keeps_valid_empty_lists_and_falls_back_safely():
    run_node(
        """
        assert.deepEqual(app.normalizeConfig({
          language: "it", suggestedQuestions: []
        }).suggestedQuestions, []);
        const config = app.normalizeConfig({
          language: "it",
          assistantName: "",
          suggestedQuestions: [" Valid ", null, "", 4, "Second"]
        });
        assert.equal(config.assistantName, "Assistente");
        assert.deepEqual(config.suggestedQuestions, ["Valid", "Second"]);
        assert.equal(app.normalizeConfig(null).suggestedQuestions.length, 5);
        assert.equal(app.normalizeConfig(null).knowledgeMode, "off");
        assert.equal(app.normalizeConfig(null).language, "it");
        assert.equal(app.normalizeConfig({ language: "en" }).assistantName, "Assistant");
        """
    )


def test_config_load_requires_valid_payload_and_never_invents_a_failed_mode():
    run_node(
        """
        const valid = {
          language: "it",
          productName: "Product",
          organizationName: "Organization",
          assistantName: "Assistant",
          welcomeTitle: "Welcome",
          welcomeSubtitle: "Ask a question.",
          disclaimer: "Verify important information.",
          suggestedQuestions: [],
          knowledgeMode: "off"
        };
        (async () => {
          for (const knowledgeMode of ["off", "searchBlob"]) {
            const loaded = await app.loadConfig(async () => ({
              ok: true,
              async json() { return { ...valid, knowledgeMode }; }
            }));
            assert.equal(loaded.failed, false);
            assert.equal(loaded.config.knowledgeMode, knowledgeMode);
            assert.equal(
              app.modePresentation(
                loaded.config.knowledgeMode,
                loaded.config.language
              ).label,
              knowledgeMode === "off"
                ? "Chat web Bing (predefinita)"
                : "Bing + documenti (Azure AI Search, facoltativo)"
            );
          }

          const failures = [
            async () => ({ ok: false, async json() { throw new Error("unused"); } }),
            async () => { throw new TypeError("network rejected"); },
            async () => ({ ok: true, async json() { return { ...valid, knowledgeMode: "other" }; } }),
            async () => ({ ok: true, async json() { return { ...valid, language: "fr" }; } })
          ];
          for (const fetchImpl of failures) {
            const loaded = await app.loadConfig(fetchImpl);
            assert.deepEqual(loaded, { config: null, failed: true });
          }
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )


def test_initial_and_failed_config_states_make_no_capability_claims():
    run_node(
        """
        for (const language of ["it", "en"]) {
          for (const status of ["loading", "failed"]) {
            const state = app.configurationPresentation(status, language);
            const copy = Object.values(state).join(" ");
            assert.doesNotMatch(copy, /Bing web chat|Chat web Bing|grounding is configured/i);
            assert.doesNotMatch(copy, /Azure AI Search (is|è) configurat/i);
            assert.match(copy, /configur|funzionalit|capabilit/i);
          }
        }
        """
    )
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="portal-config-status"' in html
    assert 'id="dialog-config-status"' in html
    assert 'html lang="it"' in html
    assert ">Caricamento della configurazione dell'assistente.</p>" in html
    assert "Start a conversation" not in html
    assert "Loading assistant configuration" not in html
    assert "Bing web grounding is configured" not in html
    assert "Bing web chat (default)" not in html
    assert "Azure AI Search is configured" not in html


def test_human_facing_mode_copy_is_explicit_and_does_not_overpromise():
    run_node(
        """
        const web = app.modePresentation("off", "en");
        assert.equal(web.label, "Bing web chat (default)");
        assert.match(web.detail, /Private documents are not available/);
        assert.doesNotMatch(web.summary, /documents/i);

        const documents = app.modePresentation("searchBlob", "en");
        assert.equal(
          documents.label,
          "Bing + your documents (Azure AI Search, optional)"
        );
        assert.match(documents.detail, /configured/);
        assert.match(documents.detail, /depends on administrator indexing/);
        assert.doesNotMatch(documents.detail, /ready|indexed successfully/i);

        const italianWeb = app.modePresentation("off", "it");
        assert.equal(italianWeb.label, "Chat web Bing (predefinita)");
        assert.match(italianWeb.detail, /documenti privati non sono disponibili/i);
        const italianDocuments = app.modePresentation("searchBlob", "it");
        assert.match(italianDocuments.detail, /dipende dall'indicizzazione/i);
        """
    )


def test_frontend_uses_one_config_request_and_plain_text_rendering():
    source = APP_JS.read_text(encoding="utf-8")

    assert 'fetchImpl("/api/config")' in source
    assert 'fetch("/health")' not in source
    assert "paragraph.textContent = block;" in source
    assert "referenceText.textContent = reference;" in source
    assert ".innerHTML" not in source
    assert "Searching Bing" not in source


def test_opaque_previous_response_validation_and_recovery_code_are_explicit():
    run_node(
        """
        assert.equal(app.isValidPreviousResponseId("provider:id/with+opaque=_"), true);
        assert.equal(app.isValidPreviousResponseId(""), false);
        assert.equal(app.isValidPreviousResponseId("a\\nb"), false);
        assert.equal(app.isValidPreviousResponseId("x".repeat(4097)), false);
        assert.equal(app.isPreviousResponseFailure(409, {
          code: "invalid_previous_response"
        }), true);
        assert.equal(app.isPreviousResponseFailure(503, {
          code: "invalid_previous_response"
        }), false);
        assert.equal(app.isPreviousResponseFailure(409, {
          code: "unknown"
        }), false);
        """
    )


def test_invalid_previous_response_clears_before_explicit_non_looping_choices():
    source = APP_JS.read_text(encoding="utf-8")
    failure = source.index("if (isPreviousResponseFailure(response.status, data))")
    clear = source.index("state.previousResponseId = null;", failure)
    recovery = source.index("showPreviousResponseError(", clear)
    assert failure < clear < recovery
    assert "retry.textContent = currentStrings().retryNew" in source
    assert "startNew.textContent = currentStrings().startNew" in source
    assert "void sendMessage(failedMessage)" in source
    assert "discardContinuation" not in source
    assert "/api/" + "conversation/" not in source
    assert "/api/chat/" + "cancel" not in source


def test_cancel_new_and_late_completion_keep_browser_continuity_client_side():
    source = APP_JS.read_text(encoding="utf-8")
    cancel = source[source.index("function cancelActiveRequest"):source.index("function openDialog")]
    clear = source[source.index("function clearConversation"):source.index("function setupEventListeners")]
    success_start = source.index("if (sequence !== state.requestSequence)")
    success = source[success_start:source.index("} catch (error)", success_start)]

    assert "state.previousResponseId =" not in cancel
    assert "state.previousResponseId = null;" in clear
    assert "if (sequence !== state.requestSequence)" in success
    assert "state.previousResponseId = data.previousResponseId;" in success


def test_translation_dictionary_has_exact_key_parity_and_complete_core_states():
    run_node(
        """
        assert.deepEqual(
          Object.keys(app.UI_STRINGS.it).sort(),
          Object.keys(app.UI_STRINGS.en).sort()
        );
        assert.equal(app.DEFAULT_LANGUAGE, "it");
        assert.equal(app.normalizeLanguage("en"), "en");
        assert.equal(app.normalizeLanguage("fr"), "it");
        for (const language of ["it", "en"]) {
          const strings = app.UI_STRINGS[language];
          for (const [key, value] of Object.entries(strings)) {
            assert.ok(
              (typeof value === "string" && value.length > 0)
              || (Array.isArray(value) && value.length === 5),
              `${language}.${key} must be populated`
            );
          }
          for (const mode of ["off", "searchBlob"]) {
            const presentation = app.modePresentation(mode, language);
            assert.deepEqual(
              Object.keys(presentation).sort(),
              ["detail", "documents", "label", "placeholder", "summary"]
            );
          }
          for (const status of ["loading", "failed"]) {
            assert.ok(app.configurationPresentation(status, language).notice);
          }
        }
        """
    )


def test_selected_language_updates_actual_static_controls_including_composer_hint():
    run_node(
        """
        class FakeElement {
          constructor() {
            this.textContent = "";
            this.title = "";
            this.attributes = new Map();
          }
          setAttribute(name, value) {
            this.attributes.set(name, String(value));
          }
          getAttribute(name) {
            return this.attributes.get(name);
          }
        }
        const elements = {
          metaDescription: new FakeElement(),
          primaryOpenLabel: new FakeElement(),
          launcher: new FakeElement(),
          closeBtn: new FakeElement(),
          clearBtn: new FakeElement(),
          conversation: new FakeElement(),
          messageLabel: new FakeElement(),
          sendBtn: new FakeElement(),
          composerHint: new FakeElement(),
        };
        const root = { lang: "" };

        assert.equal(app.applyStaticLanguage(elements, root, "en"), "en");
        assert.equal(root.lang, "en");
        assert.equal(
          elements.composerHint.textContent,
          "Enter to send · Shift+Enter for a new line"
        );
        assert.equal(elements.primaryOpenLabel.textContent, "Start a conversation");
        assert.equal(elements.clearBtn.textContent, "New chat");
        assert.equal(elements.messageLabel.textContent, "Message");
        assert.equal(elements.sendBtn.getAttribute("aria-label"), "Send message");
        assert.equal(
          elements.conversation.getAttribute("aria-label"),
          "Conversation history"
        );

        assert.equal(app.applyStaticLanguage(elements, root, "it"), "it");
        assert.equal(root.lang, "it");
        assert.equal(
          elements.composerHint.textContent,
          "Invio per inviare · Maiusc+Invio per andare a capo"
        );
        assert.equal(elements.primaryOpenLabel.textContent, "Inizia una conversazione");
        assert.equal(elements.clearBtn.textContent, "Nuova chat");
        assert.equal(elements.messageLabel.textContent, "Messaggio");
        assert.equal(elements.sendBtn.getAttribute("aria-label"), "Invia messaggio");
        """
    )
