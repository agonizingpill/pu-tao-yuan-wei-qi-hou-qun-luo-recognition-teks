import {slots, profiles} from './domain.js';
import {safe, num, notice, tag, title, field, table, select, button} from './ui.js';

export function blockPage(blocks, block, history, canWrite) {
  const geometry = blocks.map(b => `<button type="button" class="parcel ${safe(b.profile || 'neutral')} ${b.id === block?.id ? 'chosen' : ''}"
    data-block="${b.id}" aria-pressed="${b.id === block?.id}" style="--e:${b.east_m/10}%;--n:${b.north_m/10}%;--w:${b.width_m/10}%;--h:${b.height_m/10}%">${safe(b.code)}<small>${safe(b.name)}</small></button>`).join('');
  const rows = blocks.map(b => `<tr><td><button class="text-button" data-block="${b.id}">${safe(b.code)}</button></td><td>${safe(b.name)}</td><td>${safe(b.sensor)}</td><td>${tag(b.profile)}</td></tr>`);
  return `${title('地块与采样', '按地块核对探头、昼夜读数和当前群落标签。')}
    <div class="spread">
      <section><div class="section-label"><h2>坡畦边界图</h2><span>局部坐标 · 1,000 × 1,000 m</span></div>
        <div class="survey-map"><span class="north">↑ N</span><div class="site">${geometry}</div><span class="scale">地块边界示意</span></div>
        <div class="legend">${Object.keys(profiles).map(tag).join('')}</div>
        ${rows.length ? table(['地块','地形名','绑定探头','已生效标签'], rows) : notice('还没有地块。登记边界与探头后开始记采。')}
      </section>
      <section class="ledger">${block ? `
        <span class="ref">${safe(block.code)} / ${safe(block.sensor)}</span>
        <h2>${safe(block.name)}</h2>
        <p class="muted">${safe(block.cultivar)} · ${num(block.area_ha,2)} ha ${block.revision ? `· 标签 v${block.revision}` : ''}</p>
        ${canWrite ? `<details class="form-fold" id="capture"><summary>录入或补采读数</summary><form data-action="sample">
          <input type="hidden" name="block_id" value="${block.id}"><div class="fields">
          ${field('sensor','探头编号',`value="${safe(block.sensor)}" readonly`)}${field('observed_day','采样日期','type="date" value="2026-11-20"')}
          ${select('slot','采样班次',Object.entries(slots),'night')}${field('source','原始文件或巡检单','placeholder="wx-recheck-1121.csv" maxlength="90"')}
          ${field('temp_c','温度 °C','type="number" min="-30" max="60" step="0.1"')}${field('rh_pct','相对湿度 %','type="number" min="0" max="100" step="0.1"')}</div>${button('归档读数')}
        </form></details>` : ''}
        <h3>近期气象采样</h3>
        ${history.length ? table(['日期','班次','气温','湿度'], history.slice(0,12).map(r =>
          `<tr title="${safe(r.source)}"><td>${safe(r.observed_day.slice(5))}</td><td>${slots[r.slot]}</td><td>${num(r.temp_c)} °</td><td>${num(r.rh_pct,0)}%</td></tr>`)) : notice('这个探头还没有采样记录。')}` : notice('从边界图选择地块以查看采样。')}
      </section>
    </div>
    ${canWrite ? `<details class="form-fold bottom"><summary>登记新地块</summary><form data-action="block"><div class="fields wide">
      ${field('code','地块编号','placeholder="V-07"')}${field('name','地形名')}${field('cultivar','品种')}${field('area_ha','面积 ha','type="number" min="0.01" max="500" step="0.01"')}
      ${field('sensor','探头编号','placeholder="WX-307"')}${field('east_m','西缘东距 m','type="number" min="0" max="999"')}${field('north_m','南缘北距 m','type="number" min="0" max="999"')}
      ${field('width_m','东西跨度 m','type="number" min="1" max="500"')}${field('height_m','南北跨度 m','type="number" min="1" max="500"')}</div>${button('登记地块与探头')}
    </form></details>` : ''}`;
}
