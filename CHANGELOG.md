# Changelog

One line per version, newest first. The version is printed by `python run.py --version`, written into every workflow trace and served by the API.

- 0.3.1: Review fixes: the publish handler also checks sign-off rights; a declined or failed publication stops as not_published (exit 4) and is never retried; piped input never counts as sign-off; control characters are stripped from the sign-off prompt; backend details stay in the log; anonymous API calls are refused before uploads are read, and uploads are capped at 50 MB; the checklist is de-duplicated; a fault in the loop ends as tool_failed.
- 0.3.0: Human approval before a higher-impact action: the executor holds publish_completeness_report until a procurement officer signs off; simulated procurement record; `workflow --publish`; dropped steps are noted even when the run then stops.
- 0.2.0: Week 5 multi-step workflow by direct orchestration (`workflow` command, POST /workflow); create_review_ticket tool implemented to the Third Tool Specification; `--version` flag.
- 0.1.0: Weeks 1 to 4: completeness check with evidence adjudication, retrieval index and search, tools and model-driven tool calling. The version was not bumped per change before this log began.
