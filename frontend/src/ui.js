import {profiles} from './domain.js';

export const safe = value => String(value ?? '').replace(/[&<>"']/g, ch =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[ch]);
export const num = (value, digits=1) => Number(value).toFixed(digits);
export const localTime = value => value ? new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai',
  month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)) : '—';
export const chinaTime = value => new Date(`${value}+08:00`).toISOString();
export const formData = form => Object.fromEntries(new FormData(form));
export const numeric = (data, ...keys) => {
  keys.forEach(key => {data[key] = Number(data[key]);});
  return data;
};
export const tag = profile => profile
  ? `<span class="tag ${safe(profile)}">${safe(profiles[profile])}</span>` : '<span class="tag neutral">待标注</span>';
export const notice = (text, kind = '') => `<p class="notice ${kind}">${safe(text)}</p>`;
export const title = (name, summary, aside = '') => `<header class="page-title"><div><h1>${safe(name)}</h1><p>${safe(summary)}</p></div>${aside}</header>`;
export const field = (name, caption, attrs = '') => `<label>${caption}<input name="${name}" ${attrs} required></label>`;
export const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
export const select = (name, label, items, value) => `<label>${label}<select name="${name}" aria-label="${safe(label)}" required>${items.map(([id, text]) =>
  `<option value="${safe(id)}" ${String(id) === String(value) ? 'selected' : ''}>${safe(text)}</option>`).join('')}</select></label>`;
export const button = (text, style='primary') => `<button class="${style}" type="submit">${text}</button>`;
export const paragraph = (name, label, hint) => `<label>${label}<textarea name="${name}" minlength="5" maxlength="400" placeholder="${hint}" rows="2" required></textarea></label>`;
