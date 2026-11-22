const tokenKey = 'vineyard.field-session';
export const session = {
  get: () => sessionStorage.getItem(tokenKey),
  set: token => sessionStorage.setItem(tokenKey, token),
  clear: () => sessionStorage.removeItem(tokenKey),
};

export async function api(path, body) {
  const headers = {};
  if (session.get()) headers.Authorization = `Bearer ${session.get()}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {method: body === undefined ? 'GET' : 'POST', headers,
    body: body === undefined ? undefined : JSON.stringify(body)});
  if (response.ok) return response.json();
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== '/login') {
    session.clear();
    window.dispatchEvent(new Event('vineyard:expired'));
  }
  const detail = Array.isArray(data.detail)
    ? `请核对字段 ${data.detail.map(error => error.loc.at(-1)).join('、')}` : data.detail;
  throw new Error(detail || `服务暂未响应（${response.status}）`);
}
