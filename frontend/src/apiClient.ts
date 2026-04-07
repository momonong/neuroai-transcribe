import axios from 'axios';

export const TOKEN_KEY = 'neuroai_token';

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    axios.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    localStorage.removeItem(TOKEN_KEY);
    delete axios.defaults.headers.common.Authorization;
  }
}

export function loadAuthTokenFromStorage(): void {
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) {
    axios.defaults.headers.common.Authorization = `Bearer ${t}`;
  }
}
