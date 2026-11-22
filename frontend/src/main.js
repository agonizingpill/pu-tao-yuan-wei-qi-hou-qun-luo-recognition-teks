import {api, session} from './api.js';
import {roles} from './domain.js';
import {blockPage} from './blocks.js';
import {clusterPage} from './clusters.js';
import {harvestPage, irrigationPage} from './irrigation.js';
import {safe, field, formData, numeric, chinaTime} from './ui.js';

const app = document.querySelector('#app');
const routes = {blocks:'地块与采样', clusters:'微气候群落', irrigation:'灌溉轮次', harvest:'采收观察'};
const currentPage = () => Object.hasOwn(routes, location.hash.slice(1)) ? location.hash.slice(1) : 'blocks';
const state = {user:null, block:null, run:null, round:null, request:0, poll:null};

function loginPage() {
  app.innerHTML = `<main class="login-wrap">
    <section class="folio"><span class="ref">砾岚酒庄 / 田间工作台</span>
      <h1>坡畦<br>勘测册</h1><p>葡萄园微气候、滴灌排程与采前抽样</p>
      <div class="cover-plot" aria-hidden="true"><span>↑ N</span><i></i><i></i><i></i><i></i><i></i></div>
    </section>
    <section class="login-desk"><h2>登录田间工作台</h2><form data-action="login">
      ${field('username','账号','autocomplete="username"')}
      ${field('password','密码','type="password" autocomplete="current-password"')}
      <div class="feedback" role="status"></div><button class="primary" type="submit">进入勘测册</button>
    </form><div class="demo-roles"><h3>演示账号</h3>${Object.entries(roles).map(([id,label])=>
      `<button type="button" class="secondary" data-demo="${id}">${label}</button>`).join('')}</div></section></main>`;
}

function shell(page, body, message) {
  return `<header class="mast"><div class="mast-inner"><a class="brand" href="#blocks"><span>坡畦勘测册</span><small>砾岚酒庄</small></a>
    <nav aria-label="工作台">${Object.entries(routes).map(([key,label]) => `<a href="#${key}" ${key===page?'aria-current="page"':''}>${label}</a>`).join('')}</nav>
    <div class="actor"><span>${roles[state.user.role]}</span><button class="text-button" type="button" data-logout>退出</button></div>
    </div></header><main class="notebook"><div class="feedback ${message?'visible':''}" role="status">${safe(message)}</div>${body}</main>`;
}

async function render(message='') {
  const mark = ++state.request;
  clearTimeout(state.poll);
  if (!state.user) {loginPage(); return;}
  const page = currentPage();
  const supervisor = state.user.role === 'supervisor';
  const editable = state.user.role !== 'viewer';
  let body, queued;
  try {
    if (page === 'blocks') {
      const blocks = await api('/blocks');
      const block = blocks.find(b => b.id === state.block) || blocks[1] || blocks[0];
      const history = block ? await api(`/blocks/${block.id}/samples`) : [];
      body = blockPage(blocks, block, history, editable);
    } else if (page === 'clusters') {
      const [runs, labels] = await Promise.all([api('/runs'),api('/labels')]);
      const id = runs.find(r => r.id === state.run)?.id || runs[0]?.id;
      const run = id ? await api(`/runs/${id}`) : null;
      queued = run?.status === 'queued';
      body = clusterPage(runs, run, labels, editable, supervisor);
    } else if (page === 'irrigation') {
      const [blocks, rounds] = await Promise.all([api('/blocks'),api('/rounds')]);
      body = irrigationPage(blocks, rounds, rounds.find(r => r.id === state.round), editable, supervisor);
    } else {
      const [notes, rounds] = await Promise.all([api('/harvest'),api('/rounds')]);
      body = harvestPage(notes, rounds, editable);
    }
  } catch (error) {
    body = `<h1>工作台暂不可用</h1><p class="notice caution">${safe(error.message)}</p><button class="secondary" data-reload>重新加载</button>`;
  }
  if (mark !== state.request) return;
  app.innerHTML = shell(page, body, message);
  if (queued) state.poll = setTimeout(render, 1000);
}

function logout() {
  session.clear();
  Object.assign(state, {user:null, block:null, run:null, round:null});
  render();
}

function showError(error) {
  const feedback = app.querySelector('.feedback');
  if (!feedback) return;
  feedback.textContent = error.message;
  feedback.classList.add('visible', 'caution');
  feedback.scrollIntoView({block:'nearest'});
}

async function mutate(action, data, id) {
  switch (action) {
    case 'login': {
      const account = await api('/login', data);
      session.set(account.token);
      state.user = account;
      return '';
    }
    case 'block': {
      const block = await api('/blocks',numeric(data,'area_ha','east_m','north_m','width_m','height_m'));
      state.block = block.id;
      return `已登记地块 ${block.code}。`;
    }
    case 'sample':
      await api('/samples', numeric(data,'block_id','temp_c','rh_pct'));
      return '读数已归档。可在群落页重新提交缺测窗口。';
    case 'run': {
      const run = await api('/runs',data);
      state.run = run.id;
      return `已记录识别批次 #${run.id}。`;
    }
    case 'decision':
      await api(`/runs/${id}/decision`, {...data, approve:data.approve==='true'});
      return data.approve === 'true' ? '已发布标签，请到灌溉轮次处理待改排时段。' : '已退回候选标签。';
    case 'retry':
      await api(`/runs/${id}/retry`,{});
      return '原采样快照已重新入队。';
    case 'schedule': {
      const round = await api('/rounds', {...numeric(data,'block_id'), starts_at:chinaTime(data.starts_at)});
      state.round = round.id;
      return `已排 ${round.code}，${round.minutes} 分钟。`;
    }
    case 'replan':
      await api(`/rounds/${id}/replan`,{...data,starts_at:chinaTime(data.starts_at)});
      return '已按生效标签重新排灌，旧标签依据已归档。';
    case 'complete':
      await api(`/rounds/${id}/complete`,{completed_at:chinaTime(data.completed_at)});
      return '已登记完灌。';
    case 'cancel':
      await api(`/rounds/${id}/cancel`,data);
      return '已取消该轮次。';
    case 'harvest':
      await api('/harvest',{...numeric(data,'round_id','brix','berry_count'), observed_at:chinaTime(data.observed_at)});
      return '采收观察已归档。';
  }
}

app.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.action) return;
  event.preventDefault();
  const data = formData(form);
  if (event.submitter?.name) data[event.submitter.name] = event.submitter.value;
  form.querySelectorAll('button').forEach(button => button.disabled = true);
  try {await render(await mutate(form.dataset.action, data, form.dataset.id));}
  catch (error) {showError(error);}
  finally {form.querySelectorAll('button').forEach(button => button.disabled = false);}
});

app.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  const {block, round, demo, evidence, logout: exit, reload} = button.dataset;
  if (demo) {
    const form = app.querySelector('form');
    form.elements.username.value = demo;
    form.elements.password.value = 'Vineyard271!';
    form.querySelector('button').focus();
  }
  if (exit !== undefined) logout();
  if (block) {state.block = Number(block); await render();}
  if (round) {state.round = Number(round); await render();}
  if (reload !== undefined) await render();
  if (evidence) {
    try {
      const run = await api(`/runs/${Number(evidence)}/evidence`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(run,null,2)], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = `run-${run.id}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch (error) {showError(error);}
  }
});
app.addEventListener('change', event => {
  if (event.target.name === 'run') {state.run = Number(event.target.value); render();}
});
window.addEventListener('hashchange', () => {window.scrollTo(0,0); render();});
window.addEventListener('vineyard:expired', logout);

if (session.get()) {
  try {state.user = await api('/me');} catch {session.clear();}
}
await render();
