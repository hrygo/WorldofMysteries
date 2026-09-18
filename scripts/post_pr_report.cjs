'use strict';

// Called by actions/github-script. Keep GitHub API and filesystem I/O injectable
// so the exact publication code, not a textual imitation, can be regression-tested.
const fs = require('node:fs');
const MARKER = '<!-- wom-evidence-summary:v1 -->';
const LEGACY_TITLE = '## 🛡️ 《诡秘世界》协同证据摘要 (Evidence Summary)';

module.exports = async function postReport({github, context, core, reportBody}) {
  const expected = context.payload.pull_request;
  if (!expected || !/^[0-9a-f]{40}$/.test(expected.head?.sha || '')) {
    throw new Error('A pull-request event with a pinned head is required.');
  }
  const body = reportBody ?? fs.readFileSync('.hacf/tmp/pr_report.md', 'utf8');
  if (!body.startsWith(MARKER + '\n') ||
      !body.includes(`<!-- wom-evidence-head:${expected.head.sha} -->`)) {
    throw new Error('Report identity/head does not match the triggering PR.');
  }
  const params = {...context.repo, pull_number: expected.number};
  async function stillCurrent() {
    const {data: live} = await github.rest.pulls.get(params);
    return live.state === 'open' && live.head.sha === expected.head.sha &&
      live.base.sha === expected.base.sha;
  }
  if (!await stillCurrent()) {
    core.info('Skipping stale report: the PR head/base or open state changed.');
    return {action: 'skipped'};
  }
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...context.repo, issue_number: expected.number, per_page: 100,
  });
  const existing = comments.find(comment =>
    comment.user?.type === 'Bot' && comment.user?.login === 'github-actions[bot]' &&
    typeof comment.body === 'string' &&
    (comment.body.startsWith(MARKER + '\n') || comment.body.startsWith(LEGACY_TITLE + '\n'))
  );
  // Pagination may take time. Re-check immediately before writing; do not allow
  // an old run to overwrite a newer-head report or edit a human's quoted report.
  if (!await stillCurrent()) {
    core.info('Skipping stale report after comment lookup.');
    return {action: 'skipped'};
  }
  if (existing) {
    await github.rest.issues.updateComment({...context.repo, comment_id: existing.id, body});
    return {action: 'updated', commentId: existing.id};
  }
  const {data: created} = await github.rest.issues.createComment({
    ...context.repo, issue_number: expected.number, body,
  });
  return {action: 'created', commentId: created.id};
};
