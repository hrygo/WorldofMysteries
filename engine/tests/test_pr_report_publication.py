"""Execute the actual github-script publisher with deterministic API doubles.

Node is the runtime of the existing reporting workflow and is available on the
repository's GitHub-hosted CI runners. No GitHub writes occur in this test.
"""
import subprocess
from pathlib import Path


def test_actual_sticky_publisher_boundaries():
    script = Path(__file__).resolve().parents[2] / "scripts/post_pr_report.cjs"
    probe = r"""
    const assert = require('node:assert/strict');
    const post = require(process.argv[1]);
    const head = 'a'.repeat(40), base = 'b'.repeat(40);
    const marker = '<!-- wom-evidence-summary:v1 -->';
    const legacy = '## 🛡️ 《诡秘世界》协同证据摘要 (Evidence Summary)';
    const body = `${marker}\n<!-- wom-evidence-head:${head} -->\n${legacy}\n`;
    const bot = {type:'Bot', login:'github-actions[bot]'};
    async function run(comments, states = [], reportBody = body) {
      const writes = []; let reads = 0, paginated = false;
      const listComments = () => {throw Error('must paginate, not read first page');};
      const context = {repo:{owner:'owner',repo:'repo'},
        payload:{pull_request:{number:50,head:{sha:head},base:{sha:base}}}};
      const github = {
        rest:{pulls:{get: async () => ({data:states[reads++] ||
          {state:'open',head:{sha:head},base:{sha:base}}})},
          issues:{listComments,
            updateComment:async p => {writes.push(['update',p]);},
            createComment:async p => {writes.push(['create',p]);return {data:{id:999}};}}},
        paginate:async (method,params) => {
          assert.equal(method,listComments); assert.equal(params.per_page,100);
          assert.equal(params.issue_number,50); paginated=true; return comments;
        },
      };
      const result = await post({github,context,core:{info:()=>{}},reportBody});
      return {result,writes,reads,paginated};
    }
    (async () => {
      // A human quotation and another bot must not hijack the sticky target.
      const comments = [
        {id:1,user:{type:'User',login:'hrygo'},body:legacy+'\nquote'},
        {id:2,user:{type:'Bot',login:'other[bot]'},body:body},
        ...Array.from({length:130},(_,i)=>({id:10+i,user:bot,body:'unrelated'})),
        {id:5726772899,user:bot,body:legacy+'\nold report'},
      ];
      let r = await run(comments);
      assert.equal(r.result.action,'updated'); assert.equal(r.writes.length,1);
      assert.equal(r.writes[0][1].comment_id,5726772899);
      assert.equal(r.writes[0][1].body,body); assert(r.paginated);
      r = await run([{id:50,user:bot,body}]); assert.equal(r.result.commentId,50);
      r = await run(comments.slice(0,2)); assert.equal(r.result.action,'created');
      r = await run([{id:60,user:bot,body:'quote\n'+legacy+'\nnot the report'}]);
      assert.equal(r.result.action,'created');
      r = await run([], [{state:'open',head:{sha:'c'.repeat(40)},base:{sha:base}}]);
      assert.equal(r.result.action,'skipped'); assert.equal(r.writes.length,0);
      assert.equal(r.paginated,false);
      r = await run([], [{state:'closed',head:{sha:head},base:{sha:base}}]);
      assert.equal(r.result.action,'skipped');
      r = await run([], [{state:'open',head:{sha:head},base:{sha:'d'.repeat(40)}}]);
      assert.equal(r.result.action,'skipped');
      r = await run([], [
        {state:'open',head:{sha:head},base:{sha:base}},
        {state:'open',head:{sha:'c'.repeat(40)},base:{sha:base}},
      ]);
      assert.equal(r.result.action,'skipped'); assert.equal(r.writes.length,0);
      await assert.rejects(run([],[],legacy+'\n'), /identity\/head/);
      await assert.rejects(run([],[],body.replace(head,'e'.repeat(40))), /identity\/head/);
      console.log('PUBLICATION_REGRESSIONS_OK: legacy/new marker, 100+ comments, '
        + 'ownership, stale head/base, closed PR, write-time race, mismatched report');
    })().catch(e => {console.error(e);process.exitCode=1;});
    """
    result = subprocess.run(["node", "-e", probe, str(script)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PUBLICATION_REGRESSIONS_OK" in result.stdout


def test_workflow_calls_tested_publisher_and_binds_snapshot():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/pr-gate-reporter.yml").read_text()
    assert "require('./scripts/post_pr_report.cjs')" in workflow
    assert "WOM_REPORT_HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in workflow
    assert "WOM_REPORT_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert "pull_request_target" not in workflow
    assert "contents: read" in workflow
