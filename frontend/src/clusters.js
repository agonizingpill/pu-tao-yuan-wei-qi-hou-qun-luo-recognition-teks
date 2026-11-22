import {runStates, slots, tagStates} from './domain.js';
import {safe, num, localTime, notice, tag, title, field, table, select, button, paragraph} from './ui.js';

const blindStates = {queued:'等待计算', completed:'已完成', failed:'计算失败'};
const pct = value => value === null || value === undefined ? '—' : `${num(value*100,1)}%`;
const hit = value => value === null || value === undefined ? '—'
  : `<span class="hit ${value ? 'yes' : 'no'}">${value ? '命中' : '未中'}</span>`;

function bicScores(result) {
  const scores = Object.values(result.bic);
  const high = Math.max(...scores);
  const low = Math.min(...scores);
  return `<ul class="bic">${Object.entries(result.bic).map(([k, value]) => `
    <li class="${Number(k) === result.chosen_k ? 'selected' : ''}"><span>${k} 组</span>
    <i style="--size:${25+75*(high-value)/(high-low || 1)}%"></i><b>${num(value,2)}</b></li>`).join('')}</ul>`;
}

function blindPanel(tests, blind, options, canWrite) {
  const result = blind?.result;
  const summary = result?.summary;
  const sourceLine = side => side
    ? `#${side.run_id} · ${side.window_start} → ${side.window_end} · 快照 ${safe(side.digest.slice(0,12))}<br>
       <span class="muted">来源：${side.sources.map(safe).join('、') || '—'} · ${side.blocks} 个地块</span>`
    : '—';
  const schemeRows = result ? Object.entries(result.schemes).sort(([a],[b]) => a-b).map(([k,s]) => `
    <tr class="${Number(k)===result.preferred_k ? 'chosen-row' : ''}"><td>${k} 群${Number(k)===result.preferred_k?' · 训练 BIC 更小':''}</td>
      <td>${num(s.bic,2)}</td><td>${Object.entries(s.centroids).map(([p,c]) =>
        `${tag(p)} ${num(c.day_temp)}/${num(c.night_temp)}° · ${num(c.day_rh,0)}/${num(c.night_rh,0)}%`).join('<br>')}</td></tr>`).join('') : '';
  const blockRows = result?.blocks.map(b => `<tr class="${b.missing ? 'warn-row' : ''}">
    <td>${safe(b.code)}${b.name ? `<small class="muted"> ${safe(b.name)}</small>` : ''}</td>
    <td>${tag(b.published)}</td>
    <td>${tag(b.predicted_2)} <span class="muted">${pct(b.confidence_2)}</span></td>
    <td>${tag(b.predicted_3)} <span class="muted">${pct(b.confidence_3)}</span></td>
    <td>${hit(b.hit_2)}</td><td>${hit(b.hit_3)}</td>
    <td>${safe(b.coverage)}${b.missing ? ' 缺读数' : b.eligible ? '' : ' 无标签'}</td></tr>`);
  return `<section class="bottom blind"><div class="section-label"><h2>两群 / 三群盲测</h2>
      ${blind ? `<span class="tag ${blind.status==='failed'?'warning':'neutral'}">${blindStates[blind.status]}</span>` : '<span>尚未运行</span>'}</div>
    <p class="muted">用较早的已生效采样窗拟合标准尺度与两群、三群两套模型；较晚的不重叠已生效窗口只按冻结模型判群，不参与标准化或拟合。命中率对照后窗当时发布的标签，缺读数或没有标签的地块单列，不计入分母。该盲测独立于正在生效和排灌在用（正在排灌）的标签，只读不改。</p>
    ${canWrite && options.length >= 2 ? `<form data-action="blind" class="inline-form blind-form">
      ${select('train_run_id','训练前窗',options.map(r => [r.id,`#${r.id} · ${r.window_start} → ${r.window_end}`]),options.at(-2)?.id)}
      ${select('test_run_id','盲测后窗',options.map(r => [r.id,`#${r.id} · ${r.window_start} → ${r.window_end}`]),options.at(-1)?.id)}
      ${button('冻结两窗并盲测')}</form>` : notice(canWrite ? '至少需要两个已生效且不重叠的采样窗。' : '当前账号可查阅盲测来源与逐地块对照。')}
    ${tests.length ? `<div class="selector">${select('blind','查看盲测批次',tests.map(t =>
      [t.id,`#${t.id} · 训练 ${t.train_window_end} → 盲测 ${t.test_window_end} · ${blindStates[t.status]}`]), blind?.id)}</div>` : ''}
    ${blind?.error ? notice(blind.error, 'caution') : ''}
    ${blind?.status === 'queued' ? notice('两窗快照已冻结，正在等待后台计算。') : ''}
    ${blind?.status === 'failed' && canWrite ? `<form data-action="blind-retry" data-id="${blind.id}">${button('按原批次快照重试')}</form>` : ''}
    ${blind ? `<h3>窗口来源</h3>
      <table class="provenance"><tbody>
        <tr><th scope="row">训练前窗</th><td>${sourceLine(blind.provenance?.train)}</td></tr>
        <tr><th scope="row">盲测后窗</th><td>${sourceLine(blind.provenance?.test)}</td></tr>
        <tr><th scope="row">训练排除</th><td>${result?.train?.excluded?.length ? result.train.excluded.map(safe).join('、') : (result ? '无' : '—')}</td></tr>
      </tbody></table>` : ''}
    ${result ? `<div class="blind-summary">
        <div><b>${summary.hit_2} / ${summary.eligible}</b><span>两群命中 ${pct(summary.rate_2)}</span></div>
        <div><b>${summary.hit_3} / ${summary.eligible}</b><span>三群命中 ${pct(summary.rate_3)}</span></div>
        <p>${summary.eligible ? (summary.rate_3 > summary.rate_2 ? '三群在后窗盲测更准。' : summary.rate_3 < summary.rate_2 ? '两群在后窗盲测更准。' : '两套判群在后窗盲测打平。') : '没有可计入命中率的地块。'}
        ${summary.improved.length ? ` 三群改对：${summary.improved.map(safe).join('、')}。` : ''}
        ${summary.worsened.length ? ` 三群改错：${summary.worsened.map(safe).join('、')}。` : ''}</p>
      </div>
      <h3>训练窗口 BIC 与群落中心</h3>
      ${table(['方案','训练 BIC','原尺度中心 日/夜温 °C · 日/夜湿 %'], [schemeRows])}
      <h3>逐地块对照（后窗）</h3>
      <p class="muted">「当时发布」指盲测后窗冻结时该批次发布的标签，与当前生效、正在排灌的标签分列；本盲测不读取也不改动排灌依据。</p>
      ${table(['地块','当时发布标签','两群判群','三群判群','两群','三群','覆盖'], blockRows)}
      ${(summary.missing.length || summary.without_label.length) ? `<p class="muted">未计入：缺读数 ${summary.missing.map(safe).join('、') || '无'}；无发布标签 ${summary.without_label.map(safe).join('、') || '无'}。</p>` : ''}
      <p class="muted hash">参数：随机种子 ${result.seed} · 对角协方差 ${result.covariance_type} · reg_covar ${result.reg_covar} · n_init ${result.n_init} · 计算 ${blind.attempts} 次</p>` : ''}
  </section>`;
}

export function clusterPage(runs, run, labels, tests, blind, options, canWrite, supervisor) {
  const result = run?.result;
  const healthRows = run?.coverage.map(c => `<tr class="${c.deficient?'warn-row':''}"><td>${safe(c.code)}</td><td>${safe(c.sensor)}</td><td>${c.received} / ${c.expected}</td>
    <td>${c.missing.map(m => `${safe(m.day.slice(5))} ${slots[m.slot]}`).join('、') || '齐全'}</td></tr>`);
  const review = run?.status === 'review';
  return `${title('微气候群落', '三个连续日期，每地块应有六笔昼夜采样。超过 25% 缺测时停止发布。')}
    <div class="spread ${review ? 'review-spread' : ''}">
      <section>
        <div class="section-label"><h2>识别批次</h2>${run ? `<span class="tag ${review || run.status==='blocked' ? 'warning' : 'neutral'}">${runStates[run.status]}</span>` : ''}</div>
        ${runs.length ? `<div class="selector">${select('run','查看采样窗口',runs.map(r => [r.id,`${r.window_end} · ${runStates[r.status]} · #${r.id}`]), run?.id)}</div>` : notice('从有完整采样的窗口发起第一次识别。')}
        ${run?.error ? notice(run.error, 'caution') : ''}
        ${run?.status === 'queued' ? notice('采样快照已冻结，正在等待后台识别。') : ''}
        ${review ? `<div class="review"><h3>这次标签变更影响已排轮次</h3><p>确认前继续沿用旧标签，受影响的轮次暂缓执行。确认后需按新标签改排。</p>
          ${table(['轮次','地块','排定时间','旧标签','候选标签'],run.affected.map(r => `<tr><td>${safe(r.code)}</td><td>${safe(r.block)}</td><td>${localTime(r.starts_at)}</td><td>${tag(r.basis_profile)}</td><td>${tag(r.proposed_profile)}</td></tr>`))}
          ${supervisor ? `<form data-action="decision" data-id="${run.id}">${paragraph('reason','确认或退回理由','例：核对北坡备用探头，调整下一轮滴灌。')}
          <div class="actions"><button name="approve" value="true" class="primary">确认并标记待改排</button><button name="approve" value="false" class="secondary">退回候选标签</button></div></form>` : notice('请通知灌溉主管确认。')}</div>` : ''}
        ${healthRows?.length ? `<h3>探头覆盖</h3>${table(['地块','探头','有效读数','缺测班次'],healthRows)}` : ''}
        ${run?.status === 'failed' && canWrite ? `<form data-action="retry" data-id="${run.id}">${button('按原快照重试')}</form>` : ''}
        ${run ? `<p class="muted hash" title="${safe(run.digest)}">快照 ${safe(run.digest.slice(0,16))} · 计算 ${run.attempts} 次</p>` : ''}
      </section>
      <section class="ledger">
        ${canWrite ? `<h2>发起识别</h2><form data-action="run" class="inline-form">${field('window_end','窗口截止日','type="date" value="2026-11-20"')}${button('冻结采样并识别')}</form>` : ''}
        ${result ? `<div class="section-label"><h2>BIC 组数比较</h2><span class="mono">选中 ${result.chosen_k} 组</span></div>
          ${bicScores(result)}<p class="muted">BIC 越小越合适。组名按温度与相对湿度的综合排序分配。</p>
          ${table(['群落','日 / 夜温 °C','日 / 夜湿 %'],Object.entries(result.centroids).map(([p,c]) =>
            `<tr><td>${tag(p)}</td><td>${num(c.day_temp)} / ${num(c.night_temp)}</td><td>${num(c.day_rh,0)} / ${num(c.night_rh,0)}</td></tr>`))}
          <button class="text-button evidence" type="button" data-evidence="${run.id}">保存拟合证据 JSON</button>` : ''}
      </section>
    </div>
    ${blindPanel(tests, blind, options, canWrite)}
    <section class="bottom"><h2>地块标签账</h2>${labels.length ? table(['地块','标签','版本','窗口截止','状态','后验概率'], labels.map(l =>
      `<tr><td>${safe(l.code)}</td><td>${tag(l.profile)}</td><td>v${l.revision}</td><td>${safe(l.window_end)}</td><td>${tagStates[l.state]}</td><td>${num(l.confidence*100,1)}%</td></tr>`)) : notice('模型开始发布标签后，这里会保留生效和历史版本。')}</section>`;
}
