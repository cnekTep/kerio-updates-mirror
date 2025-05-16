const App = {
    // Constants
    CHECK_INTERVAL_CONNECTED: 60000,
    CHECK_INTERVAL_DISCONNECTED: 15000,
    LOG_UPDATE_INTERVAL: 2000,

    // Cached items
    elements: {
        torStatus: document.getElementById('tor_status'),
        statusIndicator: document.querySelector('#tor_status .status-indicator'),
        tabLinks: document.querySelectorAll('.tab-link'),
        tabContents: document.querySelectorAll('.tab-content'),
        updateLabel: document.querySelector('.update-label'),
        logControls: {
            system: document.getElementById('system_log_controls'),
            updates: document.getElementById('updates_log_controls')
        },
        proxyElements: {
            useProxyCheckbox: document.getElementById("use_proxy"),
            proxySettingsDiv: document.getElementById("proxy_settings"),
            proxyHost: document.getElementById("proxy_host"),
            proxyPort: document.getElementById("proxy_port"),
            form: document.querySelector("form")
        },
        updateElements: {
            updateStatus: document.getElementById('update-status'),
            currentVersion: document.getElementById('current-version'),
            latestVersion: document.getElementById('latest-version'),
            lastCheck: document.getElementById('last-check'),
            updateAvailable: document.getElementById('update-available'),
            updateChanges: document.getElementById('update-changes'),
            checkUpdatesBtn: document.getElementById('check-updates-btn')
        }
    },

    // States
    state: {
        torConnected: false,
        currentCheckInterval: null,
        torStatusInterval: null
    },

    // Application initialization
    init() {
        this.setupTabs();
        this.initLogSettings();
        this.setupTorStatusChecks();
        this.setupLanguageSwitcher();
        this.setupGeoCheckboxes();
        this.setupProxySettings();
        this.setupUpdateChecker();
        setInterval(this.updateLogs.bind(this), this.LOG_UPDATE_INTERVAL);
        window.addEventListener('hashchange', this.handleHashChange.bind(this));
        this.handleHashChange();
    },

    // Processing URL hash changes
    handleHashChange() {
        const tabId = location.hash.slice(1) || 'system_log';
        const tabLink = document.querySelector(`.tab-link[data-tab="${tabId}"]`);
        if (tabLink) this.activateTab(tabLink);
    },

    // Tab activation
    activateTab(tabLink) {
        this.elements.tabLinks.forEach(link => link.classList.remove('active'));
        this.elements.tabContents.forEach(content => content.classList.remove('active'));
        tabLink.classList.add('active');
        const tabId = tabLink.getAttribute('data-tab');
        document.getElementById(tabId).classList.add('active');
        if (['system_log', 'updates_log'].includes(tabId)) {
            setTimeout(this.updateLogs.bind(this), 100);
        }
    },

    // Setting up Tab switching
    setupTabs() {
        this.elements.tabLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const tabId = link.getAttribute('data-tab');
                history.pushState(null, null, '#' + tabId);
                this.activateTab(link);
            });
        });
    },

    // Initializing log settings
    initLogSettings() {
        const settings = [
            'system_log_autoupdate', 'system_log_autoscroll',
            'updates_log_autoupdate', 'updates_log_autoscroll'
        ];
        settings.forEach(id => {
            const el = document.getElementById(id);
            el.checked = localStorage.getItem(id) === null ? true : localStorage.getItem(id) === 'true';
            el.addEventListener('change', () => localStorage.setItem(id, el.checked));
        });
    },

    // Updating logs
    updateLogs() {
        this.updateLog('system_log', '/get_system_log', 'system-log');
        this.updateLog('updates_log', '/get_updates_log', 'updates-log');
    },

    // Updating a specific log
    updateLog(logId, logUrl, className) {
        const tab = document.getElementById(logId);
        if (tab.classList.contains('active') && document.getElementById(logId + '_autoupdate').checked) {
            fetch(logUrl)
                .then(response => response.text())
                .then(text => {
                    const logElement = document.querySelector(`#${logId} .${className}`);
                    if (logElement) {
                        logElement.innerHTML = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        if (document.getElementById(logId + '_autoscroll').checked) {
                            logElement.scrollTop = logElement.scrollHeight;
                        }
                    }
                })
                .catch(console.error);
        }
    },


    // TOR Status Update
    updateTorStatus() {
        const {statusIndicator} = this.elements;
        statusIndicator.classList.remove('status-ok', 'status-error');
        statusIndicator.classList.add('status-loading');
        statusIndicator.textContent = window.TRANSLATIONS.CHECKING;

        fetch('/tor_status')
            .then(response => response.json())
            .then(data => {
                statusIndicator.classList.remove('status-loading');
                this.state.torConnected = data.status;
                if (data.status) {
                    statusIndicator.textContent = window.TRANSLATIONS.CONNECTED;
                    statusIndicator.classList.add('status-ok');
                    this.elements.torStatus.title = `${window.TRANSLATIONS.LAST_CHECK} ${new Date(data.last_check * 1000).toLocaleTimeString()}\n${window.TRANSLATIONS.CHECKS_COMPLETED} ${data.check_count}`;
                } else {
                    statusIndicator.textContent = window.TRANSLATIONS.DISABLED;
                    statusIndicator.classList.add('status-error');
                    this.elements.torStatus.title = `${window.TRANSLATIONS.ERROR} ${data.error}\n${window.TRANSLATIONS.LAST_CHECK} ${new Date(data.last_check * 1000).toLocaleTimeString()}`;
                }
                this.updateCheckInterval();
            })
            .catch(() => {
                statusIndicator.classList.remove('status-loading');
                statusIndicator.textContent = window.TRANSLATIONS.ERROR;
                statusIndicator.classList.add('status-error');
                this.updateCheckInterval();
            });
    },

    // Updating TOR verification interval
    updateCheckInterval() {
        const interval = this.state.torConnected ? this.CHECK_INTERVAL_CONNECTED : this.CHECK_INTERVAL_DISCONNECTED;
        if (this.state.currentCheckInterval !== interval) {
            clearInterval(this.state.torStatusInterval);
            this.state.currentCheckInterval = interval;
            this.state.torStatusInterval = setInterval(this.updateTorStatus.bind(this), interval);
        }
    },

    // Setting up TOR Status Checks
    setupTorStatusChecks() {
        const useTor = document.getElementById('use_tor')?.checked;
        if (this.elements.torStatus) {
            this.elements.torStatus.style.display = useTor ? 'flex' : 'none';
        }
        if (useTor) {
            this.updateTorStatus();
            this.elements.torStatus.addEventListener('click', this.updateTorStatus.bind(this));
        } else {
            clearInterval(this.state.torStatusInterval);
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                clearInterval(this.state.torStatusInterval);
            } else if (document.getElementById('use_tor')?.checked) {
                this.updateTorStatus();
            }
        });
    },


    // Setting up language switching
    setupLanguageSwitcher() {
        const currentLang = window.APP_CONFIG.locale;
        document.querySelectorAll(`.lang-link[data-lang="${currentLang}"]`).forEach(el => {
            el.classList.add('active');
        });

        document.querySelectorAll('.lang-link').forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                if (link.classList.contains('active')) return;
                const lang = link.getAttribute('data-lang');
                try {
                    await fetch(`/set_language?lang=${lang}`, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
                    document.querySelectorAll('.lang-link').forEach(l => l.classList.remove('active'));
                    link.classList.add('active');
                    window.location.reload();
                } catch (error) {
                    console.error('Language change error:', error);
                }
            });
        });
    },

    // Configuring GeoIP Checkbox Dependencies
    setupGeoCheckboxes() {
        const ids4 = document.getElementById('IDSv4');
        const geoGithub = document.getElementById('geo_github');
        geoGithub.onchange = () => {
            if (!ids4.checked) geoGithub.checked = false;
        };
        ids4.onchange = () => {
            if (!ids4.checked) geoGithub.checked = false;
        };
    },

    // Setting up proxy settings
    setupProxySettings() {
        const {useProxyCheckbox, proxySettingsDiv, proxyHost, proxyPort, form} = this.elements.proxyElements;

        // Function to toggle proxy settings visibility
        const toggleProxySettings = () => {
            const show = useProxyCheckbox.checked;
            proxySettingsDiv.style.display = show ? "block" : "none";

            // Make fields required only if proxy is enabled
            proxyHost.required = show;
            proxyPort.required = show;
        };

        // Apply initial state
        toggleProxySettings();

        // Handle checkbox change
        useProxyCheckbox.addEventListener("change", toggleProxySettings);
    },

    // Setting up update check functionality
    setupUpdateChecker() {
        const {checkUpdatesBtn} = this.elements.updateElements;

        if (checkUpdatesBtn) {
            // Add click event listener to the update check button
            checkUpdatesBtn.addEventListener('click', this.checkForUpdates.bind(this));

            // Display the last saved update check results
            this.displayLastUpdateResults();
        }
    },

    // Display the last saved update check results without performing a new check
    displayLastUpdateResults() {
        const {
            updateStatus,
            currentVersion,
            latestVersion,
            lastCheck,
            updateAvailable,
            updateChanges
        } = this.elements.updateElements;

        // Show loading indicator
        updateStatus.classList.add('loading');

        fetch('/check_update_status')
            .then(response => response.json())
            .then(data => {
                // Update version information
                currentVersion.textContent = data.current_version || '-';
                latestVersion.textContent = data.latest_version || '-';

                // Format date and time
                if (data.timestamp) {
                    const date = new Date(data.timestamp);
                    lastCheck.textContent = date.toLocaleString();
                } else {
                    lastCheck.textContent = '-';
                }

                // Check for available updates
                if (data.has_updates && data.changes && data.changes.length > 0) {
                    updateAvailable.style.display = 'block';

                    // Clear previous content
                    updateChanges.innerHTML = '';

                    // Display changelog
                    const changesList = document.createElement('ul');
                    data.changes.forEach(change => {
                        const item = document.createElement('li');
                        const version = document.createElement('strong');
                        version.textContent = change.version + ': ';

                        item.appendChild(version);

                        // Add description based on locale
                        const locale = window.APP_CONFIG?.locale || 'en';
                        const description = change.description[locale] || change.description.en || '';
                        item.appendChild(document.createTextNode(description));

                        changesList.appendChild(item);
                    });

                    updateChanges.appendChild(changesList);
                } else {
                    updateAvailable.style.display = 'none';
                }
                if (data.has_updates) {
                    this.elements.updateLabel.style.display = 'inline-block';
                } else {
                    this.elements.updateLabel.style.display = 'none';
                }
            })
            .catch(error => {
                console.error('Error fetching update status:', error);
                lastCheck.textContent = 'Error: ' + error.message;
            })
            .finally(() => {
                // Hide loading indicator
                updateStatus.classList.remove('loading');
            });
    },

    // Check for available updates by initiating a new check
    checkForUpdates() {
        const {
            updateStatus,
            currentVersion,
            latestVersion,
            lastCheck,
            updateAvailable,
            updateChanges
        } = this.elements.updateElements;

        // Show loading indicator
        updateStatus.classList.add('loading');

        // Perform a new check for updates
        fetch('/check_for_updates')
            .then(response => response.json())
            .then(data => {
                // Update version information
                currentVersion.textContent = data.current_version || '-';
                latestVersion.textContent = data.latest_version || '-';

                // Format date and time
                if (data.timestamp) {
                    const date = new Date(data.timestamp);
                    lastCheck.textContent = date.toLocaleString();
                } else {
                    lastCheck.textContent = '-';
                }

                // Check for available updates
                if (data.has_updates && data.changes && data.changes.length > 0) {
                    updateAvailable.style.display = 'block';

                    // Clear previous content
                    updateChanges.innerHTML = '';

                    // Display changelog
                    const changesList = document.createElement('ul');
                    data.changes.forEach(change => {
                        const item = document.createElement('li');
                        const version = document.createElement('strong');
                        version.textContent = change.version + ': ';

                        item.appendChild(version);

                        // Add description based on locale
                        const locale = window.APP_CONFIG?.locale || 'en';
                        const description = change.description[locale] || change.description.en || '';
                        item.appendChild(document.createTextNode(description));

                        changesList.appendChild(item);
                    });

                    updateChanges.appendChild(changesList);
                } else {
                    updateAvailable.style.display = 'none';
                }
                if (data.has_updates) {
                    this.elements.updateLabel.style.display = 'inline-block';
                } else {
                    this.elements.updateLabel.style.display = 'none';
                }
            })
            .catch(error => {
                console.error('Error fetching update status:', error);
                lastCheck.textContent = 'Error: ' + error.message;
            })
            .finally(() => {
                // Hide loading indicator
                updateStatus.classList.remove('loading');
            });
    }
};

// Launching the app
document.addEventListener('DOMContentLoaded', () => App.init());