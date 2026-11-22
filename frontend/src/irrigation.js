import {roundStates} from './domain.js';
import {safe, localTime, notice, tag, title, field, table, select, button, paragraph, num} from './ui.js';

export function irrigationPage(blocks, rounds, selected, canWrite, supervisor) {
  const viable = blocks.filter(b => b.profile);
  const shown = selected || rounds[0];
  const rows = rounds.map(r => `<tr class="${r.review_hold || r.state==='needs_replan' ? 'warn-row' : ''}">
    <td>${localTime(r.starts_at)}</td><td><button class="text-button" data-round="${r.id}">${safe(r.code)}</button></td>
    <td>${safe(r.block_code)} ${safe(r.block_name)}</td><td>${r.minutes} 分钟</td><td>${r.review_hold ? '待标签确认' : roundStates[r.state]}</td></tr>`);
  return `${title('灌溉轮次', '按地块生效标签编排滴灌时段。所有时间均为中国标准时间。')}
    <div class="spread"><section><div class="section-label"><h2>滴灌排程</h2><span>按开始时间</span></div>
    ${rows.length ? table(['开始','轮次','地块','时长','状态'],rows) : notice('还没有排灌轮次。从右侧选择带生效标签的地块编排。')}
    ${shown ? `<article class="round-sheet"><span class="ref">${safe(shown.code)} · ${safe(shown.block_code)}</span><h3>${safe(shown.block_name)}</h3>
    <p>排程依据 ${tag(shown.profile)} v${shown.revision} · ${shown.minutes} 分钟 ${shown.state==='needs_replan' ? `→ 生效标签 ${tag(shown.active_profile)} v${shown.active_revision}` : ''}</p>
    ${shown.review_hold ? notice(`候选群落变更暂缓了本轮次。请在群落页处理 #${shown.pending_run_id}。`,'caution') : ''}
    ${canWrite && shown.state === 'needs_replan' ? `<form data-action="replan" data-id="${shown.id}">
      ${field('starts_at','改排开始时间','type="datetime-local" value="2026-11-21T08:20"')}${paragraph('reason','改排记录','写明新窗口依据')}${button('按新标签保存改排')}</form>` : ''}
    ${canWrite && shown.state === 'scheduled' && !shown.review_hold ? `<form data-action="complete" data-id="${shown.id}" class="inline-form">
      ${field('completed_at','实际完灌时间','type="datetime-local" value="2026-11-21T09:15"')}${button('登记完灌')}</form>` : ''}
    ${shown.state === 'completed' ? `<p class="muted">${localTime(shown.completed_at)} 完灌 · <a href="#harvest">前往采收观察</a></p>` : ''}
    ${supervisor && ['scheduled','needs_replan'].includes(shown.state) ? `<details class="form-fold"><summary>取消轮次</summary><form data-action="cancel" data-id="${shown.id}">
      ${paragraph('reason','取消原因','填写停灌或调整说明')}${button('确认取消','secondary')}</form></details>` : ''}
    </article>` : ''}</section>
    <section class="ledger"><h2>新增滴灌轮次</h2>
    ${canWrite && viable.length ? `<form data-action="schedule">${field('code','轮次编号','placeholder="IR-1121A"')}
      ${select('block_id','地块',viable.map(b => [b.id,`${b.code} ${b.name}`]), shown?.block_id)}
      ${field('starts_at','开始时间','type="datetime-local" value="2026-11-21T07:00"')}${button('按标签排入轮次')}</form>
      <p class="muted">凉湿 20 分钟 · 温和 35 分钟 · 暖干 50 分钟。地块时段不得重叠。</p>` : notice(viable.length ? '当前账号可查看轮次。' : '请先识别并发布群落标签。')}
    </section></div>`;
}

export function harvestPage(notes, rounds, canWrite) {
  const occupied = new Set(notes.map(n => n.round_id));
  const open = rounds.filter(r => r.state === 'completed' && !occupied.has(r.id));
  return `${title('采收观察', '将采前抽样糖度与本次滴灌记录、当时的标签版本关联。')}
    <div class="spread"><section><div class="section-label"><h2>抽样簿</h2><span>${notes.length} 笔观察</span></div>
      ${notes.length ? notes.map(n => `<article class="harvest-slip"><span class="ref">${safe(n.block_code)} / ${safe(n.round_code)}</span>
        <h3>${safe(n.block_name)} <b>${num(n.brix)} °Bx</b></h3><p>${safe(n.note)}</p>
        <p class="muted">${n.berry_count} 粒 · ${localTime(n.observed_at)} · ${tag(n.profile)} v${n.revision}</p></article>`).join('') : notice('尚未登记观察。轮次完灌后可录入糖度与果粒抽样。')}
      </section><section class="ledger"><h2>登记采前抽样</h2>
      ${canWrite && open.length ? `<form data-action="harvest">
        ${select('round_id','关联已完灌轮次',open.map(r => [r.id,`${r.code} · ${r.block_name}`]))}
        ${field('observed_at','观察时间','type="datetime-local" value="2026-11-21T10:30"')}
        <div class="fields">${field('brix','糖度 °Bx','type="number" min="0" max="45" step="0.1"')}${field('berry_count','样本果粒数','type="number" min="20" max="500"')}</div>
        ${paragraph('note','成熟度与取样备注','例如：北坡三行均匀抽样，果皮着色一致。')}${button('归档采收观察')}
      </form>` : notice(canWrite ? '暂无可关联的完灌轮次。' : '当前账号可查阅来源与观察记录。')}
    </section></div>`;
}
