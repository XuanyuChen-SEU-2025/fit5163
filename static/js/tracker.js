(function () {
    const BlogTracker = {
        csrfToken: null,
        startTime: null,
        postId: null,
        dwellSent: false,

        initPostPage(options) {
            this.csrfToken = options.csrfToken;
            this.postId = options.postId;
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
                    const response = await fetch(url, {
                        method: "POST",
                        headers: {
                            "X-CSRF-Token": this.csrfToken,
                            "X-Share-Channel": action === "share" ? "页面按钮" : "",
                        },
                    });
                    const payload = await response.json();
                    if (payload.ok) {
                        this.refreshMetrics(payload.metrics);
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
                } else if (payload.error) {
                    window.alert(payload.error);
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
                navigator.sendBeacon("/api/track/dwell", formData);
                return;
            }
            fetch("/api/track/dwell", {
                method: "POST",
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
    };

    window.BlogTracker = BlogTracker;
})();
