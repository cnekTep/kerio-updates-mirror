// ========================
// Constants
// ========================

const AUTO_REFRESH_INTERVAL = 5; // seconds
const STORAGE_KEYS = {
    theme: "theme",
    autoRefresh: "log-auto-refresh",
    autoScroll: "log-auto-scroll",
};

// ========================
// Helpers
// ========================

/** Scrolls to the bottom of the page smoothly */
const scrollToBottom = () =>
    window.scrollTo({top: document.body.scrollHeight, behavior: "smooth"});

/** Thin wrapper around localStorage for cleaner access */
const store = {
    get: (key) => localStorage.getItem(key),
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
// Theme toggle
// ========================
/**
 * Applies theme to <html>, persists it in a cookie so the server
 * can render the correct theme on the next page load (no FOUC),
 * and updates the toggle button title.
 */
function applyTheme(theme) {
    const html = document.documentElement;
    html.dataset.theme = theme;

    // Persist theme in a cookie (read by the server on next request).
    // 1 year expiry, available on all paths.
    document.cookie = `theme=${theme}; path=/; max-age=31536000; samesite=lax`;

    // Guard: button may not exist on all pages
    document.getElementById("themeToggle")?.setAttribute(
        "title",
        theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
    );
}

document.getElementById("themeToggle")?.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

// Theme is already applied server-side via the data-theme attribute
// (no flash, no JS needed on load) - just sync the button title here.
const currentTheme = document.documentElement.dataset.theme || "dark";
document.getElementById("themeToggle")?.setAttribute(
    "title",
    currentTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"
);

// ========================
// Log page: Auto-refresh & Auto-scroll
// ========================

function setAutoRefresh(enabled) {
    const refreshBtn = document.getElementById("refresh-btn");
    // Guard: button may not exist on all pages
    if (!refreshBtn) return;
    refreshBtn.setAttribute(
        "hx-trigger",
        enabled ? `every ${AUTO_REFRESH_INTERVAL}s, click` : "click"
    );
    htmx.process(refreshBtn);
}

function initLogControls() {
    const autoRefresh = document.getElementById("auto-refresh");
    const autoScroll = document.getElementById("auto-scroll");

    // Guard: both controls must exist on this page
    if (!autoRefresh || !autoScroll) return;

    // Guard against duplicate listeners on repeated HTMX swaps
    if (autoRefresh.dataset.logInitialized) return;
    autoRefresh.dataset.logInitialized = "true";

    // Restore saved state
    autoRefresh.checked = store.getBool(STORAGE_KEYS.autoRefresh);
    autoScroll.checked = store.getBool(STORAGE_KEYS.autoScroll);

    setAutoRefresh(autoRefresh.checked);
    if (autoScroll.checked) scrollToBottom();

    bindCheckbox(autoRefresh, STORAGE_KEYS.autoRefresh, setAutoRefresh);
    bindCheckbox(autoScroll, STORAGE_KEYS.autoScroll, (checked) => {
        if (checked) scrollToBottom();
    });
}

// ========================
// Toggle controls (data-attribute driven)
// ========================

/**
 * Applies an effect to a target element based on its data-effect value.
 * Supports multiple space-separated effects: e.g. data-effect="disabled aria-disabled"
 *   "disabled"      - sets/removes the disabled property; resets checkboxes when disabling
 *   "aria-disabled" - sets aria-disabled to "true" or "false"
 *   "hidden"        - toggles data-hidden attribute (allows CSS transitions)
 *
 * @param {Element} target
 * @param {boolean} active - true when the parent checkbox is checked
 */
function applyEffect(target, active) {
    const effects = (target.dataset.effect || "").split(" ");

    if (effects.includes("disabled")) {
        target.disabled = !active;
        // Reset only checkboxes (fieldset and other inputs are left as-is)
        if (!active && target.type === "checkbox") target.checked = false;
    }
    if (effects.includes("aria-disabled")) {
        target.setAttribute("aria-disabled", String(!active));
    }
    if (effects.includes("hidden")) {
        // Use data-hidden attribute instead of display:none to allow CSS transitions
        target.toggleAttribute("data-hidden", !active);
    }
}

/**
 * Scans root for all [data-controls] checkboxes and wires them to their
 * dependents ([data-controlled-by="<group>"][data-effect="<effect>"]).
 * Scoped to root to avoid re-scanning the entire document on every HTMX swap.
 * No manual config needed - relationships are declared entirely in HTML.
 *
 * @param {Document|Element} root
 */
function initToggleControls(root = document) {
    root.querySelectorAll("[data-controls]").forEach((toggle) => {
        // Guard against duplicate listeners on repeated HTMX swaps
        if (toggle.dataset.toggleInitialized) return;
        toggle.dataset.toggleInitialized = "true";

        const group = toggle.dataset.controls;
        const targets = document.querySelectorAll(`[data-controlled-by="${group}"]`);

        toggle.addEventListener("change", () => {
            targets.forEach((target) => applyEffect(target, toggle.checked));
        });
    });
}

// ========================
// Sortable (drag-and-drop priority lists)
// ========================

/**
 * Initializes SortableJS on all .sortable elements found within root.
 * Guards against double-init on repeated HTMX swaps.
 *
 * @param {Document|Element} root
 */
function initSortable(root) {
    root.querySelectorAll(".sortable").forEach((el) => {
        if (el.dataset.sortableInitialized) return;
        el.dataset.sortableInitialized = "true";

        new Sortable(el, {
            animation: 150,
            ghostClass: "sortable-ghost",
        });
    });
}

/**
 * Syncs the sortable priority list with connection method checkboxes.
 * Checking a method appends it to the list; unchecking removes it.
 * Only runs on pages that have both [data-sort-key] checkboxes and #sortable-priority.
 */
function initSortableSync() {
    const list = document.getElementById("sortable-priority");
    // Guard: only runs on the connection settings page
    if (!list) return;

    document.querySelectorAll("[data-sort-key]").forEach((checkbox) => {
        if (checkbox.dataset.sortSyncInitialized) return;
        checkbox.dataset.sortSyncInitialized = "true";

        const key = checkbox.dataset.sortKey;

        checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
                // Append a new item using the human-readable label
                const label = checkbox.dataset.sortLabel || key;
                const item = document.createElement("div");
                item.className = "sortable-item";
                item.dataset.key = key;
                item.innerHTML = `<input type="hidden" name="download_priority" value="${key}">${label}`;
                list.appendChild(item);
            } else {
                list.querySelector(`[data-key="${key}"]`)?.remove();
            }
        });
    });
}

// ========================
// Save settings notification
// ========================

/**
 * Shows a temporary dialog with a success or error message after a form POST.
 * Dialog is looked up on each request so it works with HTMX partial rendering.
 */
document.addEventListener("htmx:afterRequest", (e) => {
    // Guard: only handle form POST requests
    if (e.detail.requestConfig.verb !== "post") return;

    // Guard: if the server triggered a redirect, the page is about to
    // navigate away, so showing the dialog would just cause a flash
    if (e.detail.xhr.getResponseHeader("HX-Redirect")) return;

    const saveDialog = document.getElementById("save-dialog");
    const saveDialogMessage = document.getElementById("save-dialog-message");

    // Guard: dialog may not exist on all pages
    if (!saveDialog || !saveDialogMessage) return;

    const ok = e.detail.successful;
    const isDistroUpload = e.detail.elt.id === "distro-upload-form";

    if (ok) {
        saveDialogMessage.textContent = isDistroUpload
            ? "✓ File successfully uploaded and signed"
            : "✓ Settings saved";
    } else {
        // Try to extract detail message from JSON response (e.g. 422 validation error)
        try {
            const body = JSON.parse(e.detail.xhr.responseText);
            saveDialogMessage.textContent = `✗ ${body.detail ?? "Failed to save settings"}`;
        } catch {
            saveDialogMessage.textContent = "✗ Failed to save settings";
        }
    }

    saveDialog.dataset.state = ok ? "success" : "error";
    saveDialog.showModal();

    // Auto-close after 2s for success, 4s for errors
    clearTimeout(saveDialog._hideTimer);
    saveDialog._hideTimer = setTimeout(() => saveDialog.close(), ok ? 2000 : 4000);
});

// ========================
// Boot
// ========================

document.addEventListener("DOMContentLoaded", () => {
    initLogControls();
    initToggleControls(document);

    // Update aria-current on sidebar links based on current path
    const path = window.location.pathname;
    document.querySelectorAll("aside nav a").forEach((a) => {
        a.toggleAttribute("aria-current", a.getAttribute("href") === path);
    });

    // Guard: SortableJS may not be loaded on all pages
    if (typeof Sortable !== "undefined") {
        initSortable(document);
        initSortableSync();
    }
});

document.addEventListener("htmx:afterSettle", (e) => {
    const target = e.detail.target;

    // Update aria-current on sidebar links based on current path
    const path = window.location.pathname;
    document.querySelectorAll("aside nav a").forEach((a) => {
        a.toggleAttribute("aria-current", a.getAttribute("href") === path);
    });

    // Scroll to bottom when log content updates and auto-scroll is enabled
    if (document.getElementById("auto-scroll")?.checked && target?.id === "log-content") {
        scrollToBottom();
    }

    // Re-initialize log controls only if the relevant panel was swapped in
    // (avoids duplicate event listeners on unrelated swaps)
    const isLogPanel = target?.id === "log-content" || target?.querySelector?.("#auto-refresh") !== null;
    if (isLogPanel) initLogControls();

    // Scope toggle init to the swapped subtree, not the whole document
    initToggleControls(target);

    // Guard: SortableJS may not be loaded on all pages
    if (typeof Sortable !== "undefined") {
        initSortable(target);
        initSortableSync();
    }
});