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

export type AuthMeResponse = {
  id: number;
  username: string;
  real_name: string;
  role: string;
  is_active: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  role: string;
  user_id: number;
  username: string;
  real_name: string;
};

export type CaseTaskPatchResponse = {
  case_name: string;
  status: string;
  assignee_id: number | null;
  assignee_real_name: string | null;
  project_id: number;
};

/** PATCH /api/cases/{case_name} — 只傳入要更新的欄位；assignee_id: null 表示未指派 */
export async function updateCaseTask(
  caseName: string,
  patch: Partial<{ status: string; assignee_id: number | null; project_id: number }>,
): Promise<CaseTaskPatchResponse> {
  const { data } = await axios.patch<CaseTaskPatchResponse>(
    `/api/cases/${encodeURIComponent(caseName)}`,
    patch,
  );
  return data;
}
