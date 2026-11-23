// ========================
// Constants
// ========================

// Unique per page load; lets the server keep a single log stream per browser tab
const TAB_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
const STORAGE_KEYS = {
    autoRefresh: "log-auto-refresh",
};


// ========================
// Helpers
// ========================

/** Scrolls to the bottom of the page smoothly. Used by hx-on handlers in log.html */
const scrollToBottom = () =>
    window.scrollTo({top: document.body.scrollHeight, behavior: "smooth"});

/** Thin wrapper around localStorage for cleaner access */
const store = {
    getBool: (key) => localStorage.getItem(key) === "true",
    set: (key, value) => localStorage.setItem(key, String(value)),
};

/**
 * Binds a checkbox to a localStorage key and an optional side-effect callback.
 * Saves the value on every change and calls onChange with the new boolean state.
 */
function bindCheckbox(el, storageKey, onChange) {
    el.addEventListener("change", () => {
        store.set(storageKey, el.checked);
        onChange?.(el.checked);
    });
}


// ========================
// Log page: live stream (SSE) & Auto-refresh
// ========================
//
// How the stream works:
//  - Every page load gets its own TAB_ID; the server keeps ONE stream per TAB_ID.
//  - Opening a new stream with the same TAB_ID makes the server end the previous
//    one with a "superseded" event (hx-sse:close turns that into a final close,
//    so the extension does not reconnect).
//  - A "stop" request ends the stream without opening a new one. It is needed
//    because removing the stream element does not reliably close the connection.
//  - Message ids are byte offsets; the extension sends the last one as
//    Last-Event-ID on reconnect, so the server can resume without a snapshot.

// URL of the stream this tab may have open on the server (null = none)
let activeStreamUrl = null;

// Resolves when the last "stop" request has reached the server
let pendingStop = Promise.resolve();

/** Asks the server to end this tab's stream and forgets about it */
function stopStream() {
    // Nothing to stop if this tab never opened a stream
    if (!activeStreamUrl) return;

    // DELETE ends the stream state on the server; same URL as the stream itself
    pendingStop = fetch(`${activeStreamUrl}?client=${TAB_ID}`, {method: "DELETE"}).catch(() => {
    });
    activeStreamUrl = null;
}

/** Adds the hidden element that makes the sse extension open the connection */
function openStream(url) {
    activeStreamUrl = url;

    const el = document.createElement("div");
    el.id = "log-stream";
    el.hidden = true;
    el.setAttribute("hx-sse:connect", `${url}?client=${TAB_ID}`);
    el.setAttribute("hx-sse:close", "superseded"); // Final close, no reconnect
    el.setAttribute("hx-target", "#log-list");
    el.setAttribute("hx-swap", "beforeend");

    document.getElementById("log-component")?.appendChild(el);
    // Needed for swaps; on a full page load see the setTimeout in the Boot section
    htmx.process(el);
}

/** Opens or closes the log stream according to the Auto-refresh checkbox */
async function setAutoRefresh(enabled) {
    const url = document.getElementById("auto-refresh")?.dataset.streamUrl;
    if (!url) return;

    document.getElementById("log-stream")?.remove();

    if (!enabled) {
        stopStream();
        return;
    }

    // Wait so a late "stop" cannot kill the stream we are about to open
    await pendingStop;

    // State may have changed while waiting
    if (!document.getElementById("auto-refresh")?.checked) return;
    if (document.getElementById("log-stream")) return;

    openStream(url);
}

/** Ends the stream when the log page was swapped out for a non-log page */
function stopStreamIfLeftLogPage() {
    // Switching between logs keeps #log-component, and the new stream
    // supersedes the old one, so only a real exit needs an explicit stop
    if (!document.getElementById("log-component")) stopStream();
}

/** Restores the saved Auto-refresh state and wires the checkbox (once per element) */
function initLogControls() {
    const autoRefresh = document.getElementById("auto-refresh");

    // Guard: the control must exist on this page
    if (!autoRefresh) return;

    // Guard against duplicate listeners on repeated HTMX swaps
    if (autoRefresh.dataset.logInitialized) return;
    autoRefresh.dataset.logInitialized = "true";

    // Restore saved state
    autoRefresh.checked = store.getBool(STORAGE_KEYS.autoRefresh);

    setAutoRefresh(autoRefresh.checked);

    bindCheckbox(autoRefresh, STORAGE_KEYS.autoRefresh, setAutoRefresh);
}


// ========================
// Save settings notification
// ========================

/**
 * Builds a readable message for client-side request failures (no server response).
 * Returns null when the failure is not recognized.
 */
function describeRequestError(detail) {
    const raw = [detail.ctx?.status, detail.error?.name, detail.error?.message]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

    if (raw.includes("timeout")) return "Request timed out";
    if (raw.includes("abort")) return "Request was cancelled";
    // Chrome: "Failed to fetch", Firefox: "NetworkError...", Safari: "Load failed"
    if (/failed to fetch|networkerror|load failed/.test(raw)) {
        return "Network error: server is unreachable";
    }
    return null;
}

/**
 * Shows a temporary dialog with a success or error message after a form POST.
 * Dialog is looked up on each call so it works with HTMX partial rendering.
 *
 * @param {boolean} ok - whether the request succeeded
 * @param {string|undefined} elId - id of the element that triggered the request
 * @param {string} [responseText] - raw response body, used to extract error details
 */
function showSaveDialog(ok, elId, responseText = "", errorMessage = null) {
    // Guard: skip elements that shouldn't trigger the save dialog
    if (elId === "api-read-token-generate-btn" || elId === "api-write-token-generate-btn") return;

    const saveDialog = document.getElementById("save-dialog");
    const saveDialogMessage = document.getElementById("save-dialog-message");

    // Guard: dialog may not exist on all pages
    if (!saveDialog || !saveDialogMessage) return;

    const isDistroUpload =
        elId === "distro-control-upload" || elId === "distro-connect-upload";
    const isLicenseExpDate = elId === "get-lic-exp-date-btn";
    const isTestEmail = elId === "test-email-btn";
    const isTelegramEmail =
        elId === "test-telegram-btn" ||
        elId === "test-telegram-updates-btn" ||
        elId === "test-telegram-errors-btn";

    if (ok) {
        if (isDistroUpload) {
            saveDialogMessage.textContent = "✓ File successfully uploaded and signed";
        } else if (isLicenseExpDate) {
            saveDialogMessage.textContent = "✓ License expiration date fetched";
        } else if (isTestEmail) {
            saveDialogMessage.textContent = "✓ Test email sent";
        } else if (isTelegramEmail) {
            saveDialogMessage.textContent = "✓ Test Telegram message sent";
        } else {
            saveDialogMessage.textContent = "✓ Settings saved";
        }
    } else if (errorMessage) {
        // Client-side failure (timeout, network error): there is no server response to parse
        saveDialogMessage.textContent = `✗ ${errorMessage}`;
    } else {
        // Try to extract detail message from JSON response (e.g. 422 validation error)
        try {
            const body = JSON.parse(responseText);
            const detail = body.detail;

            // FastAPI returns a list of {loc, msg, ...} objects for validation errors
            const text = Array.isArray(detail)
                ? detail.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ")
                : detail;

            saveDialogMessage.textContent = `✗ ${text ?? "Failed to save settings"}`;
        } catch {
            const fallback = isLicenseExpDate
                ? "Failed to fetch license expiration date"
                : "Failed to save settings";
            saveDialogMessage.textContent = `✗ ${fallback}`;
        }
    }

    saveDialog.dataset.state = ok ? "success" : "error";
    saveDialog.showModal();

    // Auto-close after 2s for success, 4s for errors
    clearTimeout(saveDialog._hideTimer);
    saveDialog._hideTimer = setTimeout(() => saveDialog.close(), ok ? 2000 : 4000);
}

// Fires after any response (including 4xx/5xx), but not on network errors or timeouts
document.addEventListener("htmx:after:request", (e) => {
    const ctx = e.detail.ctx;

    // Guard: only handle POST requests
    if (ctx.request?.method?.toLowerCase() !== "post") return;

    // Guard: if the server triggered a redirect, the page is about to
    // navigate away, so showing the dialog would just cause a flash
    if (ctx.response?.headers?.get("HX-Redirect")) return;

    const status = ctx.response?.status ?? 0;
    showSaveDialog(status >= 200 && status < 400, ctx.sourceElement?.id, ctx.text);
});

// Network errors and timeouts never reach htmx:after:request - report them here
document.addEventListener("htmx:error", (e) => {
    const ctx = e.detail.ctx;
    if (ctx?.request?.method?.toLowerCase() !== "post") return;

    showSaveDialog(
        false,
        ctx.sourceElement?.id ?? e.detail.elt?.id,
        "",
        describeRequestError(e.detail)
    );
});


// ========================
// Boot
// ========================

document.addEventListener("DOMContentLoaded", () => {
    // Deferred on purpose: on a full page load htmx scans the document itself,
    // and starting the stream earlier makes it process the stream element twice
    // (two connections, the second supersedes the first). Check Network after F5
    // if the script order ever changes.
    setTimeout(initLogControls, 0);
});

document.addEventListener("htmx:after:swap", () => {
    stopStreamIfLeftLogPage();

    // Safe to call on every swap: it returns early if controls are missing or already initialized
    initLogControls();
});