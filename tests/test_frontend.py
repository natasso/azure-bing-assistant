import json
from pathlib import Path
import subprocess
import sys
import textwrap

from app.backend.config import UIConfig
from azure_bing_assistant.localization import SUPPORTED_UI_LANGUAGES, frontend_strings


APP_JS = Path(__file__).resolve().parents[1] / "app" / "frontend" / "app.js"
INDEX_HTML = APP_JS.with_name("index.html")
LOCALES_JS = APP_JS.with_name("locales.js")
BUILD_LOCALES = APP_JS.parents[2] / "scripts" / "build_frontend_locales.py"


def run_node(source: str) -> None:
    program = textwrap.dedent(
        f"""
        const assert = require("node:assert/strict");
        const app = require(process.argv[2]);
        {source}
        """
    )
    subprocess.run(
        ["node", "-", str(APP_JS)],
        input=program,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
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
          knowledgeMode: "off",
          allowedDomains: ["example.org"],
          websiteEnforcement: "allowed_domains",
          includesSubdomains: true
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
                ? "Siti autorizzati (predefinita)"
                : "Siti autorizzati + documenti (Azure AI Search, facoltativo)"
            );
          }

          const failures = [
            async () => ({ ok: true, async json() { return { ...valid, allowedDomains: undefined }; } }),
            async () => ({ ok: true, async json() { return { ...valid, allowedDomains: [] }; } }),
            async () => ({ ok: true, async json() { return { ...valid, allowedDomains: ["*.example.org"] }; } }),
            async () => ({ ok: true, async json() { return { ...valid, websiteEnforcement: "advisory" }; } }),
            async () => ({ ok: true, async json() { return { ...valid, includesSubdomains: false }; } }),
            async () => ({ ok: false, async json() { throw new Error("unused"); } }),
            async () => { throw new TypeError("network rejected"); },
            async () => ({ ok: true, async json() { return { ...valid, knowledgeMode: "other" }; } }),
            ...["de", "EN", "en-US", "", null, {}, ["en"], "__proto__", "constructor"].map(
              (language) => async () => ({ ok: true, async json() { return { ...valid, language }; } })
            )
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
        assert.equal(web.label, "Authorized websites (default)");
        assert.match(web.detail, /Private documents are not available/);
        assert.doesNotMatch(web.summary, /documents/i);

        const documents = app.modePresentation("searchBlob", "en");
        assert.equal(
          documents.label,
          "Authorized websites + documents (Azure AI Search, optional)"
        );
        assert.match(documents.detail, /configured/);
        assert.match(documents.detail, /depends on administrator indexing/);
        assert.doesNotMatch(documents.detail, /ready|indexed successfully/i);

        const italianWeb = app.modePresentation("off", "it");
        assert.equal(italianWeb.label, "Siti autorizzati (predefinita)");
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
        assert.equal(app.normalizeLanguage("de"), "it");
        assert.deepEqual(app.SUPPORTED_LANGUAGES, [
          "it", "en", "fr", "es", "pt", "el", "he", "ar", "tr"
        ]);
        assert.deepEqual(app.RTL_LANGUAGES, ["he", "ar"]);
        for (const language of app.SUPPORTED_LANGUAGES) {
          assert.equal(app.normalizeLanguage(language), language);
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

        for (const language of [...app.SUPPORTED_LANGUAGES, "it"]) {
          const strings = app.UI_STRINGS[language];
          assert.equal(app.applyStaticLanguage(elements, root, language), language);
          assert.equal(root.lang, language);
          assert.equal(root.dir, ["he", "ar"].includes(language) ? "rtl" : "ltr");
          assert.equal(elements.messageLabel.textContent, strings.messageLabel);
          assert.equal(elements.clearBtn.textContent, strings.newChat);
          assert.equal(elements.composerHint.textContent, strings.composerHint);
          assert.equal(elements.primaryOpenLabel.textContent, strings.startConversation);
          assert.equal(elements.sendBtn.getAttribute("aria-label"), strings.sendMessage);
          assert.equal(elements.conversation.getAttribute("aria-label"), strings.conversationHistory);
          assert.equal(elements.metaDescription.getAttribute("content"), strings.metaDescription);
        }
        """
    )


def test_browser_bundle_matches_canonical_catalogs_and_backend_defaults():
    expected = {}
    for language in SUPPORTED_UI_LANGUAGES:
        ui = UIConfig(language=language)
        expected[language] = {
            "language": language,
            "productName": ui.product_name,
            "organizationName": ui.organization_name,
            "assistantName": ui.assistant_name,
            "welcomeTitle": ui.welcome_title,
            "welcomeSubtitle": ui.welcome_subtitle,
            "disclaimer": ui.disclaimer,
            "suggestedQuestions": ui.suggested_questions,
            "knowledgeMode": "off",
        }
    catalogs = {language: frontend_strings(language) for language in SUPPORTED_UI_LANGUAGES}
    run_node(
        f"""
        const expected = {json.dumps(expected)};
        const catalogs = {json.dumps(catalogs)};
        assert.deepEqual(app.UI_STRINGS, catalogs);
        (async () => {{
          for (const [language, config] of Object.entries(expected)) {{
            assert.deepEqual(app.localizedDefaultConfig(language), config);
            const loaded = await app.loadConfig(async () => ({{
              ok: true,
              async json() {{
                return {{
                  ...config,
                  allowedDomains: ["example.org"],
                  websiteEnforcement: "allowed_domains",
                  includesSubdomains: true
                }};
              }}
            }}));
            assert.equal(loaded.failed, false);
            assert.equal(loaded.config.language, language);
            assert.equal(loaded.config.assistantName, config.assistantName);
            const overridden = app.normalizeConfig({{
              ...loaded.config, welcomeTitle: "Literal title", suggestedQuestions: []
            }});
            assert.equal(overridden.welcomeTitle, "Literal title");
            assert.deepEqual(overridden.suggestedQuestions, []);
          }}
        }})().catch((error) => {{
          console.error(error);
          process.exitCode = 1;
        }});
        """
    )


def test_generated_catalog_is_current_and_browser_commonjs_exports_agree():
    subprocess.run(
        [sys.executable, str(BUILD_LOCALES), "--check"],
        check=True,
        capture_output=True,
        text=True,
    )
    run_node(
        f"""
        const fs = require("node:fs");
        const vm = require("node:vm");
        const path = {json.dumps(str(LOCALES_JS))};
        const browser = vm.createContext({{}});
        vm.runInContext(fs.readFileSync(path, "utf8"), browser);
        const bundle = require(path);
        assert.deepEqual(JSON.parse(JSON.stringify(browser.CHATBOT_I18N)), bundle);
        assert.equal(Object.isFrozen(bundle), true);
        assert.equal(Object.isFrozen(bundle.strings.he), true);
        assert.equal(Object.isFrozen(bundle.strings.ar.suggestions), true);
        vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), browser);
        assert.equal(vm.runInContext('normalizeLanguage("he")', browser), "he");
        assert.equal(vm.runInContext('stringsFor("ar").messageLabel', browser), app.UI_STRINGS.ar.messageLabel);
        """
    )


def test_generator_check_rejects_missing_or_byte_stale_bundles_without_writing(monkeypatch):
    from scripts import build_frontend_locales as build

    expected = build.generate_bundle().encode("utf-8")

    class Bundle:
        content = expected

        def is_file(self):
            return self.content is not None

        def read_bytes(self):
            return self.content

        def write_bytes(self, content):
            raise AssertionError("--check must never write")

    output = Bundle()
    monkeypatch.setattr(build, "OUTPUT", output)
    monkeypatch.setattr(sys, "argv", ["build_frontend_locales.py", "--check"])
    assert build.main() == 0
    for content in [None, expected + b" ", expected.replace(b"\n", b"\r\n")]:
        output.content = content
        assert build.main() == 1


def test_bidi_messages_citations_and_domains_use_dom_isolation_not_text_controls():
    run_node(
        r"""
        class Element {
          constructor(tagName, ownerDocument) {
            this.tagName = tagName;
            this.ownerDocument = ownerDocument;
            this.children = [];
            this.textContent = "";
          }
          append(...children) { this.children.push(...children); }
        }
        const fakeDocument = { createElement(tagName) { return new Element(tagName, this); } };
        const container = fakeDocument.createElement("div");
        const message = "שלום <script>alert(1)</script>\n\nمرحبا\nEnglish identifier";
        app.appendPlainTextBlocks(container, message);
        assert.equal(container.children.length, 2);
        for (const paragraph of container.children) {
          assert.equal(paragraph.tagName, "p");
          assert.equal(paragraph.dir, "auto");
          assert.equal(paragraph.children.length, 0);
        }
        assert.equal(container.children.map((child) => child.textContent).join("\n\n"), message);
        for (const language of ["he", "ar", "it"]) {
          const sources = fakeDocument.createElement("div");
          const references = [
            "https://example.org/document?id=123&lang=ar",
            "https://example.org/שלום",
            "http://example.org/reference",
            "******protected-source",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "https://user:password@example.org/",
          ];
          app.appendCitations(sources, references.map((reference) => ({
            label: "مصدر <img onerror=alert(1)>", reference
          })), language);
          const list = sources.children[0];
          assert.equal(list.children[0].textContent, app.UI_STRINGS[language].sources);
          references.forEach((reference, index) => {
            const target = list.children[index + 1].children[0];
            const [title, renderedReference] = target.children;
            assert.equal(title.dir, "auto");
            assert.equal(title.textContent, "مصدر <img onerror=alert(1)>");
            assert.equal(title.children.length, 0);
            assert.equal(renderedReference.tagName, "bdi");
            assert.equal(renderedReference.dir, "ltr");
            assert.equal(renderedReference.textContent, reference);
            assert.equal(renderedReference.children.length, 0);
            if (index < 3) {
              assert.equal(target.tagName, "a");
              assert.equal(target.href, reference);
              assert.equal(target.target, "_blank");
              assert.equal(target.rel, "noopener noreferrer");
            } else {
              assert.equal(target.tagName, "span");
              assert.equal(target.href, undefined);
            }
          });
        }
        const description = fakeDocument.createElement("p");
        app.setDomainDescription(description, app.UI_STRINGS.he.bingConfigured, ["example.org", "docs.example.org"]);
        assert.equal(description.textContent, app.UI_STRINGS.he.bingConfigured);
        assert.equal(description.children[1], ", ");
        for (const identifier of [description.children[0], description.children[2]]) {
          assert.equal(identifier.tagName, "bdi");
          assert.equal(identifier.dir, "ltr");
        }
        assert.equal(description.children[0].textContent, "example.org");
        assert.equal(description.children[2].textContent, "docs.example.org");
        """
    )
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'dir="auto"' in html[html.index("<textarea"):html.index("</textarea>")]
    assert '<bdi dir="ltr"><span id="char-count">' in html
    css = APP_JS.with_name("styles.css").read_text(encoding="utf-8")
    assert "unicode-bidi: plaintext;" in css
    assert "unicode-bidi: isolate;" in css
    assert "text-align: start;" in css
    assert "padding-inline-end:" in css
    assert "border-start-start-radius:" in css
    assert "border-start-end-radius:" in css
