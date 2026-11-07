// Production bundle, entirely intercepted APIs. No real account, messages or publication.
import assert from 'node:assert/strict';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium, webkit } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { preview } from 'vite';

const output = fileURLToPath(new URL('../../docs/ui-core-redesign/after/', import.meta.url));
await mkdir(output, { recursive: true });
const dictionaries = {};
for (const lang of ['en', 'tr']) {
  dictionaries[lang] = {};
  for (const file of ['common', 'inbox', 'agent', 'agentWork', 'content', 'ai']) Object.assign(dictionaries[lang], JSON.parse(await readFile(new URL(`../src/i18n/locales/${lang}/${file}.json`, import.meta.url), 'utf8')));
}
const ws = '11111111-1111-4111-8111-111111111111', account = 'a1000000-0000-4000-8000-000000000001';
const qid = 'a2000000-0000-4000-8000-000000000001', convo = 'a3000000-0000-4000-8000-000000000001';
const thread = 'a4000000-0000-4000-8000-000000000001', contentId = 'a5000000-0000-4000-8000-000000000001';
const base = `/w/${ws}`, api = `/api/v1/workspaces/${ws}`;
const pageOf = items => ({ items, next_cursor: null });
const server = await preview({ root: fileURLToPath(new URL('../', import.meta.url)), preview: { port: 0, host: '127.0.0.1' } });
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
const results = [];
const browsers = {};
let complete = false;

async function fixture(browser, locale, width, role = 'owner') {
  const context = await browser.newContext({ viewport: { width, height: 900 }, locale, timezoneId: 'Europe/Istanbul', serviceWorkers: 'block' });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [], unexpected = [], requests = [];
  const t = key => key.split('.').reduce((value, part) => value[part], dictionaries[locale]);
  const state = { conflict: false, unavailable: false, reportFailed: false, expired: false, answered: false, draftStatus: 'pending_approval', task: null, delegation: null, ready: false, quiet: false, needsReauth: false, publishFailed: false, moderation: 'visible' };
  const now = new Date().toISOString(), future = new Date(Date.now() + 86400000).toISOString();
  let item = { id: contentId, content_type: 'feed_image', status: 'draft', version: 1, title: 'Summer studio update', caption: 'Welcome to our studio. Merhaba!', overlay_text_suggestions: [], visual_notes: null, social_account_id: account, media_asset_id: 'media-1', media_deleted: false, scheduled_at: null, schedule_local: null, approval_id: null, approval: null, operation: null, hold_reason: null, rejection_note: null, validation: { passed: true, issues: [], stale: false, errors: [], warnings: [] }, generation: null, published_at: null, external_media_id: null, external_permalink: null, last_error_code: null, can_cancel: true, created_at: now, updated_at: now, is_simulated: true };
  const conversation = { id: convo, social_account_id: account, customer_handle: 'Fixture customer', customer_number: 42, attention: 'needs_approval', handling_mode: 'automatic', last_message_preview: 'Could I change my booking?', last_message_at: now, window_ends_at: future, is_simulated: true };
  const question = () => ({ id: qid, thread_id: thread, customer_id: 'customer-1', source_cursor: 1, required_info: 'exception', visibility: 'customer_reply', body: 'Can this booking be changed?', state: state.answered ? 'answered' : 'pending', version: state.answered ? 2 : 1, answer_id: null, expires_at: future });
  const approval = () => ({ id: 'approval-1', kind: 'authorization', action: 'reply.send', status: state.expired ? 'expired' : 'pending', payload_hash: 'a'.repeat(64), can_decide: role !== 'staff' && !state.expired, subject: { id: 'draft-1', type: 'reply_draft', version: 1, status: state.draftStatus, link: { target: 'conversation', id: convo } }, summary: { draft_id: 'draft-1', conversation_id: convo, label: 'Booking reply' }, expires_at: future, execute_before: null, required_permission: 'reply.approve', is_simulated: true, created_at: now, decided_at: null, decided_by_name: null, decision_note: null });
  const draft = () => ({ id: 'draft-1', conversation_id: convo, status: state.draftStatus, source: 'ai', language: locale, intent: 'general', flags: [], text: 'We can help with your booking.', suggestion_text: null, rendered_facts: [], validation: { passed: true, issues: [] }, decision: 'approval_required', decision_reasons: ['POLICY_REQUIRES_APPROVAL'], approval_id: 'approval-1', approval_state: state.expired ? { status: 'expired', expires_at: now, decided_by_name: null, decided_at: null, decision_note: null } : null, version: 1, failure_code: null, window_ends_at: future, created_at: now, is_simulated: true });
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', async route => {
    const url = new URL(route.request().url()), path = url.pathname, method = route.request().method();
    if (url.origin !== origin) { unexpected.push('external request'); return route.abort(); }
    if (!path.startsWith('/api/')) return route.continue();
    const body = method === 'GET' ? null : route.request().postDataJSON();
    requests.push({ path, query: url.search, method, body });
    const send = (json, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(json) });
    const problem = (code = 'VERSION_CONFLICT', status = 409) => send({ code, status, title: code, request_id: 'fixture-request' }, status);
    if (path === '/api/v1/meta') return send({ product_name: 'AgentNest', demo_tools_enabled: true, llm_mode: 'fake', supported_locales: ['tr', 'en'], instagram_providers: ['mock'] });
    if (path === '/api/v1/auth/me') return send({ user: { id: 'user-1', display_name: 'Deniz', email: 'fixture@example.test', ui_locale: locale }, csrf_token: 'fixture', memberships: [{ workspace_id: ws, workspace_name: 'Studio Garden · Test', role, is_demo: true }] });
    if (path === api) return send({ id: ws, name: 'Studio Garden · Test', slug: 'fixture', business_category: 'fitness', market: 'tr', default_locale: locale, reply_languages: ['tr', 'en'], timezone: 'Europe/Istanbul', currency: 'TRY', is_demo: true, status: 'active', settings: {}, created_at: now });
    if (path.endsWith('/deletion-status')) return send({ is_deleting: false });
    if (path.endsWith('/notifications')) return send({ items: [], next_cursor: null, unread_count: 0 });
    if (path.endsWith('/readiness')) return send({ level: state.ready ? 'ready' : 'ready_for_drafts', requirements: [{ code: 'business_name', required_for: 'drafts', satisfied: true, status: 'ok', link: { target: 'knowledge', category: 'identity', key: 'identity.business_name' }, missing_keys: [] }, { code: 'booking_instructions', required_for: 'ready', satisfied: false, status: 'missing', link: { target: 'knowledge', category: 'booking', key: 'booking.instructions' }, missing_keys: [] }] });
    if (path.endsWith('/social-accounts')) return send(pageOf([{ id: account, username: 'studio_fixture', status: state.needsReauth ? 'needs_reauth' : 'connected', provider_kind: 'mock', platform: 'instagram', capabilities: { messaging: true, feed_publish: true, comment_moderate: true }, is_simulated: true }]));
    if (path.includes('/reports/daily')) {
      if (state.reportFailed) return problem('INTERNAL_ERROR', 503);
      return send({ local_date: now.slice(0,10), timezone: 'Europe/Istanbul', period_start: now, period_end: now, generated_at: now, is_partial: true, has_simulated_data: true, definitions_version: '1', metrics: ['inbound_messages', 'replies_sent', 'content_published', 'attention_now', ...(role === 'staff' ? [] : ['pending_approvals_now', 'content_on_hold_now'])].map(key => ({ key, value: state.quiet ? 0 : 1, link: { route: key === 'attention_now' ? `${base}/inbox` : `${base}/approvals` } })), summary: { empty: false, text: '', sections: [] } });
    }
    if (path.endsWith('/conversations')) return send(pageOf(Array.from({ length: 8 }, (_, i) => ({ ...conversation, id: i ? `${convo.slice(0,-1)}${i + 1}` : convo, customer_handle: i ? `Fixture customer ${i + 1}` : conversation.customer_handle }))));
    if (path === `${api}/conversations/${convo}`) return send({ conversation, messages: [{ id: 'message-1', direction: 'inbound', sender_kind: 'customer', text: 'Could I change my booking?', attachments: [], provider_timestamp: now, is_simulated: true }], open_draft: draft(), recent_drafts: [] });
    if (path.endsWith('/reply-drafts/draft-1/edit')) { state.draftStatus = 'queued'; return send(draft()); }
    if (path.endsWith('/reply-drafts/draft-1')) { if (method === 'PATCH') { state.draftStatus = 'queued'; return send({ draft: draft(), warnings: [] }); } return send(draft()); }
    if (path.endsWith('/replies')) return send({ draft: { ...draft(), status: 'queued' }, warnings: [] });
    if (path.endsWith('/agent/threads')) return send(pageOf([{ id: thread, account_id: account, surface: path.includes('/comments') || url.searchParams.get('source_ref') === 'public-thread' ? 'comment' : 'dm', source_ref: url.searchParams.get('source_ref'), state: 'active', handling_mode: 'agent', version: 1, customer_id: 'customer-1', goal: 'waiting_owner', is_simulated: true, actions: [] }]));
    if (path.endsWith('/owner-questions')) return send(pageOf([question()]));
    if (path.endsWith(`/owner-questions/${qid}`)) return send(question());
    if (path.endsWith(`/owner-questions/${qid}/answers`)) return send(pageOf(state.answered ? [{ id: 'answer-1', question_id: qid, version: 1, kind: 'answer', body: 'Yes, the booking may be changed.', author_role: 'owner', candidate_id: 'candidate-1', expires_at: future }] : []));
    if (path.endsWith(`/owner-questions/${qid}/answer`)) { if (state.conflict) return problem(); state.answered = true; return send({ id: 'answer-1', question_id: qid, version: 2, kind: body.kind, body: body.body, author_role: role, candidate_id: body.reusable_knowledge ? 'candidate-1' : null, expires_at: future }); }
    if (path.endsWith('/comments') || path.endsWith('/comments/threads/public-thread')) return send(pageOf([{ id: 'comment-1', text: 'What classes are available?', state: state.moderation, thread_id: 'public-thread', media_id: 'public-media', version: 1, is_owner: false, is_simulated: true }]));
    if (path.endsWith('/comments/media/public-media')) return send({ id: 'public-media', caption: 'Our studio classes this month.', state: 'visible', ownership_state: 'verified_synthetic', version: 1, is_simulated: true });
    if (path.endsWith('/comments/comment-1/moderation-operations')) return send(pageOf([]));
    if (path.endsWith('/comments/comment-1/moderate')) { state.moderation = body.effect === 'hide' ? 'hidden' : 'visible'; return send({ operation_id: 'moderation-1', status: 'succeeded', effect: body.effect, is_simulated: true, error_code: null, created_at: now }); }
    if (path.endsWith('/agent')) return send({ state: 'active', controller_mode: 'agent', config_version: 3, controller_epoch: 1, is_simulated: true, session_counts: { waiting_owner: 1 }, pending_questions: state.answered ? 0 : 1, pending_approvals: state.quiet ? 0 : 1, recent_actions: ['queued', 'outcome_unknown', 'failed', 'succeeded'].map((status, i) => ({ id: `act-${i}`, action_type: 'dm.send', status, operation_id: null, created_at: now })) });
    if (path.endsWith('/agent/personality')) return send({ version: 1, goals: 'Help our customers', personality: { tone: 'warm', formality: 'professional', length: 'short', emoji: 'none', dm_style: 'conversational', comment_style: 'concise', examples: { tr: [], en: [] } } });
    if (path.endsWith('/agent/delegation')) return send(state.delegation);
    if (path.endsWith('/agent/delegation/preview')) return send({ next_version: 1, changed_actions: ['dm.send'] });
    if (path.endsWith('/agent/delegation/apply')) { state.delegation = { version: 1, config_version: 4, policy: body.policy }; return send(state.delegation); }
    if (path.endsWith('/agent/tasks') && method === 'POST') { state.task = { id: 'task-1', account_id: account, status: 'queued', question_version: 0, clarification: null, actions: [] }; return send(state.task); }
    if (path.endsWith('/agent/tasks')) return send(pageOf(state.task ? [state.task] : []));
    if (path.endsWith('/agent/tasks/task-1')) return send(state.task);
    if (path.endsWith('/approvals/approval-1/decision')) { state.draftStatus = body.decision === 'approve' ? 'queued' : 'rejected'; return send({ ...approval(), status: body.decision === 'approve' ? 'approved' : 'rejected' }); }
    if (path.endsWith('/approvals/approval-1')) return send(approval());
    if (path.endsWith('/approvals')) return send(pageOf([approval()]));
    if (path === `${api}/content-items/${contentId}`) { if (method === 'PATCH') { if (state.conflict) { item.version++; return problem(); } item = { ...item, ...body, version: item.version + 1 }; } return send(item); }
    if (path.endsWith(`/content-items/${contentId}/validate`)) return send({ passed: true, issues: [], stale: false, errors: [], warnings: [] });
    if (path.endsWith(`/content-items/${contentId}/submit`)) { item = { ...item, status: role === 'staff' ? 'pending_approval' : 'scheduled', scheduled_at: body.scheduled_at, version: item.version + 1 }; return send(item); }
    if (path.endsWith('/content-items')) return send(pageOf(url.searchParams.get('status') === 'failed' ? state.publishFailed ? [{ ...item, id: 'failed-item', status: 'failed', title: 'Failed studio post', last_error_code: 'MEDIA_REJECTED' }] : [] : url.searchParams.get('tab') === 'scheduled' ? state.quiet ? [] : [{ ...item, status: 'scheduled', scheduled_at: future }] : [item]));
    if (path.endsWith('/media/media-1/content')) { if (state.unavailable) return problem('NOT_FOUND', 404); return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><rect width="600" height="600" fill="#d6e7cc"/><circle cx="300" cy="280" r="130" fill="#31664c"/><text x="300" y="480" text-anchor="middle" font-size="38" fill="#253b31">STUDIO GARDEN</text></svg>' }); }
    if (path.endsWith('/facts') || path.endsWith('/customers/customer-1/memory')) return send(pageOf([]));
    unexpected.push(`${method} ${path}`); return problem('NOT_FOUND', 404);
  });
  return { context, page, t, state, requests, errors, unexpected, getItem: () => item };
}

async function audit(f, label, capture = true) {
  const { page } = f;
  await page.locator('h1').waitFor();
  await page.evaluate(() => document.fonts.ready);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  assert.equal(overflow, false, `${label}: horizontal overflow`);
  const clippedControls = await page.locator('main a, main button, main input, main select, main textarea').evaluateAll(elements => elements.filter(el => {
    const rect = el.getBoundingClientRect();
    const closed = el.closest("details:not([open])");
    const visible = (!closed || !!el.closest("summary")) && getComputedStyle(el).visibility !== "hidden";
    return visible && rect.width > 0 && rect.height > 0 && (rect.left < -1 || rect.right > innerWidth + 1);
  }).map(el => `${el.tagName}: ${el.textContent.slice(0, 70)}`));
  assert.deepEqual(clippedControls, [], `${label}: controls clipped horizontally`);
  const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
  if (scan.violations.length) await writeFile(`${output}/${label}-axe.json`, JSON.stringify(scan.violations, null, 2));
  assert.deepEqual(scan.violations.map(v => v.id), [], `${label}: accessibility`);
  assert.deepEqual(f.errors, [], `${label}: browser errors`);
  if (capture) {
    const viewportCapture = /short-keyboard|zoom-reflow/.test(label) || page.viewportSize().width < 768 || await page.getByRole('dialog').count() > 0;
    if (!viewportCapture) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    }
    await page.screenshot({ path: `${output}/${label}.png`, fullPage: !viewportCapture });
  }
  const result = { label, overflow, violations: scan.violations.length };
  const existing = results.findIndex(item => item.label === label);
  if (existing < 0) results.push(result); else results[existing] = result;
}

try {
  for (const [engineName, engine] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await engine.launch();
    browsers[engineName] = browser.version();
    try {
      const runMatrix = async (locale, width) => {
        const f = await fixture(browser, locale, width);
        const { page, t } = f, label = `${engineName}-${locale}-${width}`;
        try {
          await page.goto(`${origin}${base}`);
          await page.locator('[data-testid=home-attention]').waitFor();
          const attentionY = await page.locator('[data-testid=home-attention]').evaluate(el => el.getBoundingClientRect().top);
          const commandY = await page.locator('#command-input').evaluate(el => el.getBoundingClientRect().top);
          assert(attentionY < commandY, 'attention precedes request entry');
          assert.equal(await page.locator('#command-input').evaluate(el => getComputedStyle(el.closest('form')).position), 'static');
          await audit(f, `${label}-today`);
          await page.goto(`${origin}${base}/inbox/${convo}?attention=needs_approval`);
          await page.locator('[data-testid=draft-card]').waitFor();
          assert.equal(await page.locator('[data-testid=inbox-list]').isVisible(), width >= 1200);
          if (width >= 1200) assert.equal(Math.round((await page.locator('[data-testid=inbox-list]').boundingBox()).width), 320);
          await audit(f, `${label}-inbox`);
          await page.goto(`${origin}${base}/more/agent/questions/${qid}?account=${account}`);
          await page.getByLabel(t('agentWork.answer'), { exact: true }).waitFor();
          assert.equal(await page.getByLabel(t('agentWork.knowledgeKey')).count(), 0);
          await audit(f, `${label}-question`);
          const start = f.requests.length;
          await page.goto(`${origin}${base}/more/agent/comments/public-thread?account=${account}`);
          await page.getByText('Our studio classes this month.').waitFor();
          assert.equal(f.requests.slice(start).some(r => /\/conversations|\/owner-questions|\/customers\//.test(r.path)), false, 'public view makes no private requests');
          await audit(f, `${label}-comments`);
          await page.goto(`${origin}${base}/more/agent?account=${account}`);
          await page.getByRole('heading', { name: t('agent.tasks'), exact: true }).waitFor();
          assert.equal(await page.getByLabel(t('agent.goals'), { exact: true }).count(), 0);
          await audit(f, `${label}-assistant`);
          for (const panel of ['voice', 'permissions', 'history']) {
            await page.goto(`${origin}${base}/more/agent?account=${account}&panel=${panel}`);
            await page.getByRole('heading', { name: t(panel === 'voice' ? 'agent.personality' : panel === 'permissions' ? 'agent.delegation' : 'agent.recentActions'), exact: true }).waitFor();
            await audit(f, `${label}-assistant-${panel}`);
          }
          await page.goto(`${origin}${base}/approvals`);
          await page.locator('[data-approval-id]').waitFor();
          await audit(f, `${label}-approvals`);
          await page.goto(`${origin}${base}/content`);
          await page.locator('[data-testid=content-card]').waitFor();
          await audit(f, `${label}-content-library`);
          await page.goto(`${origin}${base}/content/${contentId}`);
          await page.locator('[data-testid=post-preview]').waitFor({ state: 'attached' });
          await page.getByLabel(t('content.editor.captionLabel'), { exact: true }).fill('Local caption · Yerel açıklama');
          await audit(f, `${label}-content-edit`);
          if (width < 1200) await page.getByRole('button', { name: t('core.preview'), exact: true }).click();
          assert.equal(await page.locator('[data-testid=post-preview]').getByText('Local caption · Yerel açıklama', { exact: true }).isVisible(), true);
          await audit(f, `${label}-content-preview`);
          assert.deepEqual(f.unexpected, [], `${label}: unexpected API or external request`);
          console.log(`${label}: core matrix passed`);
        } finally { await f.context.close(); }
      };
      const scenarios = process.env.UI_CORE_MODE === 'journeys' ? [] : ['en', 'tr'].flatMap(locale => [360, 390, 768, 1024, 1440, 1920].map(width => ({ locale, width })));
      for (let index = 0; index < scenarios.length; index += 2) {
        const batch = await Promise.allSettled(scenarios.slice(index, index + 2).map(scenario => runMatrix(scenario.locale, scenario.width)));
        const failure = batch.find(result => result.status === 'rejected');
        if (failure) throw failure.reason;
      }
      // Stateful owner journeys in both languages, plus focused small-screen and permission checks.
      for (const locale of ['en', 'tr']) {
        const f = await fixture(browser, locale, 1440);
        const { page, t, state, requests } = f;
        try {
          await page.goto(`${origin}${base}/inbox?attention=needs_approval`);
          await page.locator(`[data-conversation-id="${convo}"]`).click();
          await page.getByRole('button', { name: t('convo.draft.edit'), exact: true }).click();
          await page.getByLabel(t('convo.draft.editLabel')).fill('Edited booking answer');
          await page.getByRole('button', { name: t('convo.draft.saveAndSend'), exact: true }).click();
          await page.waitForFunction(() => !document.querySelector('textarea[id^="edit-"]'));
          assert(requests.some(r => r.path.endsWith('/reply-drafts/draft-1') && r.method === 'PATCH' && r.body.text === 'Edited booking answer'));
          await page.goBack();
          assert.equal(new URL(page.url()).searchParams.get('attention'), 'needs_approval');
          state.draftStatus = 'pending_approval';
          await page.goto(`${origin}${base}/inbox/${convo}`);
          await page.getByRole('button', { name: t('convo.draft.approve'), exact: true }).click();
          await page.getByRole('button', { name: t('convo.draft.cancel'), exact: true }).waitFor();
          assert(requests.some(r => r.path.endsWith('/decision') && r.body.decision === 'approve'));
          assert(requests.some(r => r.path.endsWith('/owner-questions') && new URLSearchParams(r.query).get('thread_id') === thread));
          await page.goto(`${origin}${base}/more/agent/questions/${qid}?account=${account}`);
          await page.getByLabel(t('agentWork.answer'), { exact: true }).fill('Yes, the booking may be changed.');
          await page.getByLabel(t('agentWork.reuse'), { exact: true }).check();
          await page.getByRole('button', { name: t('agentWork.sendAnswer'), exact: true }).click();
          await page.getByText(t('agentWork.answerRecorded')).waitFor();
          assert.equal(requests.find(r => r.path.endsWith(`/${qid}/answer`)).body.reusable_knowledge.key, `custom.owner_answer_${qid.replaceAll('-', '')}`);
          await page.goto(`${origin}${base}/more/agent?account=${account}`);
          await page.getByLabel(t('agent.taskText'), { exact: true }).fill('Prepare a studio post draft');
          await page.getByRole('button', { name: t('agent.submitTask'), exact: true }).click();
          await page.getByRole('link', { name: t('agent.taskProgress'), exact: true }).click();
          await page.getByRole('heading', { name: t('agentWork.task'), exact: true }).waitFor();
          await page.goto(`${origin}${base}/more/agent?account=${account}&panel=permissions`);
          const dm = page.locator('fieldset').filter({ has: page.locator('legend', { hasText: t('agent.actions.dm_send') }) });
          await dm.getByRole('combobox').selectOption('ask');
          await page.getByRole('button', { name: t('agent.previewDelegation'), exact: true }).click();
          assert.equal(requests.filter(r => r.path.endsWith('/delegation/apply')).length, 0);
          await Promise.all([page.waitForResponse(response => response.url().endsWith('/delegation/apply')), page.getByRole('button', { name: t('agent.applyDelegation'), exact: true }).click()]);
          assert.deepEqual(requests.find(r => r.path.endsWith('/delegation/preview')).body, requests.find(r => r.path.endsWith('/delegation/apply')).body);
          await page.goto(`${origin}${base}/content/${contentId}`);
          await page.getByLabel(t('content.editor.captionLabel'), { exact: true }).fill('Updated caption');
          assert.equal(await page.getByRole('button', { name: t('content.actions.schedule'), exact: true }).isDisabled(), true);
          await page.getByRole('button', { name: t('content.editor.save'), exact: true }).click();
          await page.getByText(t('content.editor.saved'), { exact: true }).waitFor();
          await page.getByRole('button', { name: t('content.editor.check'), exact: true }).click();
          await page.locator('[data-testid=check-clean]').waitFor();
          await page.getByRole('button', { name: t('content.actions.schedule'), exact: true }).click();
          await audit(f, `${engineName}-${locale}-schedule-review`);
          // This button affects only the intercepted fixture ledger.
          const dialog = page.getByRole('dialog');
          await dialog.getByRole('button', { name: t('content.schedule.submitApprove'), exact: true }).click();
          await page.waitForFunction(() => !document.querySelector('[role=dialog]'));
          assert.equal(f.getItem().status, 'scheduled');
          await page.goto(`${origin}${base}/approvals`);
          await page.locator('[data-approval-id]').click();
          await audit(f, `${engineName}-${locale}-approval`);
          await page.goto(`${origin}${base}/more/agent/comments/public-thread?account=${account}`);
          await page.getByRole('button', { name: t('agentWork.manual.hide'), exact: true }).click();
          assert.equal(requests.filter(r => r.path.endsWith('/moderate')).length, 0);
          await page.getByRole('button', { name: t('agentWork.confirmEffect'), exact: true }).click();
          await page.getByRole('button', { name: t('agentWork.manual.unhide'), exact: true }).waitFor();
          assert.equal(requests.find(r => r.path.endsWith('/moderate')).body.effect, 'hide');
          await audit(f, `${engineName}-${locale}-moderated-comment`);
          // Simulate the reduced layout viewport available while a phone keyboard is open.
          state.draftStatus = 'pending_approval';
          await page.setViewportSize({ width: 390, height: 420 });
          await page.goto(`${origin}${base}/inbox/${convo}?attention=needs_approval`);
          await page.getByRole('button', { name: t('core.manualReply'), exact: true }).click();
          const composer = page.getByLabel(t('convo.composer.label'), { exact: true });
          await composer.fill('Unsent private reply');
          page.once('dialog', dialog => dialog.dismiss());
          await page.getByRole('link', { name: t('core.comments'), exact: true }).click();
          assert.equal(new URL(page.url()).pathname, `${base}/inbox/${convo}`);
          assert.equal(await composer.inputValue(), 'Unsent private reply');
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          await composer.focus();
          await page.keyboard.press('Tab');
          assert.equal(await page.getByRole('button', { name: t('convo.composer.send'), exact: true }).evaluate(el => el === document.activeElement), true);
          const buttonBounds = await page.getByRole('button', { name: t('convo.composer.send'), exact: true }).boundingBox();
          assert(buttonBounds.y >= 70 && buttonBounds.y + buttonBounds.height <= 356, 'Focused send control clears sticky header and phone tabs');
          await audit(f, `${engineName}-${locale}-short-keyboard-focus`);
          page.once('dialog', dialog => dialog.accept());
          await page.getByRole('link', { name: t('core.comments'), exact: true }).click();
          await page.getByText(t('agentWork.publicNotice')).waitFor();
          await page.getByRole('link', { name: 'What classes are available?', exact: true }).waitFor();
          await page.waitForLoadState('networkidle');
          state.expired = true; state.draftStatus = 'expired';
          await page.goto(`${origin}${base}/inbox/${convo}`);
          await page.locator('[data-testid=draft-card]').waitFor();
          assert.equal(await page.getByRole('button', { name: t('convo.draft.approve'), exact: true }).count(), 0);
          await audit(f, `${engineName}-${locale}-expired-draft`);
          // 1440x900 at 200% browser zoom has a 720x450 CSS layout viewport.
          await page.setViewportSize({ width: 720, height: 450 });
          await page.goto(`${origin}${base}/more/agent?panel=permissions`);
          await page.getByRole('heading', { name: t('agent.delegation'), exact: true }).waitFor();
          await audit(f, `${engineName}-${locale}-zoom-reflow-proxy`);
          await page.setViewportSize({ width: 1440, height: 900 });
          state.unavailable = true;
          await page.goto(`${origin}${base}/content/${contentId}`);
          await page.locator('[data-testid=post-preview]').getByText(t('content.media.previewFailed')).waitFor();
          await audit(f, `${engineName}-${locale}-unavailable-media`);
          state.reportFailed = true;
          await page.goto(`${origin}${base}`);
          await page.getByRole('alert').waitFor();
          assert.equal(await page.locator('[data-testid=attention-none]').count(), 0);
          await audit(f, `${engineName}-${locale}-partial-failure`);
          state.reportFailed = false; state.ready = true; state.quiet = true; state.answered = true;
          await page.goto(`${origin}${base}`);
          await page.locator('[data-testid=attention-none]').waitFor();
          assert.equal(await page.locator('[data-testid=readiness-level]').count(), 0);
          await audit(f, `${engineName}-${locale}-quiet-ready`);
          state.quiet = false; state.needsReauth = true; state.publishFailed = true;
          await page.goto(`${origin}${base}`);
          await page.locator('[data-testid=banner-needs-reauth]').waitFor();
          await page.getByRole('link', { name: t('core.fixPost'), exact: true }).waitFor();
          await audit(f, `${engineName}-${locale}-account-publishing-failures`);
          assert.deepEqual(f.errors, []); assert.deepEqual(f.unexpected, []);
          console.log(`${engineName}-${locale}: owner journeys passed`);
        } catch (error) { console.error(await page.locator('main').innerText()); await page.screenshot({path: `${output}/${engineName}-${locale}-failure.png`, fullPage: true}); throw error; } finally { await f.context.close(); }
      }
      for (const role of ['manager', 'staff']) {
        const f = await fixture(browser, 'en', 390, role);
        const { page, t } = f;
        try {
          await page.goto(`${origin}${base}/more/agent?panel=permissions`);
          await page.getByRole('heading', { name: t('agent.delegation'), exact: true }).waitFor();
          assert.equal(await page.getByRole('button', { name: t('agent.previewDelegation'), exact: true }).count(), 0);
          await audit(f, `${engineName}-${role}-permissions`);
          await page.goto(`${origin}${base}/more/agent/questions/${qid}?account=${account}`);
          await page.getByLabel(t(role === 'staff' ? 'agentWork.proposal' : 'agentWork.answer'), { exact: true }).waitFor();
          assert.equal(await page.getByLabel(t('agentWork.reuse'), { exact: true }).count(), role === 'staff' ? 0 : 1);
          await audit(f, `${engineName}-${role}-question`);
        } finally { await f.context.close(); }
      }
    } finally { await browser.close(); }
  }
  assert.equal(new Set(results.map(result => result.label)).size, results.length, 'Unique evidence labels');
  complete = true;
} finally {
  await writeFile(`${output}/results.json`, JSON.stringify({ complete, capturedAt: new Date().toISOString(), evidence: 'intercepted fixtures, not live Instagram', node: process.version, browsers, results }, null, 2));
  await new Promise(resolve => server.httpServer.close(resolve));
}
console.log(`Core UI: ${results.length} captures/checks passed`);
