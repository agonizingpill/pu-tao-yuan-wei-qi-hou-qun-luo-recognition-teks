import {runStates, slots, tagStates} from './domain.js';
import {safe, num, localTime, notice, tag, title, field, table, select, button, paragraph} from './ui.js';

function bicScores(result) {
  const scores = Object.values(result.bic);
  const high = Math.max(...scores);
  const low = Math.min(...scores);
  return `<ul class="bic">${Object.entries(result.bic).map(([k, value]) => `
    <li class="${Number(k) === result.chosen_k ? 'selected' : ''}"><span>${k} 组</span>
    <i style="--size:${25+75*(high-value)/(high-low || 1)}%"></i><b>${num(value,2)}</b></li>`).join('')}</ul>`;
}

export function clusterPage(runs, run, labels, canWrite, supervisor) {
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
    <section class="bottom"><h2>地块标签账</h2>${labels.length ? table(['地块','标签','版本','窗口截止','状态','后验概率'], labels.map(l =>
      `<tr><td>${safe(l.code)}</td><td>${tag(l.profile)}</td><td>v${l.revision}</td><td>${safe(l.window_end)}</td><td>${tagStates[l.state]}</td><td>${num(l.confidence*100,1)}%</td></tr>`)) : notice('模型开始发布标签后，这里会保留生效和历史版本。')}</section>`;
}
