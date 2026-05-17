(function () {
    const BlogTracker = {
        csrfToken: null,
        startTime: null,
        postId: null,
        dwellSent: false,
        initialized: false,

        initPostPage(options = {}) {
            const root = document.querySelector("[data-post-root]");
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');

            this.csrfToken = options.csrfToken || (csrfMeta ? csrfMeta.content : "");
            this.postId = Number(options.postId || (root ? root.dataset.postId : 0));
            if (!this.csrfToken || !this.postId || this.initialized) {
                return;
            }

            this.initialized = true;
            this.startTime = Date.now();
            this.bindActionButtons();
            this.bindCommentForm();
            window.addEventListener("pagehide", () => this.sendDwell());
            document.addEventListener("visibilitychange", () => {
                if (document.visibilityState === "hidden") {
                    this.sendDwell();
                }
            });
        },

        bindActionButtons() {
            document.querySelectorAll("[data-action]").forEach((button) => {
                button.addEventListener("click", async () => {
                    const action = button.dataset.action;
                    const url = `/api/posts/${button.dataset.postId}/${action}`;
                    const headers = { "X-CSRF-Token": this.csrfToken };

                    if (action === "share") {
                        headers["X-Share-Channel"] = "page-button";
                    }

                    try {
                        const response = await fetch(url, { method: "POST", headers });
                        const payload = await response.json();
                        if (!response.ok || !payload.ok) {
                            window.alert(payload.error || "Action failed. Please try again.");
                            return;
                        }
                        this.refreshMetrics(payload.metrics);
                    } catch (_error) {
                        window.alert("Action failed. Please try again.");
                    }
                });
            });
        },

        bindCommentForm() {
            const form = document.querySelector("[data-comment-form]");
            if (!form) {
                return;
            }

            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                const formData = new FormData(form);
                formData.set("csrf_token", this.csrfToken);

                try {
                    const response = await fetch(`/api/posts/${form.dataset.postId}/comment`, {
                        method: "POST",
                        headers: {
                            "X-CSRF-Token": this.csrfToken,
                        },
                        body: formData,
                    });
                    const payload = await response.json();
                    if (payload.ok) {
                        this.refreshMetrics(payload.metrics);
                        window.location.reload();
                    } else {
                        window.alert(payload.error || "Comment failed. Please try again.");
                    }
                } catch (_error) {
                    window.alert("Comment failed. Please try again.");
                }
            });
        },

        sendDwell() {
            if (this.dwellSent || !this.postId || !this.startTime) {
                return;
            }

            this.dwellSent = true;
            const seconds = Math.max(1, Math.round((Date.now() - this.startTime) / 1000));
            const formData = new FormData();
            formData.append("post_id", this.postId);
            formData.append("seconds", seconds);
            formData.append("csrf_token", this.csrfToken);

            if (navigator.sendBeacon) {
                const accepted = navigator.sendBeacon("/api/track/dwell", formData);
                if (accepted) {
                    return;
                }
            }

            fetch("/api/track/dwell", {
                method: "POST",
                headers: {
                    "X-CSRF-Token": this.csrfToken,
                },
                body: formData,
                keepalive: true,
            });
        },

        refreshMetrics(metrics) {
            Object.entries(metrics).forEach(([key, value]) => {
                const node = document.querySelector(`[data-metric="${key}"]`);
                if (!node) {
                    return;
                }
                node.textContent = key === "avg_dwell" ? `${value}s` : value;
            });
        },

        autoInit() {
            const root = document.querySelector("[data-post-root]");
            if (!root) {
                return;
            }
            this.initPostPage({
                postId: root.dataset.postId,
            });
        },
    };

    window.BlogTracker = BlogTracker;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => BlogTracker.autoInit());
    } else {
        BlogTracker.autoInit();
    }
})();
